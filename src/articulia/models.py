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


@lru_cache
def get_reranker() -> CrossEncoder:
    """Cross-encoder para reordenar candidatos (bge-reranker-v2-m3)."""
    return CrossEncoder(get_settings().reranker_model, max_length=MAX_TOKENS, device="cpu")


def embed(texts: list[str], batch_size: int = 16) -> np.ndarray:
    """Embeddings normalizados (norma 1), listos para distancia coseno."""
    return get_embedder().encode(
        texts, batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True
    )
