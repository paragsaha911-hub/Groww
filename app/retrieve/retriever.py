from __future__ import annotations

import re
import unicodedata
from typing import Any, Protocol, Sequence, runtime_checkable

from app import config
from app.guardrails.pii import scan as pii_scan
from app.guardrails.pii import scrub as pii_scrub
from app.index.embed import MiniLMEmbedder
from app.index.store import ChromaStore
from app.models import Chunk, RetrievalResult, ScoredChunk
from app.retrieve.rerank import (
    CrossEncoderReranker,
    heuristic_score,
    lexical_backend,
    score_lexical,
    tokenize,
)

FLOOR_METRIC = "cosine_similarity"
TIEBREAK_WEIGHT = 0.001


@runtime_checkable
class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int | None = None) -> RetrievalResult: ...


def normalise(text: str) -> str:
    cleaned = unicodedata.normalize("NFKD", text or "").lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def scheme_aliases(scheme_id: str) -> list[str]:
    scheme = config.scheme_by_id(scheme_id)
    aliases = [scheme.name] if scheme else []
    aliases.extend(config.SCHEME_NAME_ALIASES.get(scheme_id, ()))
    if scheme is not None and scheme.category:
        aliases.append(f"{scheme.category} {scheme.name}".strip())
    seen: list[str] = []
    for alias in aliases:
        key = normalise(alias)
        if key and key not in seen:
            seen.append(key)
    return seen


def match_scheme(query: str) -> str | None:
    haystack = normalise(query)
    if not haystack:
        return None
    padded = f" {haystack} "
    hits: list[str] = []
    for scheme in config.SCHEMES:
        for alias in scheme_aliases(scheme.scheme_id):
            if f" {alias} " in padded and scheme.scheme_id not in hits:
                hits.append(scheme.scheme_id)
    if len(hits) == 1:
        return hits[0]
    return None


def cosine_from_distance(distance: float) -> float:
    return 1.0 - float(distance)


def ranks_from_scores(scores: Sequence[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    ranks = [0] * len(scores)
    for position, index in enumerate(order, start=1):
        ranks[index] = position
    return ranks


def rrf_fuse(rankings: Sequence[Sequence[str]], k: int) -> dict[str, float]:
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + position)
    return fused


class HybridRetriever:
    def __init__(
        self,
        store: Any = None,
        embedder: Any = None,
        reranker: Any = None,
        top_k_fetch: int | None = None,
        top_k: int | None = None,
        rrf_k: int | None = None,
        similarity_floor: float | None = None,
    ) -> None:
        self.store = store if store is not None else ChromaStore()
        self._embedder = embedder
        self.reranker = reranker if reranker is not None else CrossEncoderReranker()
        self.top_k_fetch = top_k_fetch or config.TOP_K_FETCH
        self.top_k = top_k or config.TOP_K
        self.rrf_k = rrf_k or config.RRF_K
        self.similarity_floor = (
            config.SIMILARITY_FLOOR if similarity_floor is None else similarity_floor
        )

    @property
    def embedder(self) -> Any:
        if self._embedder is None:
            self._embedder = MiniLMEmbedder(
                corpus_version=getattr(self.store, "corpus_version", config.corpus_version())
            )
        return self._embedder

    def embed_query(self, query: str) -> list[float]:
        return self.embedder.encode([query])[0]

    def fetch_candidates(self, vector: list[float], scheme_id: str | None) -> list[ScoredChunk]:
        where = {"scheme_id": scheme_id} if scheme_id else None
        return list(self.store.query(vector, top_k=self.top_k_fetch, where=where))

    def lexical_rankings(
        self, candidates: Sequence[ScoredChunk], query: str
    ) -> tuple[dict[str, float], list[str]]:
        lexical = score_lexical([item.chunk for item in candidates], query)
        scores = {item.chunk_id: float(score) for item, score in zip(candidates, lexical)}
        order = sorted(
            range(len(candidates)),
            key=lambda index: (-lexical[index], candidates[index].chunk_id),
        )
        return scores, [candidates[index].chunk_id for index in order]

    def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], scheme_id: str | None, top_k: int
    ) -> tuple[list[ScoredChunk], bool, str]:
        chosen = list(candidates[:top_k])
        if not chosen:
            return [], False, "none"
        cross = self.reranker.rerank(query, [item.chunk for item in chosen])
        if cross is None:
            scores = [heuristic_score(query, item.chunk, scheme_id) for item in chosen]
            backend = "heuristic"
        else:
            scores = list(cross)
            backend = f"cross-encoder:{self.reranker.model_id}"
        for item, score in zip(chosen, scores):
            item.rerank_score = float(score)
        return chosen, cross is not None, backend

    def final_score(self, item: ScoredChunk, ceiling: float) -> float:
        normalised = item.fused_score / ceiling if ceiling > 0 else 0.0
        return normalised + TIEBREAK_WEIGHT * item.rerank_score

    def retrieve(self, query: str, top_k: int | None = None) -> RetrievalResult:
        limit = top_k or self.top_k
        self.store.assert_model_identity()

        raw_query = query or ""
        pii = pii_scan(raw_query)
        safe_query = pii_scrub(raw_query)

        scheme_id = match_scheme(safe_query)
        vector = self.embed_query(safe_query)
        candidates = self.fetch_candidates(vector, scheme_id)

        result = RetrievalResult(
            query=safe_query,
            floor=self.similarity_floor,
            scheme_filter=scheme_id,
            candidates=list(candidates),
            lexical_backend=lexical_backend(),
            pii_detected=pii.has_pii,
        )
        if not candidates:
            return result

        cosine_scores = {item.chunk_id: item.cosine_score for item in candidates}
        cosine_order = [
            item.chunk_id
            for item in sorted(
                candidates, key=lambda item: (-item.cosine_score, item.chunk_id)
            )
        ]
        lexical_scores, lexical_order = self.lexical_rankings(candidates, safe_query)
        fused = rrf_fuse([cosine_order, lexical_order], self.rrf_k)

        for item in candidates:
            item.fused_score = fused.get(item.chunk_id, 0.0)
            item.lexical_score = lexical_scores.get(item.chunk_id, 0.0)
            item.rerank_score = 0.0
            item.best_score = item.fused_score

        ranked, reranked, reranker_name = self.rerank(
            safe_query, candidates, scheme_id, limit
        )

        ceiling = 2.0 / (self.rrf_k + 1)
        for item in ranked:
            item.best_score = self.final_score(item, ceiling)
        ranked.sort(key=lambda item: (-item.best_score, item.chunk_id))
        for position, item in enumerate(ranked, start=1):
            item.rank = position

        result.best_score = max(cosine_scores.values(), default=0.0)
        result.reranked = reranked
        result.reranker = reranker_name
        result.nearest = list(ranked)

        if result.best_score < self.similarity_floor:
            result.passed_floor = False
            return result

        result.passed_floor = True
        result.chunks = ranked
        return result
