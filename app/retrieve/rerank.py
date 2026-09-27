from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Sequence

from app import config
from app.models import Chunk

TOKEN_RE = re.compile(r"[a-z0-9]+")
BM25_K1 = 1.5
BM25_B = 0.75
CROSS_ENCODER_CANDIDATES = (
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "cross-encoder/ms-marco-MiniLM-L-12-v2",
)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def lexical_document(chunk: Chunk) -> str:
    return " ".join(
        part
        for part in (
            chunk.section_title,
            chunk.heading_path,
            chunk.section_title,
            chunk.text,
        )
        if part
    )


class BM25:
    def __init__(
        self,
        documents: Sequence[Sequence[str]],
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.documents = [list(document) for document in documents]
        self.count = len(self.documents)
        self.lengths = [len(document) for document in self.documents]
        self.average_length = (
            sum(self.lengths) / self.count if self.count else 0.0
        )
        self.frequency: list[dict[str, int]] = []
        for document in self.documents:
            counts: dict[str, int] = {}
            for token in document:
                counts[token] = counts.get(token, 0) + 1
            self.frequency.append(counts)
        self.document_frequency: dict[str, int] = {}
        for counts in self.frequency:
            for token in counts:
                self.document_frequency[token] = self.document_frequency.get(token, 0) + 1

    def idf(self, token: str) -> float:
        seen = self.document_frequency.get(token, 0)
        return math.log(1 + (self.count - seen + 0.5) / (seen + 0.5))

    def scores(self, query_tokens: Sequence[str]) -> list[float]:
        if not self.count:
            return []
        results = [0.0] * self.count
        for token in query_tokens:
            weight = self.idf(token)
            if weight <= 0:
                continue
            for index, counts in enumerate(self.frequency):
                occurrences = counts.get(token, 0)
                if not occurrences:
                    continue
                length = self.lengths[index] or 1
                denominator = occurrences + self.k1 * (
                    1 - self.b + self.b * (length / (self.average_length or 1))
                )
                results[index] += weight * (occurrences * (self.k1 + 1)) / denominator
        return results


def lexical_backend() -> str:
    try:
        import rank_bm25  # noqa: F401
    except ImportError:
        return "builtin-bm25"
    return "rank_bm25"


def score_lexical(chunks: Sequence[Chunk], query: str) -> list[float]:
    documents = [tokenize(lexical_document(chunk)) for chunk in chunks]
    query_tokens = tokenize(query)
    if not query_tokens:
        return [0.0] * len(chunks)
    return BM25(documents).scores(query_tokens)


def numeric_density(text: str) -> float:
    tokens = tokenize(text)
    if not tokens:
        return 0.0
    numeric = sum(1 for token in tokens if any(character.isdigit() for character in token))
    return numeric / len(tokens)


def heading_overlap(query_tokens: Sequence[str], chunk: Chunk) -> float:
    if not query_tokens:
        return 0.0
    heading_tokens = set(tokenize(f"{chunk.section_title} {chunk.heading_path}"))
    if not heading_tokens:
        return 0.0
    hits = sum(1 for token in set(query_tokens) if token in heading_tokens)
    return hits / len(set(query_tokens))


def heuristic_score(
    query: str, chunk: Chunk, scheme_filter: str | None = None
) -> float:
    query_tokens = tokenize(query)
    heading = heading_overlap(query_tokens, chunk)
    scheme = 1.0 if scheme_filter and chunk.scheme_id == scheme_filter else 0.0
    density = min(numeric_density(chunk.text), 0.25) / 0.25
    return 0.5 * heading + 0.3 * scheme + 0.2 * density


def detect_cross_encoder(
    candidates: Sequence[str] = CROSS_ENCODER_CANDIDATES,
    cache_dir: Path | None = None,
) -> str | None:
    from app.index.embed import local_snapshot

    cache_dir = Path(cache_dir) if cache_dir else config.MODELS_DIR
    for model_id in candidates:
        if local_snapshot(model_id, cache_dir) is not None:
            return model_id
    return None


class CrossEncoderReranker:
    def __init__(self, model_id: str | None = None, cache_dir: Path | None = None) -> None:
        self.model_id = model_id or detect_cross_encoder(cache_dir=cache_dir)
        self._model: Any = None

    @property
    def available(self) -> bool:
        return self.model_id is not None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_id, device="cpu")
        return self._model

    def rerank(self, query: str, chunks: Sequence[Chunk]) -> list[float] | None:
        if not self.available or not chunks:
            return None
        try:
            model = self._load()
            pairs = [(query, chunk.text) for chunk in chunks]
            raw = model.predict(pairs)
        except Exception:
            return None
        return [float(value) for value in raw]
