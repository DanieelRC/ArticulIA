"""Divide el texto limpio de una ley en artículos con sus metadatos."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel

from articulia.ingest.loader import LawDocument

_SUFFIXES = {
    "bis": "Bis",
    "ter": "Ter",
    "quater": "Quáter",
    "quáter": "Quáter",
    "quintus": "Quintus",
    "quinquies": "Quinquies",
    "sexies": "Sexies",
    "septies": "Septies",
    "octies": "Octies",
    "nonies": "Nonies",
    "decies": "Decies",
}
_SUFFIX_RE = "|".join(sorted(_SUFFIXES, key=len, reverse=True))

# "Artículo 5o.-", "Artículo 123 Bis.-", "Artículo 103-Bis.-", "Artículo 65 Bis 7.",
# "Artículo 39-A.-", "Artículo 410 A.-", "ARTICULO 1º.-", "Artículo 14."
# El sufijo va ANTES del terminador, así "Artículo 14. A ninguna..." no toma la "A" como sufijo.
_ARTICLE = re.compile(
    r"^(?:ART[IÍ]CULOS?|Art[ií]culos?)\s+(?P<num>\d+)\s*(?:o|º|°)?"
    rf"(?:\.?\s*-?\s*(?P<suf>(?i:{_SUFFIX_RE}))(?:\s+(?P<sufn>\d+))?"
    r"|\s*-?\s*(?P<let>[A-Z])(?=\s*[.-]))?"
    r"\s*(?:\.\s*-|\.|-)(?=\s|\(|$)\s*"
)

_ORDINAL = (
    r"(?:(?:d[eé]cim|vig[eé]sim|trig[eé]sim)[oa]?\s*)?"
    r"(?:primer|segund|tercer|cuart|quint|sext|s[eé]ptim|octav|noven|d[eé]cim|und[eé]cim|"
    r"duod[eé]cim|vig[eé]sim|trig[eé]sim|[uú]nic)[oa]?"
)
# Transitorios con ordinal: "PRIMERO.-", "Artículo Primero.", "ARTÍCULO ÚNICO.-"
_ORDINAL_ARTICLE = re.compile(
    rf"^(?:(?:ART[IÍ]CULO|Art[ií]culo)\s+)?(?P<ord>(?i:{_ORDINAL}))\s*(?:\.\s*-|\.|-)\s*"
)
_TRANSITORIOS = re.compile(
    r"^(?:ART[IÍ]CULOS\s+|Art[ií]culos\s+)?(?:TRANSITORIOS?|Transitorios?):?$"
)
_REFORM_DECREES = re.compile(r"^ART[IÍ]CULOS TRANSITORIOS DE DECRETOS DE REFORMA")
# Fórmulas de cierre del decreto original; lo que sigue son firmas, no artículos.
_CLOSING = re.compile(
    r"^(?:Por tanto,? mando|SAL[OÓ]N DE SESIONES|Sal[oó]n de Sesiones|"
    r"M[eé]xico, D\.\s?F\.,? a|Ciudad de M[eé]xico, a|Dado en )"
)
_STRUCTURE = re.compile(
    r"^(?P<kind>LIBRO|Libro|T[IÍ]TULO|T[ií]tulo|CAP[IÍ]TULO|Cap[ií]tulo|SECCI[OÓ]N|Secci[oó]n)\s+"
    rf"(?P<ord>[IVXLC]+|(?i:{_ORDINAL}))(?:\s+(?i:bis|ter))?\b\.?\s*(?P<rest>.*)$"
)
_LEVELS = ("libro", "titulo", "capitulo", "seccion")
_LEVEL_NAMES = {"libro": "Libro", "titulo": "Título", "capitulo": "Capítulo", "seccion": "Sección"}
# Notas de reforma: "Párrafo reformado DOF 10-06-2011", "Artículo derogado DOF ..."
_ANNOTATION = re.compile(
    r"^[A-ZÁÉÍÓÚÑ].{0,200}\b(?i:reformad|adicionad|derogad|original|recorrid|aclaraci|"
    r"erratas|reubicad|modificad|denominaci).{0,200}DOF\s+\d{2}-\d{2}-\d{4}"
)
_ANNOTATION_CONT = re.compile(r"^[\d\-,\sy]+$")
# Notas editoriales ("Nota: El artículo ... a la letra señalaba:") que citan otras leyes.
_NOTE = re.compile(r"^Nota:")
_DEROGATED = re.compile(r"^\(?\s*(?:Se deroga|Derogad[oa])\b", re.IGNORECASE)


class Article(BaseModel):
    """Un artículo de ley con sus metadatos, listo para indexar."""

    id: str
    ley: str
    ley_nombre: str
    numero: str
    numero_base: int | None
    tipo: Literal["articulo", "transitorio"]
    derogado: bool
    libro: str | None = None
    titulo: str | None = None
    capitulo: str | None = None
    seccion: str | None = None
    texto: str
    reformas: list[str]
    fecha_ultima_reforma: date | None
    url: str


def _structure_level(kind: str) -> str:
    """Normaliza 'TÍTULO', 'Capitulo', etc. a la clave de nivel."""
    k = kind.lower().replace("í", "i").replace("ó", "o")
    return {"libro": "libro", "titulo": "titulo", "capitulo": "capitulo", "seccion": "seccion"}[k]


def is_annotation(line: str) -> bool:
    """True si la línea es una nota de reforma del DOF y no texto legal."""
    return bool(_ANNOTATION.match(line))


def parse_article_heading(line: str) -> tuple[str, int, str] | None:
    """Reconoce un encabezado numérico de artículo.

    Devuelve (numero_normalizado, numero_base, resto_de_la_linea) o None.
    """
    m = _ARTICLE.match(line)
    if not m:
        return None
    num = int(m["num"])
    if m["suf"]:
        numero = f"{num} {_SUFFIXES[m['suf'].lower()]}" + (f" {m['sufn']}" if m["sufn"] else "")
    elif m["let"]:
        numero = f"{num}-{m['let']}"
    else:
        numero = str(num)
    return numero, num, line[m.end() :]


def _parse_ordinal_heading(line: str) -> tuple[str, str] | None:
    m = _ORDINAL_ARTICLE.match(line)
    if not m:
        return None
    return m["ord"].capitalize(), line[m.end() :]


def _ends_sentence(line: str) -> bool:
    return line == "" or line[-1] in '.:;)"”'


def split_law(doc: LawDocument) -> list[Article]:
    """Divide una ley en artículos permanentes y transitorios del texto original.

    Los transitorios de decretos de reforma posteriores se descartan.
    """
    articles: list[Article] = []
    context: dict[str, str | None] = dict.fromkeys(_LEVELS)
    current: dict | None = None
    pending_structure: str | None = None  # nivel cuyo nombre está en la(s) línea(s) siguiente(s)
    section: Literal["articulo", "transitorio"] = "articulo"
    prev = ""  # última línea vista
    prev_is_break = True  # la línea anterior permite iniciar un artículo

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        texto = "\n".join(current["lines"]).strip()
        texto = re.sub(r"\n{3,}", "\n\n", texto)
        clave = doc.clave if current["tipo"] == "articulo" else f"{doc.clave}-T"
        articles.append(
            Article(
                id=f"{clave}-{current['numero'].replace(' ', '_')}",
                ley=doc.clave,
                ley_nombre=doc.nombre,
                numero=current["numero"],
                numero_base=current["base"],
                tipo=current["tipo"],
                derogado=bool(_DEROGATED.match(texto)),
                **current["context"],
                texto=texto,
                reformas=current["reformas"],
                fecha_ultima_reforma=doc.fecha_ultima_reforma,
                url=doc.url,
            )
        )
        current = None

    def start(numero: str, base: int | None, rest: str) -> None:
        nonlocal current
        flush()
        current = {
            "numero": numero,
            "base": base,
            "tipo": section,
            "context": dict(context),
            "lines": [rest] if rest else [],
            "reformas": [],
        }

    started = False
    closed = False
    in_note = False  # dentro de una nota editorial: se descarta hasta el siguiente encabezado
    for line in doc.texto.splitlines():
        if _REFORM_DECREES.match(line):
            break
        if started and section == "articulo" and _TRANSITORIOS.match(line):
            flush()
            section = "transitorio"
            context = dict.fromkeys(_LEVELS)
            prev, prev_is_break = line, True
            continue
        if closed:
            continue
        if section == "transitorio" and _CLOSING.match(line):
            flush()
            closed = True
            continue

        if is_annotation(line) or (is_annotation(prev) and _ANNOTATION_CONT.match(line)):
            if current is not None:
                current["reformas"].append(line)
            pending_structure = None
            prev, prev_is_break = line, True
            continue

        heading = parse_article_heading(line) if prev_is_break else None
        # Un artículo citado dentro de una nota (p. ej. "Artículo 54.-" de otra ley tras el
        # artículo 1777) rompe la numeración ascendente: no es un artículo nuevo.
        if heading and current is not None and current["base"] and heading[1] < current["base"]:
            heading = None
        if heading is None and section == "transitorio" and prev_is_break:
            ordinal = _parse_ordinal_heading(line)
            if ordinal:
                heading = (ordinal[0], None, ordinal[1])
        if heading:
            started = True
            in_note = False
            pending_structure = None
            start(*heading)
            prev, prev_is_break = line, _ends_sentence(line)
            continue

        if _NOTE.match(line):
            in_note = True
        if in_note:
            prev, prev_is_break = line, _ends_sentence(line)
            continue

        struct = _STRUCTURE.match(line) if prev_is_break and section == "articulo" else None
        if struct:
            flush()
            in_note = False
            level = _structure_level(struct["kind"])
            idx = _LEVELS.index(level)
            for lower in _LEVELS[idx + 1 :]:
                context[lower] = None
            label = f"{_LEVEL_NAMES[level]} {struct['ord']}"
            rest = struct["rest"].strip(" .-")
            context[level] = f"{label}. {rest}" if rest else label
            pending_structure = None if rest else level
            prev, prev_is_break = line, True
            continue

        if pending_structure and line:
            name = context[pending_structure]
            sep = ". " if name and "." not in name else " "
            context[pending_structure] = f"{name}{sep}{line}"
            prev, prev_is_break = line, True
            continue
        if not line:
            pending_structure = None

        if current is not None:
            current["lines"].append(line)
        prev, prev_is_break = line, _ends_sentence(line)

    flush()
    return articles
