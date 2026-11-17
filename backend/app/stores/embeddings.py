"""Text embeddings, behind one interface so the provider can be swapped.

Anthropic does not offer an embedding model; its docs point to Voyage AI. Two providers:

  local  (default) BAAI/bge-small-en-v1.5 via fastembed. Runs on this machine: no key, works offline,
                   and document text never leaves the boundary.
  voyage           Voyage AI (e.g. voyage-finance-2 / voyage-4). Set EMBED_PROVIDER=voyage and
                   VOYAGE_API_KEY. Better retrieval quality, but text is sent to a third party, so in a
                   bank this needs data-protection approval (or a self-hosted model).

Queries and documents are embedded differently (both providers support this), which improves retrieval.
"""
from functools import lru_cache

import numpy as np

from app import config


def model_name() -> str:
    return config.VOYAGE_EMBED_MODEL if config.EMBED_PROVIDER == "voyage" else config.EMBED_MODEL


@lru_cache(maxsize=1)
def _local():
    from fastembed import TextEmbedding  # imported lazily: loading the model takes ~1s
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(config.EMBED_MODEL, cache_dir=str(config.MODELS_DIR))


@lru_cache(maxsize=1)
def _voyage():
    import voyageai  # only needed when EMBED_PROVIDER=voyage (uv add voyageai)
    return voyageai.Client()  # reads VOYAGE_API_KEY


def _as_arrays(vectors) -> list[np.ndarray]:
    return [np.asarray(v, dtype=np.float32) for v in vectors]


def embed_passages(texts: list[str]) -> list[np.ndarray]:
    if config.EMBED_PROVIDER == "voyage":
        return _as_arrays(_voyage().embed(texts, model=config.VOYAGE_EMBED_MODEL, input_type="document").embeddings)
    return _as_arrays(_local().passage_embed(texts))


@lru_cache(maxsize=4)
def _cross_encoder(name: str):
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return TextCrossEncoder(name, cache_dir=str(config.MODELS_DIR))


def rerank_scores(query: str, texts: list[str], model: str | None = None) -> list[float]:
    """Cross-encoder relevance: the model reads the question and each passage together (higher = more relevant)."""
    if not texts:
        return []
    return [float(s) for s in _cross_encoder(model or config.RERANK_MODEL).rerank(query, texts)]


def embed_query(text: str) -> np.ndarray:
    if config.EMBED_PROVIDER == "voyage":
        return _as_arrays(_voyage().embed([text], model=config.VOYAGE_EMBED_MODEL, input_type="query").embeddings)[0]
    return np.asarray(next(iter(_local().query_embed([text]))), dtype=np.float32)
