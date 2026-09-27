from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Sequence

import pytest

from app import config
from app.models import Chunk, ScoredChunk
from app.retrieve import rerank as rerank_module
from app.retrieve.retriever import (
    FLOOR_METRIC,
    HybridRetriever,
    RetrievalResult,
    Retriever,
    cosine_from_distance,
    match_scheme,
    rrf_fuse,
)

CORPUS_VERSION = "cv-test-0001"
RETRIEVED_AT = datetime(2026, 9, 25, 4, 0, tzinfo=timezone.utc)

S1_EXPENSE = Chunk(
    chunk_id="S1:0000",
    source_id="S1",
    scheme_id="S1",
    scheme_name="HDFC Large Cap Fund",
    category="Large Cap",
    section_title="Expenses",
    heading_path="HDFC Large Cap Fund > Direct Growth > Fees and Expenses",
    text=(
        "Expense ratio 1.56% of average daily assets. Direct plan expense ratio "
        "1.56%. TER 1.57%. Exit load 1.00%. Annual expense 0.15% for the Direct plan."
    ),
    ordinal=0,
    char_start=0,
    char_end=180,
    url="https://example.test/s1",
    retrieved_at=RETRIEVED_AT,
    authority="mirror",
    corpus_version=CORPUS_VERSION,
    document_date=date(2026, 9, 25),
)

S1_TAX = Chunk(
    chunk_id="S1:0001",
    source_id="S1",
    scheme_id="S1",
    scheme_name="HDFC Large Cap Fund",
    category="Large Cap",
    section_title="Taxation",
    heading_path="HDFC Large Cap Fund > Direct Growth > Tax",
    text=(
        "Section 80C benefits do not apply to this scheme. The investor may claim "
        "80C deduction on ELSS only, not on an equity large cap fund."
    ),
    ordinal=1,
    char_start=180,
    char_end=340,
    url="https://example.test/s1",
    retrieved_at=RETRIEVED_AT,
    authority="mirror",
    corpus_version=CORPUS_VERSION,
)

S2_EXPENSE = Chunk(
    chunk_id="S2:0000",
    source_id="S2",
    scheme_id="S2",
    scheme_name="HDFC Flexi Cap Fund",
    category="Flexi Cap",
    section_title="Expenses",
    heading_path="HDFC Flexi Cap Fund > Direct Growth > Fees and Expenses",
    text=(
        "Expense ratio 1.25% of average daily assets. Direct plan expense ratio "
        "1.25%. TER 1.28%. Exit load 1.00%."
    ),
    ordinal=0,
    char_start=0,
    char_end=160,
    url="https://example.test/s2",
    retrieved_at=RETRIEVED_AT,
    authority="mirror",
    corpus_version=CORPUS_VERSION,
)

S3_TIER = Chunk(
    chunk_id="S3:0000",
    source_id="S3",
    scheme_id="S3",
    scheme_name="HDFC Balanced Advantage Fund",
    category="Balanced Advantage",
    section_title="Direct Plan Tier 1",
    heading_path="HDFC Balanced Advantage Fund > Direct Growth > Plan Variants",
    text=(
        "Tier 1 direct growth plan expense ratio 0.65%. Tier 2 expense ratio 0.90%. "
        "Direct growth is available without a load."
    ),
    ordinal=0,
    char_start=0,
    char_end=170,
    url="https://example.test/s3",
    retrieved_at=RETRIEVED_AT,
    authority="mirror",
    corpus_version=CORPUS_VERSION,
)

FIXTURE_CHUNKS = [S1_EXPENSE, S1_TAX, S2_EXPENSE, S3_TIER]

QUERY_VECTORS: dict[str, list[float]] = {
    "expense ratio of HDFC Large Cap Fund": [1.0, 0.0, 0.0, 0.0],
    "HDFC": [1.0, 0.0, 0.0, 0.0],
    "HDFC Flexi Cap Fund": [0.9, 0.1, 0.0, 0.0],
    "expense ratio of HDFC Flexi Cap Fund": [0.9, 0.1, 0.0, 0.0],
    "80C deduction eligibility": [0.2, 0.95, 0.0, 0.0],
    "Tier 1 expense ratio": [0.0, 0.1, 0.2, 0.98],
    "quantum chromodynamics lattice gauge theory": [-1.0, -0.1, 0.0, 0.0],
}

