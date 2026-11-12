"""Ingesta: `uv run python -m articulia.ingest [data/raw] [data/processed]`.

Convierte cada PDF a JSONL (un artículo por línea) e imprime un resumen para validar conteos.
"""

import sys
from collections import Counter
from pathlib import Path

from articulia.ingest.loader import load_pdf
from articulia.ingest.splitter import Article, split_law


def summarize(articles: list[Article]) -> dict[str, object]:
    """Resumen de una ley: conteos, duplicados y huecos en la numeración permanente."""
    perm = [a for a in articles if a.tipo == "articulo"]
    bases = {a.numero_base for a in perm if a.numero_base is not None}
    max_base = max(bases, default=0)
    dupes = [k for k, n in Counter(a.id for a in articles).items() if n > 1]
    return {
        "permanentes": len(perm),
        "con_numero_simple": sum(1 for a in perm if a.numero.isdigit()),
        "derogados": sum(1 for a in perm if a.derogado),
        "transitorios": len(articles) - len(perm),
        "ultimo": max_base,
        "huecos": sorted(set(range(1, max_base + 1)) - bases),
        "duplicados": dupes,
    }


def main(raw_dir: Path, out_dir: Path) -> int:
    """Procesa todos los PDFs de `raw_dir` y escribe `<ley>.jsonl` en `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(raw_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No hay PDFs en {raw_dir}")
        return 1
    ok = True
    print("| Ley | Permanentes | Núm. simples | Derogados | Transitorios | Último | Huecos | Dup |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    for pdf in pdfs:
        doc = load_pdf(pdf)
        articles = split_law(doc)
        with open(out_dir / f"{doc.clave}.jsonl", "w", encoding="utf-8") as f:
            for a in articles:
                f.write(a.model_dump_json() + "\n")
        s = summarize(articles)
        ok &= not s["huecos"] and not s["duplicados"]
        print(
            f"| {doc.clave} | {s['permanentes']} | {s['con_numero_simple']} | {s['derogados']} "
            f"| {s['transitorios']} | {s['ultimo']} | {s['huecos'] or '-'} "
            f"| {s['duplicados'] or '-'} |"
        )
    return 0 if ok else 2


if __name__ == "__main__":
    args = [Path(a) for a in sys.argv[1:]]
    raw = args[0] if args else Path("data/raw")
    out = args[1] if len(args) > 1 else Path("data/processed")
    sys.exit(main(raw, out))
