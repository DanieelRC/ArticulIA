"""Dataset de evaluación y métricas propias (hit@k, MRR, abstención, citas válidas, latencia).

Las métricas de Ragas (fidelidad y relevancia) se calculan en `eval/run_eval.py`; aquí solo va lo
que no necesita un LLM para poder probarse sin red.
"""

import json
import math
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TipoPregunta = Literal["directa", "multiple", "sin_respuesta"]


class Pregunta(BaseModel):
    """Una línea de `eval/dataset.jsonl`."""

    id: str = Field(description="Identificador único, p. ej. 'lft-vacaciones-1'.")
    pregunta: str = Field(min_length=5)
    tipo: TipoPregunta
    esperados: list[str] = Field(
        default_factory=list,
        description="Ids de artículo que responden la pregunta: 'LFT-76', 'LFT-47_Bis'.",
    )
    referencia: str = Field(min_length=3, description="Respuesta de referencia breve.")

    @model_validator(mode="after")
    def _coherente(self) -> "Pregunta":
        if self.tipo == "sin_respuesta" and self.esperados:
            raise ValueError(f"{self.id}: una pregunta sin_respuesta no lleva artículos esperados")
        if self.tipo != "sin_respuesta" and not self.esperados:
            raise ValueError(f"{self.id}: falta la lista de artículos esperados")
        if self.tipo == "multiple" and len(self.esperados) < 2:
            raise ValueError(f"{self.id}: una pregunta multiple espera dos o más artículos")
        return self

    @property
    def leyes(self) -> set[str]:
        """Leyes de los artículos esperados."""
        return {e.split("-", 1)[0] for e in self.esperados}


def cargar_dataset(path: Path, ids_validos: set[str] | None = None) -> list[Pregunta]:
    """Lee y valida el dataset. Con `ids_validos`, exige que cada artículo esperado exista."""
    preguntas: list[Pregunta] = []
    errores: list[str] = []
    with open(path, encoding="utf-8") as f:
        for n, linea in enumerate(f, start=1):
            if not linea.strip() or linea.lstrip().startswith("//"):
                continue
            try:
                preguntas.append(Pregunta.model_validate_json(linea))
            except ValueError as exc:
                errores.append(f"línea {n}: {exc}")
    repetidos = [i for i, c in Counter(p.id for p in preguntas).items() if c > 1]
    if repetidos:
        errores.append(f"ids repetidos: {repetidos}")
    if ids_validos is not None:
        for p in preguntas:
            faltan = [e for e in p.esperados if e not in ids_validos]
            if faltan:
                errores.append(f"{p.id}: artículos que no existen en el corpus: {faltan}")
    if errores:
        raise ValueError("Dataset inválido:\n- " + "\n- ".join(errores))
    return preguntas


def ids_del_corpus(processed_dir: Path) -> set[str]:
    """Ids de todos los artículos de `data/processed/*.jsonl`."""
    ids: set[str] = set()
    for path in processed_dir.glob("*.jsonl"):
        with open(path, encoding="utf-8") as f:
            ids.update(json.loads(line)["id"] for line in f if line.strip())
    return ids


# --- Métricas de recuperación ---------------------------------------------------------------


def hit_at_k(recuperados: list[str], esperados: list[str], k: int = 5) -> float:
    """1 si al menos un artículo esperado aparece entre los primeros k."""
    return float(any(r in esperados for r in recuperados[:k]))


def reciprocal_rank(recuperados: list[str], esperados: list[str], k: int = 5) -> float:
    """1/posición del primer artículo esperado dentro de los primeros k (0 si no aparece)."""
    for pos, r in enumerate(recuperados[:k], start=1):
        if r in esperados:
            return 1.0 / pos
    return 0.0


def recall_at_k(recuperados: list[str], esperados: list[str], k: int = 5) -> float:
    """Fracción de los artículos esperados que aparecen entre los primeros k."""
    if not esperados:
        return 0.0
    return len(set(recuperados[:k]) & set(esperados)) / len(esperados)


# --- Métricas del agente ------------------------------------------------------------------------


def citas_validas(citados: list[str], recuperados: set[str]) -> float | None:
    """Fracción de citas que apuntan a artículos recuperados por el agente (None sin citas)."""
    if not citados:
        return None
    return sum(c in recuperados for c in citados) / len(citados)


def percentil(valores: list[float], p: float) -> float:
    """Percentil por interpolación lineal (p entre 0 y 100)."""
    if not valores:
        return math.nan
    xs = sorted(valores)
    pos = (len(xs) - 1) * p / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def media(valores: list[float | None]) -> float:
    """Promedio ignorando None (nan si no hay valores)."""
    xs = [v for v in valores if v is not None]
    return sum(xs) / len(xs) if xs else math.nan


# --- Reporte ------------------------------------------------------------------------------------


class Fila(BaseModel):
    """Renglón de la tabla de resultados."""

    metrica: str
    valor: float
    meta: str = ""
    formato: Literal["ratio", "segundos", "entero"] = "ratio"

    def valor_txt(self) -> str:
        """Valor formateado para Markdown."""
        if math.isnan(self.valor):
            return "n/d"
        if self.formato == "segundos":
            return f"{self.valor:.1f} s"
        if self.formato == "entero":
            return f"{self.valor:,.0f}"
        return f"{self.valor:.2f}"


def tabla_markdown(filas: list[Fila], titulo: str | None = None) -> str:
    """Tabla lista para pegar en el README."""
    lineas = [f"**{titulo}**", ""] if titulo else []
    lineas += ["| Métrica | Valor | Meta |", "| --- | ---: | ---: |"]
    lineas += [f"| {f.metrica} | {f.valor_txt()} | {f.meta} |" for f in filas]
    return "\n".join(lineas)


def resumen_dataset(preguntas: list[Pregunta]) -> dict[str, object]:
    """Distribución por tipo y por ley, para revisar que el dataset esté balanceado."""
    por_ley: Counter[str] = Counter()
    for p in preguntas:
        por_ley.update(p.leyes)
    return {
        "total": len(preguntas),
        "por_tipo": dict(Counter(p.tipo for p in preguntas)),
        "por_ley": dict(sorted(por_ley.items())),
    }