CHUNK_VECTORS: dict[str, list[float]] = {
    "S1:0000": [0.98, 0.05, 0.0, 0.0],
    "S1:0001": [0.22, 0.94, 0.0, 0.0],
    "S2:0000": [0.90, 0.10, 0.0, 0.0],
    "S3:0000": [0.02, 0.10, 0.20, 0.97],
}


class StubEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        out = []
        for text in texts:
            try:
                out.append(list(QUERY_VECTORS[text]))
            except KeyError as error:
                raise AssertionError(f"unstubbed query: {text!r}") from error
        return out


class RecordingEmbedder:
    def __init__(self, vector: Sequence[float]) -> None:
        self.vector = list(vector)
        self.calls: list[list[str]] = []

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [list(self.vector) for _ in texts]


class StubStore:
    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = list(chunks)
        self.identity_calls = 0
        self.queries: list[tuple[list[float], int, dict[str, Any] | None]] = []
        self.corpus_version = CORPUS_VERSION

    def assert_model_identity(self) -> None:
        self.identity_calls += 1

    def query(
        self, vector: list[float], top_k: int, where: dict[str, Any] | None = None
    ) -> list[ScoredChunk]:
        self.queries.append((list(vector), top_k, where))
        pool = [
            chunk
            for chunk in self.chunks
            if where is None or chunk.scheme_id == where.get("scheme_id")
        ]
        scored = []
        for chunk in pool:
            similarity = _dot(chunk_vectors(chunk), vector)
            distance = 1.0 - similarity
            scored.append(
                ScoredChunk(chunk=chunk, rank=0, fused_score=0.0, cosine_score=similarity)
            )
        scored.sort(key=lambda item: -item.cosine_score)
        return scored[:top_k]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def chunk_vectors(chunk: Chunk) -> list[float]:
    return CHUNK_VECTORS[chunk.chunk_id]


class NullReranker:
    def __init__(self) -> None:
        self.model_id = None

    @property
    def available(self) -> bool:
        return False

    def rerank(self, query: str, chunks: Sequence[Chunk]) -> list[float] | None:
        return None


@pytest.fixture
def retriever() -> HybridRetriever:
    return HybridRetriever(
        store=StubStore(FIXTURE_CHUNKS),
        embedder=StubEmbedder(),
        reranker=NullReranker(),
    )


def test_retriever_protocol_is_satisfied(retriever: HybridRetriever) -> None:
    assert isinstance(retriever, Retriever)


def test_assert_model_identity_runs_on_every_retrieve(retriever: HybridRetriever) -> None:
    for _ in range(3):
        retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert retriever.store.identity_calls == 3


def test_candidate_pool_uses_top_k_fetch(retriever: HybridRetriever) -> None:
    retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    _, top_k, _ = retriever.store.queries[-1]
    assert top_k == config.TOP_K_FETCH == 20


