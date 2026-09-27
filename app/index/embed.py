from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np

from app import config

os.environ.setdefault("HF_HOME", str(config.MODELS_DIR))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(config.MODELS_DIR))
os.environ.setdefault("TRANSFORMERS_CACHE", str(config.MODELS_DIR))


@runtime_checkable
class Embedder(Protocol):
    model_id: str
    dim: int

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class DimensionMismatchError(ValueError):
    pass


def cache_key(corpus_version: str, model_id: str, text: str) -> str:
    return sha256(f"{corpus_version}|{model_id}|{text}".encode("utf-8")).hexdigest()


def local_snapshot(model_id: str, cache_dir: Path) -> Path | None:
    candidates = (
        cache_dir / f"models--{model_id.replace('/', '--')}",
        cache_dir / model_id.rsplit("/", 1)[-1],
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def load_sentence_transformer(model_id: str, cache_dir: Path | None = None) -> Any:
    cache_dir = Path(cache_dir) if cache_dir else config.MODELS_DIR
    cached = local_snapshot(model_id, cache_dir) is not None
    if cached:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        model_id,
        cache_folder=str(cache_dir),
        local_files_only=cached,
        device="cpu",
    )


class MiniLMEmbedder:
    def __init__(
        self,
        corpus_version: str,
        model_id: str | None = None,
        batch_size: int | None = None,
        expected_dim: int | None = None,
        cache_dir: Path | None = None,
        encoder: Callable[[list[str]], Any] | None = None,
    ) -> None:
        self.corpus_version = corpus_version
        self.model_id = model_id or config.EMBED_MODEL
        self.batch_size = batch_size or config.EMBED_BATCH_SIZE
        self.dim = expected_dim or config.EMBED_DIM
        self.cache_dir = Path(cache_dir) if cache_dir else config.EMBEDDING_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._encoder = encoder
        self._model: Any = None

    @property
    def encoder(self) -> Callable[[list[str]], Any]:
        if self._encoder is None:
            if self._model is None:
                self._model = load_sentence_transformer(self.model_id)
            self._encoder = self._model.encode
        return self._encoder

    def _cache_path(self, text: str) -> Path:
        return self.cache_dir / f"{cache_key(self.corpus_version, self.model_id, text)}.npy"

    def _cached(self, text: str) -> list[float] | None:
        path = self._cache_path(text)
        if not path.is_file():
            return None
        try:
            vector = np.load(path)
        except (ValueError, OSError):
            return None
        if vector.shape != (self.dim,):
            path.unlink(missing_ok=True)
            return None
        return [float(value) for value in vector]

    def _store(self, text: str, vector: list[float]) -> None:
        np.save(self._cache_path(text), np.asarray(vector, dtype=np.float32))

    def _check_dim(self, vectors: Any) -> np.ndarray:
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.ndim != 2:
            raise ValueError(f"encoder returned shape {array.shape}; expected 2-D")
        if array.shape[1] != self.dim:
            raise DimensionMismatchError(
                f"embedding dimension mismatch: expected {self.dim}, got {array.shape[1]}. "
                f"Model {self.model_id!r} does not match config.EMBED_DIM; re-index required."
            )
        return array

    @staticmethod
    def _normalise(array: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return array / norms

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        for text in texts:
            if not isinstance(text, str):
                raise TypeError(f"expected str to embed, got {type(text).__name__}")

        results: list[list[float] | None] = [None] * len(texts)
        pending: dict[str, list[int]] = {}
        for index, text in enumerate(texts):
            cached = self._cached(text)
            if cached is not None:
                results[index] = cached
            else:
                pending.setdefault(text, []).append(index)

        pending_texts = list(pending)
        if pending_texts:
            order = sorted(range(len(pending_texts)), key=lambda i: len(pending_texts[i]))
            encode = self.encoder
            for offset in range(0, len(order), self.batch_size):
                window = order[offset : offset + self.batch_size]
                batch = [pending_texts[i] for i in window]
                vectors = self._normalise(self._check_dim(encode(batch)))
                for position, index in enumerate(window):
                    vector = [float(value) for value in vectors[position]]
                    self._store(pending_texts[index], vector)
                    for target in pending[pending_texts[index]]:
                        results[target] = vector

        missing = [index for index, value in enumerate(results) if value is None]
        if missing:
            raise RuntimeError(f"no vector produced for input indices {missing[:5]}")
        return [value for value in results if value is not None]


def model_identity(model_id: str | None = None, dim: int | None = None) -> dict[str, Any]:
    return {
        "model_id": model_id or config.EMBED_MODEL,
        "dim": dim or config.EMBED_DIM,
    }
