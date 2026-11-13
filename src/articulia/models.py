"""Carga perezosa y cacheada de los modelos locales (embeddings y reranker)."""

from functools import lru_cache

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from articulia.config import get_settings

EMBEDDING_DIM = 1024
MAX_TOKENS = 512


@lru_cache
def get_embedder() -> SentenceTransformer:
    """Modelo de embeddings (bge-m3), cargado una sola vez por proceso."""
    model = SentenceTransformer(get_settings().embedding_model, device="cpu")
    model.max_seq_length = MAX_TOKENS
    return model


def _cross_encoder(modelo: str, int8: bool) -> CrossEncoder:
    ce = CrossEncoder(modelo, max_length=get_settings().rerank_max_length, device="cpu")
    if int8:
        import torch

        # Cuantización dinámica de las capas lineales: menos tiempo en CPU con casi la misma
        # calidad (medido en eval/bench_reranker.py).
        torch.quantization.quantize_dynamic(ce, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
    return ce


@lru_cache
def get_reranker() -> CrossEncoder:
    """Cross-encoder principal para reordenar candidatos (bge-reranker-v2-m3)."""
    s = get_settings()
    return _cross_encoder(s.reranker_model, s.reranker_int8)


@lru_cache
def get_prefilter() -> CrossEncoder | None:
    """Cross-encoder ligero que recorta candidatos antes del principal (None si está apagado)."""
    s = get_settings()
    return _cross_encoder(s.rerank_prefilter_model, False) if s.rerank_prefilter_model else None


def embed(texts: list[str], batch_size: int = 16) -> np.ndarray:
    """Embeddings normalizados (norma 1), listos para distancia coseno."""
    return get_embedder().encode(
        texts, batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True
    )
