"""Evaluación de ArticulIA sobre eval/dataset.jsonl.

Uso:
    uv run python eval/run_eval.py                       # completa: recuperación + agente + Ragas
    uv run python eval/run_eval.py --solo-recuperacion   # sin LLM: hit@5 y MRR
    uv run python eval/run_eval.py --solo-recuperacion --sin-reranker
    uv run python eval/run_eval.py --limite 10 --umbral-hit5 0.8   # evaluación rápida para CI
    uv run python eval/run_eval.py --reanudar                      # continuar una corrida cortada

Imprime una tabla Markdown lista para el README y guarda resultados en eval/results/.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # sin telemetría de Ragas

from articulia.evaluation import (  # noqa: E402
    Fila,
    Pregunta,
    cargar_dataset,
    citas_validas,
    hit_at_k,
    ids_del_corpus,
    media,
    percentil,
    recall_at_k,
    reciprocal_rank,
    resumen_dataset,
    tabla_markdown,
)

RAIZ = Path(__file__).resolve().parent.parent
CITA_RE = re.compile(r"\s*\[[A-Z]+,\s*(?:art\.|transitorio)[^\]]*\]")


# --- Recuperación --------------------------------------------------------------------------------


def evaluar_recuperacion(preguntas: list[Pregunta], usar_reranker: bool) -> tuple[list[Fila], list]:
    """hit@5, MRR y recall@5 de la búsqueda (sin LLM) sobre las preguntas con respuesta."""
    from articulia.db import connect
    from articulia.retrieval.rerank import search

    detalle = []
    with connect() as conn:
        search(conn, "calentamiento", top_k=5, use_reranker=usar_reranker)  # carga modelos
        for p in preguntas:
            if p.tipo == "sin_respuesta":
                continue
            t0 = time.perf_counter()
            ids = [r.id for r in search(conn, p.pregunta, top_k=5, use_reranker=usar_reranker)]
            detalle.append(
                {
                    "id": p.id,
                    "tipo": p.tipo,
                    "esperados": p.esperados,
                    "recuperados": ids,
                    "hit5": hit_at_k(ids, p.esperados),
                    "rr": reciprocal_rank(ids, p.esperados),
                    "recall5": recall_at_k(ids, p.esperados),
                    "segundos": time.perf_counter() - t0,
                }
            )
    lat = [d["segundos"] for d in detalle]
    filas = [
        Fila(metrica="Hit@5", valor=media([d["hit5"] for d in detalle]), meta="≥ 0.85"),
        Fila(metrica="MRR", valor=media([d["rr"] for d in detalle]), meta="≥ 0.70"),
        Fila(metrica="Recall@5", valor=media([d["recall5"] for d in detalle])),
        Fila(metrica="Latencia búsqueda p50", valor=percentil(lat, 50), formato="segundos"),
    ]
    return filas, detalle


# --- Agente --------------------------------------------------------------------------------------


def correr_agente(preguntas: list[Pregunta], progreso: Path | None = None) -> list[dict]:
    """Corre el agente completo y registra respuesta, recuperados, citas, latencia y tokens.

    Con `progreso`, cada pregunta se escribe en ese JSONL al terminar y las que ya están ahí no
    se vuelven a correr: una evaluación interrumpida se reanuda sin pagarla dos veces.
    """
    from langchain_core.callbacks import get_usage_metadata_callback

    from articulia.agent.graph import _RECURSION_LIMIT, _inicial, build_graph

    hechas: dict[str, dict] = {}
    if progreso is not None and progreso.exists():
        with open(progreso, encoding="utf-8") as f:
            hechas = {d["id"]: d for d in map(json.loads, filter(str.strip, f))}
        print(f"Reanudando: {len(hechas)} preguntas ya evaluadas", file=sys.stderr)

    graph = build_graph()
    salidas = []
    for i, p in enumerate(preguntas, start=1):
        if p.id in hechas and not hechas[p.id].get("error"):
            salidas.append(hechas[p.id])
            continue
        print(f"[{i}/{len(preguntas)}] {p.id}", file=sys.stderr)
        t0 = time.perf_counter()
        with get_usage_metadata_callback() as uso:
            try:
                final = graph.invoke(
                    _inicial(p.pregunta, None), {"recursion_limit": _RECURSION_LIMIT}
                )
                error = None
            except Exception as exc:  # una pregunta fallida no detiene la evaluación
                final, error = {}, f"{type(exc).__name__}: {exc}"
        segundos = time.perf_counter() - t0
        resp = final.get("respuesta")
        articulos = final.get("articulos", {})
        usos = uso.usage_metadata.values()
        salida = {
            "id": p.id,
            "tipo": p.tipo,
            "pregunta": p.pregunta,
            "esperados": p.esperados,
            "referencia": p.referencia,
            "respuesta": resp.respuesta if resp else None,
            "sin_evidencia": resp.sin_evidencia if resp else None,
            "citados": [c.article_id for c in resp.citas] if resp else [],
            "recuperados": list(articulos),
            "textos": {k: v["texto"] for k, v in articulos.items()},
            "segundos": segundos,
            "tokens": sum(u.get("total_tokens", 0) for u in usos),
            "tokens_entrada": sum(u.get("input_tokens", 0) for u in usos),
            "tokens_salida": sum(u.get("output_tokens", 0) for u in usos),
            "iteraciones": final.get("iteraciones"),
            "error": error,
        }
        salidas.append(salida)
        if progreso is not None:
            with open(progreso, "a", encoding="utf-8") as f:
                f.write(json.dumps(salida, ensure_ascii=False) + "\n")
    return salidas


def metricas_agente(salidas: list[dict]) -> list[Fila]:
    """Citas válidas, abstención correcta, aciertos de cita, latencia y tokens."""
    con_resp = [s for s in salidas if s["tipo"] != "sin_respuesta" and s["respuesta"]]
    sin_resp = [s for s in salidas if s["tipo"] == "sin_respuesta"]
    respondidas = [s for s in con_resp if not s["sin_evidencia"]]
    lat = [s["segundos"] for s in salidas if not s["error"]]
    tok = [s["tokens"] for s in salidas if s["tokens"]]
    return [
        Fila(
            metrica="Citas válidas",
            valor=media([citas_validas(s["citados"], set(s["recuperados"])) for s in respondidas]),
            meta="1.00",
        ),
        Fila(
            metrica="Cita el artículo esperado",
            valor=media([float(bool(set(s["citados"]) & set(s["esperados"]))) for s in con_resp]),
        ),
        Fila(
            metrica="Abstención correcta",
            valor=media([float(bool(s["sin_evidencia"])) for s in sin_resp]),
            meta="≥ 0.80",
        ),
        Fila(
            metrica="Abstención indebida",
            valor=media([float(bool(s["sin_evidencia"])) for s in con_resp]),
            meta="lo más baja posible",
        ),
        Fila(metrica="Latencia p50", valor=percentil(lat, 50), formato="segundos"),
        Fila(metrica="Latencia p95", valor=percentil(lat, 95), formato="segundos"),
        Fila(metrica="Tokens por consulta (media)", valor=media(tok), formato="entero"),
        Fila(
            metrica="Iteraciones por consulta (media)",
            valor=media([s.get("iteraciones") for s in salidas]),
        ),
        Fila(
            metrica="Errores",
            valor=float(sum(1 for s in salidas if s["error"])),
            formato="entero",
        ),
    ]


# --- Ragas ---------------------------------------------------------------------------------------


class _EmbeddingsLocales:
    """Adaptador LangChain sobre los embeddings bge-m3 del proyecto (sin otra dependencia)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from articulia.models import embed

        return embed(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


def metricas_ragas(salidas: list[dict]) -> list[Fila]:
    """Fidelidad y relevancia de la respuesta con Ragas sobre las respuestas no abstenidas.

    El contexto de cada respuesta son los artículos que CITA (no todo lo recuperado): la fidelidad
    mide si cada afirmación está respaldada por los artículos citados.
    """
    import warnings

    from langchain_core.embeddings import Embeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.run_config import RunConfig

    from articulia.llm import get_llm

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from ragas.metrics import AnswerRelevancy, Faithfulness

    muestras = [
        {
            "user_input": s["pregunta"],
            "response": CITA_RE.sub("", s["respuesta"]),
            "retrieved_contexts": [s["textos"][c] for c in s["citados"] if c in s["textos"]],
            "reference": s["referencia"],
        }
        for s in salidas
        if s["respuesta"] and not s["sin_evidencia"] and s["citados"]
    ]
    if not muestras:
        return []

    emb = type("Bge", (_EmbeddingsLocales, Embeddings), {})()
    resultado = evaluate(
        EvaluationDataset.from_list(muestras),
        metrics=[Faithfulness(), AnswerRelevancy(strictness=1)],
        llm=LangchainLLMWrapper(get_llm()),
        embeddings=LangchainEmbeddingsWrapper(emb),
        run_config=RunConfig(max_workers=2, timeout=180),
        show_progress=True,
    )
    df = resultado.to_pandas()
    return [
        Fila(metrica="Fidelidad (Ragas)", valor=float(df["faithfulness"].mean()), meta="≥ 0.85"),
        Fila(
            metrica="Relevancia de la respuesta (Ragas)",
            valor=float(df["answer_relevancy"].mean()),
            meta="≥ 0.80",
        ),
    ]


# --- CLI -----------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Corre la evaluación y devuelve el código de salida (1 si hit@5 queda bajo el umbral)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=RAIZ / "eval" / "dataset.jsonl")
    ap.add_argument("--salida", type=Path, default=RAIZ / "eval" / "results")
    ap.add_argument("--limite", type=int, help="Evaluar solo las primeras N preguntas.")
    ap.add_argument("--solo-recuperacion", action="store_true", help="Sin LLM: hit@5 y MRR.")
    ap.add_argument("--sin-reranker", action="store_true")
    ap.add_argument("--sin-ragas", action="store_true", help="Omitir fidelidad y relevancia.")
    ap.add_argument("--umbral-hit5", type=float, help="Falla (código 1) si hit@5 es menor.")
    ap.add_argument("--etiqueta", default="", help="Nombre corto de la corrida.")
    ap.add_argument(
        "--reanudar", action="store_true", help="Continuar una corrida interrumpida del agente."
    )
    args = ap.parse_args(argv)

    preguntas = cargar_dataset(args.dataset, ids_del_corpus(RAIZ / "data" / "processed"))
    if args.limite:
        preguntas = preguntas[: args.limite]
    print(f"Dataset: {resumen_dataset(preguntas)}", file=sys.stderr)

    usar_reranker = not args.sin_reranker
    os.environ["RERANKER_ENABLED"] = "true" if usar_reranker else "false"
    from articulia.config import get_settings

    get_settings.cache_clear()

    filas, detalle_rec = evaluar_recuperacion(preguntas, usar_reranker)
    salidas: list[dict] = []
    if not args.solo_recuperacion:
        args.salida.mkdir(parents=True, exist_ok=True)
        progreso = args.salida / f"_progreso-{args.etiqueta or 'agente'}.jsonl"
        if not args.reanudar and progreso.exists():
            progreso.unlink()
        salidas = correr_agente(preguntas, progreso)
        filas += metricas_agente(salidas)
        if not args.sin_ragas:
            filas += metricas_ragas(salidas)

    fecha = datetime.now().strftime("%Y-%m-%d")
    s = get_settings()
    modo = "solo recuperación" if args.solo_recuperacion else f"{s.llm_provider}/{s.llm_model}"
    titulo = (
        f"Evaluación {fecha} · {len(preguntas)} preguntas · {modo} · "
        f"reranker {'sí' if usar_reranker else 'no'}"
    )
    tabla = tabla_markdown(filas, titulo)
    print(tabla)

    args.salida.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S") + (
        f"-{args.etiqueta}" if args.etiqueta else ""
    )
    (args.salida / f"{sello}.md").write_text(tabla + "\n", encoding="utf-8")
    (args.salida / f"{sello}.json").write_text(
        json.dumps(
            {
                "titulo": titulo,
                "metricas": [f.model_dump() for f in filas],
                "recuperacion": detalle_rec,
                "agente": [{k: v for k, v in x.items() if k != "textos"} for x in salidas],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nResultados en {args.salida / sello}.{{md,json}}", file=sys.stderr)

    hit5 = next(f.valor for f in filas if f.metrica == "Hit@5")
    if args.umbral_hit5 is not None and hit5 < args.umbral_hit5:
        print(f"hit@5 = {hit5:.2f} < umbral {args.umbral_hit5}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
