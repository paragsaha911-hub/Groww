from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from app import config

DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBED_DIM = 384


def model_identity(model_id: str = DEFAULT_MODEL_ID, dim: int = DEFAULT_EMBED_DIM) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "dim": dim,
    }


def local_snapshot(model_id: str, cache_dir: Path | str | None = None) -> Path | None:
    cache_path = Path(cache_dir) if cache_dir else config.MODELS_DIR
    target = cache_path / model_id.replace("/", "--")
    if target.exists():
        return target
    return None


class Embedder:
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Path | str | None = None,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else config.MODELS_DIR
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir) if self.cache_dir else None,
            )
        return self._model

    def encode(self, texts: Sequence[str] | str) -> list[list[float]] | list[float]:
        if isinstance(texts, str):
            return self.embed_query(texts)
        if not texts:
            return []
        model = self._load()
        embeddings = model.embed(list(texts))
        return [list(vector) for vector in embeddings]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self.encode(texts)  # type: ignore

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        embeddings = list(model.embed([text or ""]))
        return list(embeddings[0])


class MiniLMEmbedder(Embedder):
    """Drop-in lightweight FastEmbed implementation satisfying legacy MiniLMEmbedder imports."""
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Path | str | None = None,
    ) -> None:
        super().__init__(model_name=model_name, cache_dir=cache_dir)


_default_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return _default_embedder


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    return get_embedder().encode(texts)  # type: ignore


def embed_query(text: str) -> list[float]:
    return get_embedder().embed_query(text)