def test_scheme_named_query_applies_scheme_filter(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert result.scheme_filter == "S1"
    _, _, where = retriever.store.queries[-1]
    assert where == {"scheme_id": "S1"}
    assert result.passed_floor is True
    assert {item.chunk.scheme_id for item in result.chunks} == {"S1"}


def test_scheme_filter_uses_alias_match(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("expense ratio of HDFC Flexi Cap Fund")
    assert result.scheme_filter == "S2"
    assert result.chunks[0].chunk_id == "S2:0000"


def test_ambiguous_scheme_returns_none_from_match_scheme() -> None:
    assert match_scheme("HDFC") is None
    assert match_scheme("tell me about HDFC") is None
    assert match_scheme("HDFC Large Cap Fund") == "S1"
    assert match_scheme("HDFC Flexi Cap Fund") == "S2"


def test_ambiguous_scheme_query_applies_no_filter(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("HDFC")
    assert result.scheme_filter is None
    _, _, where = retriever.store.queries[-1]
    assert where is None
    assert len({item.chunk.scheme_id for item in result.chunks}) > 1


def test_comparative_query_naming_two_schemes_is_not_pinned() -> None:
    assert match_scheme("HDFC Large Cap Fund versus HDFC Flexi Cap Fund") is None


def test_unrelated_query_applies_no_scheme_filter(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("quantum chromodynamics lattice gauge theory")
    assert result.scheme_filter is None
    _, _, where = retriever.store.queries[-1]
    assert where is None


def test_off_corpus_query_fails_the_floor(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("quantum chromodynamics lattice gauge theory")
    assert result.best_score < result.floor
    assert result.passed_floor is False
    assert result.chunks == []
    assert result.nearest


def test_on_corpus_query_passes_the_floor(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert result.best_score >= result.floor
    assert result.passed_floor is True
    assert result.chunks
    assert result.chunks[0].rank == 1


def test_exact_token_query_retrieves_the_right_section(
    retriever: HybridRetriever,
) -> None:
    result = retriever.retrieve("80C deduction eligibility")
    assert result.passed_floor is True
    assert result.chunks[0].chunk_id == "S1:0001"
    assert "80C" in result.chunks[0].chunk.text
    assert result.chunks[0].lexical_score > 0.0


def test_exact_token_tier_query_retrieves_the_right_section(
    retriever: HybridRetriever,
) -> None:
    result = retriever.retrieve("Tier 1 expense ratio")
    assert result.chunks[0].chunk_id == "S3:0000"
    assert result.chunks[0].lexical_score > 0.0


def test_cosine_distance_to_similarity_conversion() -> None:
    assert cosine_from_distance(0.0) == pytest.approx(1.0)
    assert cosine_from_distance(0.25) == pytest.approx(0.75)
    assert cosine_from_distance(1.0) == pytest.approx(0.0)
    assert cosine_from_distance(2.0) == pytest.approx(-1.0)


def test_store_distance_is_converted_to_similarity(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert result.best_score == pytest.approx(0.98, abs=1e-6)
    assert all(0.0 < item.cosine_score <= 1.0001 for item in result.chunks)


def test_rrf_fuse_hand_computed_example() -> None:
    cosine_ranking = ["A", "B", "C"]
    lexical_ranking = ["C", "A", "D"]
    fused = rrf_fuse([cosine_ranking, lexical_ranking], 60)
    assert fused["A"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["B"] == pytest.approx(1 / 62)
    assert fused["C"] == pytest.approx(1 / 63 + 1 / 61)
    assert fused["D"] == pytest.approx(1 / 63)
    assert fused["A"] == pytest.approx(0.0325225, abs=1e-6)
    assert fused["C"] == pytest.approx(0.0322663, abs=1e-6)
    assert [key for key, _ in sorted(fused.items(), key=lambda kv: -kv[1])] == [
        "A",
        "C",
        "B",
        "D",
    ]


def test_rrf_fuse_single_ranking_matches_definition() -> None:
    fused = rrf_fuse([["X", "Y", "Z"]], 60)
    assert fused["X"] == pytest.approx(1 / 61)
    assert fused["Y"] == pytest.approx(1 / 62)
    assert fused["Z"] == pytest.approx(1 / 63)


def test_rrf_fuse_uses_config_rrf_k_of_60(retriever: HybridRetriever) -> None:
    assert retriever.rrf_k == config.RRF_K == 60
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert all(item.fused_score > 0.0 for item in result.chunks)
    assert max(item.fused_score for item in result.chunks) == pytest.approx(2 / 61)


def test_every_scored_chunk_carries_all_score_fields(
    retriever: HybridRetriever,
) -> None:
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert result.chunks
    for item in result.chunks:
        for field in (
            "rank",
            "chunk_id",
            "fused_score",
            "cosine_score",
            "lexical_score",
            "rerank_score",
            "best_score",
        ):
            assert hasattr(item, field), field
        assert item.rank >= 1
        assert item.chunk_id
        assert isinstance(item.fused_score, float)
        assert isinstance(item.cosine_score, float)
        assert isinstance(item.lexical_score, float)
        assert isinstance(item.rerank_score, float)
        assert isinstance(item.best_score, float)
        assert item.rerank_score > 0.0


def test_scores_survive_a_floor_rejection(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("quantum chromodynamics lattice gauge theory")
    assert result.passed_floor is False
    assert result.chunks == []
    assert result.nearest
    for item in result.nearest:
        assert item.fused_score > 0.0
        assert item.lexical_score >= 0.0
        assert item.rerank_score >= 0.0
        assert item.best_score >= 0.0
        assert item.rank >= 1


def test_ranks_are_dense_and_ordered(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("HDFC")
    ranks = [item.rank for item in result.chunks]
    assert ranks == list(range(1, len(ranks) + 1))
    best = [item.best_score for item in result.chunks]
    assert best == sorted(best, reverse=True)


def test_top_k_limits_returned_chunks(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("HDFC", top_k=2)
    assert len(result.chunks) <= 2
    assert retriever.top_k == config.TOP_K == 5


def test_cross_encoder_is_skipped_silently_when_absent(
    retriever: HybridRetriever,
) -> None:
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert result.reranked is False
    assert result.reranker == "heuristic"
    assert all(item.rerank_score > 0.0 for item in result.chunks)


def test_heuristic_rerank_prefers_matching_heading() -> None:
    heading = rerank_module.heuristic_score(
        "expense ratio of HDFC Large Cap Fund", S1_EXPENSE, "S1"
    )
    other = rerank_module.heuristic_score("expense ratio", S1_TAX, "S1")
    assert heading > other


def test_detect_cross_encoder_returns_none_without_local_model(
    tmp_path: Any,
) -> None:
    assert rerank_module.detect_cross_encoder(cache_dir=tmp_path) is None


def test_cross_encoder_reranker_reports_unavailable(tmp_path: Any) -> None:
    reranker = rerank_module.CrossEncoderReranker(cache_dir=tmp_path)
    assert reranker.available is False
    assert reranker.rerank("query", [S1_EXPENSE]) is None


def test_pii_in_query_is_scrubbed_before_embedding() -> None:
    store = StubStore(FIXTURE_CHUNKS)
    embedder = RecordingEmbedder([1.0, 0.0, 0.0, 0.0])
    retriever = HybridRetriever(store=store, embedder=embedder, reranker=NullReranker())
    result = retriever.retrieve(
        "My PAN is ABCDE1234F, expense ratio of HDFC Large Cap Fund"
    )
    assert result.pii_detected is True
    assert embedder.calls[-1] == [
        "My PAN is [REDACTED:pan], expense ratio of HDFC Large Cap Fund"
    ]
    assert result.query == embedder.calls[-1][0]
    assert "ABCDE1234F" not in result.query
    assert result.scheme_filter == "S1"


def test_clean_query_is_embedded_verbatim() -> None:
    embedder = RecordingEmbedder([1.0, 0.0, 0.0, 0.0])
    store = StubStore(FIXTURE_CHUNKS)
    retriever = HybridRetriever(store=store, embedder=embedder, reranker=NullReranker())
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert embedder.calls[-1] == ["expense ratio of HDFC Large Cap Fund"]
    assert result.pii_detected is False
    assert result.passed_floor is True


def test_builtin_bm25_ranks_exact_token_first() -> None:
    chunks = [S1_EXPENSE, S1_TAX, S2_EXPENSE, S3_TIER]
    scores = rerank_module.score_lexical(chunks, "80C deduction")
    assert scores[chunks.index(S1_TAX)] > scores[chunks.index(S1_EXPENSE)]


def test_bm25_returns_zeros_for_empty_query() -> None:
    chunks = [S1_EXPENSE, S1_TAX]
    assert rerank_module.score_lexical(chunks, "") == [0.0, 0.0]
    assert rerank_module.score_lexical([], "80C") == []


def test_tokenize_keeps_exact_alphanumeric_tokens() -> None:
    assert rerank_module.tokenize("Is 80C allowed in Tier 1?") == [
        "is",
        "80c",
        "allowed",
        "in",
        "tier",
        "1",
    ]


def test_numeric_density_counts_numeric_tokens() -> None:
    assert rerank_module.numeric_density("1.56% and 2") == pytest.approx(3 / 4)
    assert rerank_module.numeric_density("80C benefits apply") == pytest.approx(1 / 3)
    assert rerank_module.numeric_density("no digits here") == 0.0
    assert rerank_module.numeric_density("") == 0.0


def test_lexical_backend_reports_a_known_name() -> None:
    assert rerank_module.lexical_backend() in {"builtin-bm25", "rank_bm25"}


def test_result_floor_metric_is_cosine_similarity() -> None:
    assert FLOOR_METRIC == "cosine_similarity"


def test_floor_is_config_default(retriever: HybridRetriever) -> None:
    result = retriever.retrieve("expense ratio of HDFC Large Cap Fund")
    assert result.floor == config.SIMILARITY_FLOOR == 0.3


def test_retrieval_result_defaults_are_safe() -> None:
    result = RetrievalResult(query="q")
    assert result.passed_floor is False
    assert result.chunks == []
    assert result.to_trace() == []


def test_empty_query_fails_the_floor(retriever: HybridRetriever) -> None:
    embedder = StubEmbedder()
    embedder.encode = lambda texts: [[0.0, 0.0, 0.0, 0.0] for _ in texts]
    retriever._embedder = embedder
    result = retriever.retrieve("")
    assert result.passed_floor is False
    assert result.chunks == []


def test_real_chroma_store_integration(tmp_path: Any) -> None:
    from app.index.store import ChromaStore

    store = ChromaStore(
        corpus_version=CORPUS_VERSION,
        collection_name="test_retriever",
        path=tmp_path,
    )
    store.assert_model_identity()
    vectors = [CHUNK_VECTORS[chunk.chunk_id] for chunk in FIXTURE_CHUNKS]
    assert store.upsert(list(FIXTURE_CHUNKS), vectors) == len(FIXTURE_CHUNKS)

    class LookupEmbedder:
        def encode(self, texts: Sequence[str]) -> list[list[float]]:
            return [QUERY_VECTORS[texts[0]]]

    retriever = HybridRetriever(store=store, embedder=LookupEmbedder(), reranker=NullReranker())
    result = retriever.retrieve("80C deduction eligibility")
    assert result.scheme_filter is None
    assert result.passed_floor is True
    assert result.chunks[0].chunk_id == "S1:0001"
    assert all(item.cosine_score > 0 for item in result.chunks)
    assert all(item.chunk_id for item in result.chunks)


def test_real_chroma_store_scheme_filter(tmp_path: Any) -> None:
    from app.index.store import ChromaStore

    store = ChromaStore(
        corpus_version=CORPUS_VERSION,
        collection_name="test_retriever_filter",
        path=tmp_path,
    )
    vectors = [CHUNK_VECTORS[chunk.chunk_id] for chunk in FIXTURE_CHUNKS]
    store.upsert(list(FIXTURE_CHUNKS), vectors)

    class LookupEmbedder:
        def encode(self, texts: Sequence[str]) -> list[list[float]]:
            return [QUERY_VECTORS[texts[0]]]

    retriever = HybridRetriever(store=store, embedder=LookupEmbedder(), reranker=NullReranker())
    result = retriever.retrieve("expense ratio of HDFC Flexi Cap Fund")
    assert result.scheme_filter == "S2"
    assert {item.chunk.scheme_id for item in result.chunks} == {"S2"}


def test_query_cli_json_output(retriever: HybridRetriever, monkeypatch: Any, capsys: Any) -> None:
    from scripts import query as query_module

    monkeypatch.setattr(query_module, "HybridRetriever", lambda *a, **k: retriever)
    exit_code = query_module.main(
        ["expense ratio of HDFC Large Cap Fund", "--json", "--debug"]
    )
    assert exit_code == 0
    payload = capsys.readouterr().out
    assert '"passed_floor": true' in payload
    assert '"scheme_filter": "S1"' in payload
    assert '"cosine_similarity"' in payload


def test_query_cli_reports_floor_failure(retriever: HybridRetriever, monkeypatch: Any) -> None:
    from scripts import query as query_module

    monkeypatch.setattr(query_module, "HybridRetriever", lambda *a, **k: retriever)
    exit_code = query_module.main(["quantum chromodynamics lattice gauge theory"])
    assert exit_code == 1
