"""Convierte los PDFs de la Cámara de Diputados en texto limpio."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pymupdf

BASE_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf"

LEYES: dict[str, str] = {
    "CPEUM": "Constitución Política de los Estados Unidos Mexicanos",
    "LFT": "Ley Federal del Trabajo",
    "CCF": "Código Civil Federal",
    "LFPDPPP": "Ley Federal de Protección de Datos Personales en Posesión de los Particulares",
    "LFDA": "Ley Federal del Derecho de Autor",
    "LFPC": "Ley Federal de Protección al Consumidor",
}
"""Clave (nombre del PDF en LeyesBiblio) -> nombre oficial de la ley."""

# El encabezado de cada página termina en la línea "N de M".
_PAGE_COUNTER = re.compile(r"^\s*\d+\s+de\s+\d+\s*$")
_HEADER_MAX_LINES = 15
_LAST_REFORM = re.compile(r"[ÚU]ltima [Rr]eforma(?: publicada)? DOF (\d{2}-\d{2}-\d{4})")
# Numeral de fracción o inciso solo en su línea ("I.", "A.", "a)"): se une con la línea siguiente.
_LONE_NUMERAL = re.compile(r"^([IVXLC]+\.|[A-Z]\.|[a-z]\))[ \t]*\n[ \t]*(?=\S)", re.MULTILINE)


@dataclass(frozen=True)
class LawDocument:
    """Texto limpio de una ley y sus metadatos."""

    clave: str
    nombre: str
    fecha_ultima_reforma: date | None
    url: str
    texto: str


def strip_page_header(page_text: str) -> str:
    """Quita el encabezado repetido de una página (todo hasta la línea "N de M")."""
    lines = page_text.splitlines()
    for i, line in enumerate(lines[:_HEADER_MAX_LINES]):
        if _PAGE_COUNTER.match(line):
            return "\n".join(lines[i + 1 :])
    return page_text


def clean_text(text: str) -> str:
    """Normaliza espacios, une numerales sueltos con su texto y colapsa líneas vacías."""
    text = text.replace(" ", " ").replace("​", "")
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _LONE_NUMERAL.sub(r"\1 ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def parse_last_reform(text: str) -> date | None:
    """Extrae la fecha de última reforma (DOF dd-mm-aaaa) del texto de la portada."""
    match = _LAST_REFORM.search(text)
    return datetime.strptime(match.group(1), "%d-%m-%Y").date() if match else None


def load_pdf(path: Path) -> LawDocument:
    """Lee un PDF de LeyesBiblio y devuelve su texto limpio sin encabezados de página."""
    clave = path.stem.upper()
    with pymupdf.open(path) as doc:
        pages = [page.get_text() for page in doc]
    return LawDocument(
        clave=clave,
        nombre=LEYES.get(clave, clave),
        fecha_ultima_reforma=parse_last_reform(pages[0]) if pages else None,
        url=f"{BASE_URL}/{path.name}",
        texto=clean_text("\n".join(strip_page_header(p) for p in pages)),
    )
