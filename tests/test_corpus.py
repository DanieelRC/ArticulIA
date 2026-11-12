"""Validación del corpus procesado (data/processed). Se salta si no se ha corrido la ingesta."""

import json
from pathlib import Path

import pytest

from articulia.ingest.__main__ import summarize
from articulia.ingest.splitter import Article

PROCESSED = Path(__file__).parent.parent / "data" / "processed"
LEYES = ["CPEUM", "LFT", "CCF", "LFPDPPP", "LFDA", "LFPC"]


def _load(ley: str) -> list[Article]:
    path = PROCESSED / f"{ley}.jsonl"
    if not path.exists():
        pytest.skip(f"{path} no existe; corre `uv run python -m articulia.ingest`")
    with open(path, encoding="utf-8") as f:
        return [Article.model_validate_json(line) for line in f]


@pytest.mark.parametrize("ley", LEYES)
def test_numeracion_sin_huecos_ni_duplicados(ley: str) -> None:
    s = summarize(_load(ley))
    assert s["huecos"] == []
    assert s["duplicados"] == []


def test_constitucion_tiene_136_articulos_permanentes() -> None:
    assert summarize(_load("CPEUM"))["permanentes"] == 136


def test_lft_articulo_61_jornada() -> None:
    art = {a.id: a for a in _load("LFT")}["LFT-61"]
    assert art.capitulo == "Capítulo II. Jornada de trabajo"
    assert "jornada diaria" in art.texto
    assert all("DOF" not in line for line in art.texto.splitlines())


def test_registros_son_json_valido() -> None:
    with open(PROCESSED / "CPEUM.jsonl", encoding="utf-8") as f:
        first = json.loads(f.readline())
    assert first["id"] == "CPEUM-1"
    assert first["url"].endswith("/CPEUM.pdf")
