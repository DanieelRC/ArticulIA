"""Pruebas de las métricas propias, del validador del dataset y del script de evaluación."""

import importlib.util
import json
import math
from pathlib import Path

import pytest

from articulia.evaluation import (
    Fila,
    Pregunta,
    cargar_dataset,
    citas_validas,
    hit_at_k,
    media,
    percentil,
    recall_at_k,
    reciprocal_rank,
    resumen_dataset,
    tabla_markdown,
)

RAIZ = Path(__file__).resolve().parent.parent


def _run_eval():
    spec = importlib.util.spec_from_file_location("run_eval", RAIZ / "eval" / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Métricas ---------------------------------------------------------------------------------


def test_hit_y_mrr() -> None:
    recuperados = ["LFT-59", "LFT-66", "LFT-63", "LFT-58", "LFT-61"]
    assert hit_at_k(recuperados, ["LFT-61"]) == 1.0
    assert hit_at_k(recuperados, ["LFT-61"], k=4) == 0.0
    assert reciprocal_rank(recuperados, ["LFT-61"]) == pytest.approx(1 / 5)
    assert reciprocal_rank(recuperados, ["LFT-61", "LFT-59"]) == 1.0
    assert reciprocal_rank(recuperados, ["LFT-76"]) == 0.0


def test_recall() -> None:
    assert recall_at_k(["LFT-76", "LFT-78"], ["LFT-76", "LFT-80"]) == 0.5
    assert recall_at_k(["LFT-76"], []) == 0.0


def test_citas_validas() -> None:
    assert citas_validas(["LFT-76", "LFT-78"], {"LFT-76", "LFT-78", "LFT-81"}) == 1.0
    assert citas_validas(["LFT-76", "LFT-80"], {"LFT-76"}) == 0.5
    assert citas_validas([], {"LFT-76"}) is None


def test_percentil_y_media() -> None:
    assert percentil([1, 2, 3, 4], 50) == 2.5
    assert percentil([10.0], 95) == 10.0
    assert math.isnan(percentil([], 50))
    assert media([1.0, None, 0.0]) == 0.5
    assert math.isnan(media([None]))


def test_tabla_markdown() -> None:
    tabla = tabla_markdown(
        [
            Fila(metrica="Hit@5", valor=0.875, meta="≥ 0.85"),
            Fila(metrica="Latencia p50", valor=12.34, formato="segundos"),
            Fila(metrica="Fidelidad", valor=math.nan),
        ],
        "Evaluación",
    )
    assert "| Hit@5 | 0.88 | ≥ 0.85 |" in tabla
    assert "| Latencia p50 | 12.3 s |  |" in tabla
    assert "| Fidelidad | n/d |  |" in tabla


# --- Dataset ----------------------------------------------------------------------------------


def _linea(**kw: object) -> str:
    base = {
        "id": "lft-vacaciones-1",
        "pregunta": "¿Cuántos días de vacaciones me tocan en mi primer año?",
        "tipo": "directa",
        "esperados": ["LFT-76"],
        "referencia": "Doce días laborables.",
    }
    return json.dumps(base | kw, ensure_ascii=False)


def test_dataset_valido(tmp_path: Path) -> None:
    path = tmp_path / "d.jsonl"
    path.write_text(
        "\n".join(
            [
                _linea(),
                "// las líneas que empiezan con // son comentarios",
                _linea(
                    id="lft-jornada",
                    pregunta="¿Cuánto dura la jornada y cuál es el máximo semanal?",
                    tipo="multiple",
                    esperados=["LFT-59", "LFT-61"],
                    referencia="Ocho horas diurnas y cuarenta horas a la semana.",
                ),
                _linea(
                    id="fuera-1",
                    pregunta="¿Cuánto cuesta la verificación vehicular en la CDMX?",
                    tipo="sin_respuesta",
                    esperados=[],
                    referencia="No está en el corpus federal.",
                ),
            ]
        ),
        encoding="utf-8",
    )
    preguntas = cargar_dataset(path, {"LFT-76", "LFT-59", "LFT-61"})
    assert len(preguntas) == 3
    assert resumen_dataset(preguntas) == {
        "total": 3,
        "por_tipo": {"directa": 1, "multiple": 1, "sin_respuesta": 1},
        "por_ley": {"LFT": 2},
    }


@pytest.mark.parametrize(
    ("linea", "mensaje"),
    [
        (_linea(tipo="sin_respuesta"), "no lleva artículos esperados"),
        (_linea(esperados=[]), "falta la lista"),
        (_linea(tipo="multiple"), "dos o más"),
        (_linea(esperados=["LFT-9999"]), "no existen en el corpus"),
        (_linea() + "\n" + _linea(), "ids repetidos"),
    ],
)
def test_dataset_invalido(tmp_path: Path, linea: str, mensaje: str) -> None:
    path = tmp_path / "d.jsonl"
    path.write_text(linea, encoding="utf-8")
    with pytest.raises(ValueError, match=mensaje):
        cargar_dataset(path, {"LFT-76"})


def test_pregunta_conoce_sus_leyes() -> None:
    p = Pregunta(
        id="x",
        pregunta="¿Datos personales en la Constitución y en la ley?",
        tipo="multiple",
        esperados=["CPEUM-16", "LFPDPPP-3"],
        referencia="Ambas protegen los datos personales.",
    )
    assert p.leyes == {"CPEUM", "LFPDPPP"}


# --- Script -----------------------------------------------------------------------------------


def _salida(**kw: object) -> dict:
    base = {
        "id": "q",
        "tipo": "directa",
        "esperados": ["LFT-76"],
        "respuesta": "Doce días [LFT, art. 76].",
        "sin_evidencia": False,
        "citados": ["LFT-76"],
        "recuperados": ["LFT-76", "LFT-78"],
        "segundos": 10.0,
        "tokens": 1000,
        "error": None,
    }
    return base | kw


def test_metricas_agente() -> None:
    filas = _run_eval().metricas_agente(
        [
            _salida(),
            _salida(id="q2", citados=["LFT-78", "LFT-80"], segundos=20.0, tokens=3000),
            _salida(id="q3", tipo="sin_respuesta", esperados=[], sin_evidencia=True, citados=[]),
            _salida(id="q4", tipo="sin_respuesta", esperados=[], sin_evidencia=False),
        ]
    )
    v = {f.metrica: f.valor for f in filas}
    assert v["Citas válidas"] == pytest.approx(0.75)  # (1 + 0.5) / 2
    assert v["Cita el artículo esperado"] == 0.5
    assert v["Abstención correcta"] == 0.5
    assert v["Abstención indebida"] == 0.0
    assert v["Tokens por consulta (media)"] == pytest.approx(1500)


def test_cli_solo_recuperacion_y_umbral(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _run_eval()
    dataset = tmp_path / "d.jsonl"
    dataset.write_text(_linea(), encoding="utf-8")
    monkeypatch.setattr(
        mod,
        "evaluar_recuperacion",
        lambda preguntas, usar_reranker: ([Fila(metrica="Hit@5", valor=0.5)], []),
    )
    salida = tmp_path / "res"
    codigo = mod.main(
        ["--dataset", str(dataset), "--salida", str(salida), "--solo-recuperacion",
         "--umbral-hit5", "0.8", "--etiqueta", "prueba"]
    )  # fmt: skip
    assert codigo == 1
    [md] = list(salida.glob("*-prueba.md"))
    assert "| Hit@5 | 0.50 |" in md.read_text(encoding="utf-8")
