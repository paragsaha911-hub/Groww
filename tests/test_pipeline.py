from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import pipeline
from app.models import (
    AUTHORITY_MIRROR,
    AUTHORITY_OFFICIAL,
    Chunk,
    QueryResult,
    RetrievalResult,
    ScoredChunk,
)

BASE = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)


def make_chunk(
    source_id: str = "groww_large_cap",
    scheme_id: str = "S1",
    section_title: str = "Fees",
    text: str = "Direct growth expense ratio is 1.12%.",
    authority: str = AUTHORITY_MIRROR,
    retrieved_at: datetime = BASE,
) -> Chunk:
    return Chunk(
        chunk_id=f"{source_id}#{section_title}",
        source_id=source_id,
        scheme_id=scheme_id,
        scheme_name="HDFC Large Cap Fund",
        category="Large Cap",
        section_title=section_title,
        heading_path=f"{section_title}",
        text=text,
        ordinal=0,
        char_start=0,
        char_end=len(text),
        url="https://groww.in/funds/hdfc-large-cap-fund",
        retrieved_at=retrieved_at,
        authority=authority,
        corpus_version="test-version",
        page=None,
        token_count=12,
        document_date=datetime(2026, 6, 30, tzinfo=timezone.utc).date(),
    )


def scored(chunk: Chunk, rank: int = 1, best: float = 0.72) -> ScoredChunk:
    return ScoredChunk(
        chunk=chunk,
        rank=rank,
        fused_score=best,
        cosine_score=best,
        lexical_score=0.4,
        rerank_score=best,
        best_score=best,
    )


def make_result(
    passed_floor: bool = True,
    chunks: list[Chunk] | None = None,
    nearest: Chunk | None = None,
) -> RetrievalResult:
    chosen = chunks if chunks is not None else [make_chunk()]
    candidates = [scored(chunk, rank=index + 1) for index, chunk in enumerate(chosen)]
    return RetrievalResult(
        query="q",
        intent="factual",
        candidates=candidates,
        chunks=[item.chunk for item in candidates],
        best_score=candidates[0].best_score if candidates else 0.0,
        floor=0.3,
        passed_floor=passed_floor,
        scheme_filter=None,
        reranked=False,
        reranker="none",
        lexical_backend="none",
        pii_detected=[],
        nearest=nearest,
    )


class FakeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None) -> RetrievalResult:
        self.calls.append((query, top_k))
        return self.result


class FakeAnswerer:
    name = "fake"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    def generate(self, system: str, user: str) -> str:
        self.calls += 1
        return self.answer


@pytest.fixture()
def traces(tmp_path: Path) -> Path:
    return tmp_path / "traces.jsonl"


def read_traces(traces: Path) -> list[dict]:
    if not traces.exists():
        return []
    return [json.loads(line) for line in traces.read_text(encoding="utf-8").splitlines() if line]


FACTUAL_ANSWER = (
    "The direct growth expense ratio of HDFC Large Cap Fund is 1.12%.\n"
    "SOURCE_ID:groww_large_cap"
)
ADVICE_ANSWER = (
    "There is no exit load on HDFC ELSS Tax Saver Fund after three years.\n"
    "SOURCE_ID:groww_large_cap"
)


def test_pii_query_refuses_before_retrieval(traces: Path) -> None:
    retriever = FakeRetriever(make_result())
    result = pipeline.answer_question(
        "my PAN is ABCDE1234F, what is the expense ratio?",
        retriever=retriever,
        traces_path=traces,
    )
    assert result.refused is True
    assert result.refusal_kind == "npi"
    assert retriever.calls == []
    assert len(read_traces(traces)) == 1


def test_pan_is_detected_and_recorded(traces: Path) -> None:
    result = pipeline.answer_question(
        "PAN ABCDE1234F", retriever=FakeRetriever(make_result()), traces_path=traces
    )
    record = read_traces(traces)[0]
    assert "pan" in record["pii_detected"]
    assert result.refusal_kind == "npi"


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("Should I buy HDFC Small Cap Fund?", "advice"),
        ("which of these grew most last year?", "performance"),
        ("what is the weather in mumbai tomorrow?", "out_of_scope"),
    ],
)
def test_intent_refusals_skip_retrieval(query: str, kind: str, traces: Path) -> None:
    retriever = FakeRetriever(make_result())
    result = pipeline.answer_question(query, retriever=retriever, traces_path=traces)
    assert result.refused is True
    assert result.refusal_kind == kind
    assert result.intent == kind
    assert retriever.calls == []


def test_advice_refusal_carries_educational_link(traces: Path) -> None:
    result = pipeline.answer_question(
        "Should I buy HDFC Small Cap Fund?",
        retriever=FakeRetriever(make_result()),
        traces_path=traces,
    )
    assert pipeline.EDUCATIONAL_URL in result.answer


def test_performance_refusal_carries_factsheet_link(traces: Path) -> None:
    result = pipeline.answer_question(
        "what is the 1-year return?",
        retriever=FakeRetriever(make_result()),
        traces_path=traces,
    )
    assert config_factsheet() in result.answer


def config_factsheet() -> str:
    from app import config

    return config.OFFICIAL_FACTSHEET_URL


def test_out_of_scope_refusal_carries_sources_link(traces: Path) -> None:
    result = pipeline.answer_question(
        "tell me about SBI Bluechip Fund",
        retriever=FakeRetriever(make_result()),
        traces_path=traces,
    )
    assert pipeline.SOURCES_URL in result.answer


def test_floor_failure_returns_not_found_with_nearest_sections(traces: Path) -> None:
    nearest = make_chunk(section_title="Contact")
    retriever = FakeRetriever(
        make_result(passed_floor=False, chunks=[], nearest=nearest)
    )
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=retriever,
        traces_path=traces,
    )
    assert result.refused is True
    assert result.refusal_kind == "not_found"
    assert "Contact" in result.answer
    assert "expense ratio" in result.answer


def test_empty_retrieval_is_not_found(traces: Path) -> None:
    retriever = FakeRetriever(make_result(passed_floor=False, chunks=[]))
    result = pipeline.answer_question(
        "What is the benchmark of HDFC Flexi Cap Fund?",
        retriever=retriever,
        traces_path=traces,
    )
    assert result.refusal_kind == "not_found"
    assert "none" in result.answer


def test_successful_answer_carries_citation_and_freshness(traces: Path) -> None:
    retriever = FakeRetriever(make_result())
    answerer = FakeAnswerer(FACTUAL_ANSWER)
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=retriever,
        answerer=answerer,
        traces_path=traces,
    )
    assert result.refused is False
    assert result.intent == "factual"
    assert len(result.citations) == 1
    assert result.citations[0].source_id == "groww_large_cap"
    assert result.freshness_date == BASE.date()
    assert result.authority == AUTHORITY_MIRROR
    assert result.latency_ms >= 0
    assert answerer.calls == 1


def test_retriever_receives_the_scrubbed_query(traces: Path) -> None:
    retriever = FakeRetriever(make_result())
    pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=retriever,
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    assert retriever.calls[0][0] == "What is the expense ratio of HDFC Large Cap Fund?"


def test_detected_pii_never_reaches_retrieval(traces: Path) -> None:
    retriever = FakeRetriever(make_result())
    result = pipeline.answer_question(
        "what is the expense ratio for my folio 1234567890 in HDFC Large Cap Fund?",
        retriever=retriever,
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    assert result.refusal_kind == "npi"
    assert retriever.calls == []
    assert "1234567890" not in traces.read_text(encoding="utf-8")


def test_redacted_preview_removes_pii() -> None:
    preview = pipeline.redacted_preview("my PAN is ABCDE1234F and phone 9876543210")
    assert "ABCDE1234F" not in preview
    assert "9876543210" not in preview


def test_top_k_is_passed_to_retriever(traces: Path) -> None:
    from app import config

    retriever = FakeRetriever(make_result())
    pipeline.answer_question(
        "What is the exit load on HDFC ELSS Tax Saver Fund?",
        retriever=retriever,
        answerer=FakeAnswerer(ADVICE_ANSWER),
        traces_path=traces,
    )
    assert retriever.calls[0][1] == config.TOP_K


def test_offline_flag_uses_extractive_answerer(traces: Path) -> None:
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        offline=True,
        retriever=FakeRetriever(make_result()),
        traces_path=traces,
    )
    assert result.generator.startswith("extractive")
    assert result.refused is False


def test_model_semantic_refusal_becomes_not_found(traces: Path) -> None:
    answerer = FakeAnswerer("NOT_FOUND: I could not find that in my sources.")
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=FakeRetriever(make_result()),
        answerer=answerer,
        traces_path=traces,
    )
    assert result.refused is True
    assert result.refusal_kind == "not_found"
    assert result.citations == []


def test_long_answer_is_shortened_and_generator_noted(traces: Path) -> None:
    long_answer = " ".join(
        f"Sentence number {index} adds filler detail [SOURCE:groww_large_cap]."
        for index in range(1, 8)
    )
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(long_answer),
        traces_path=traces,
    )
    assert result.refused is False
    assert "shortened" in result.generator


def test_debug_flag_does_not_change_the_answer(traces: Path) -> None:
    retriever_a = FakeRetriever(make_result())
    retriever_b = FakeRetriever(make_result())
    plain = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=retriever_a,
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    debug = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        debug=True,
        retriever=retriever_b,
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    assert plain.answer == debug.answer


def test_raw_query_is_never_written_to_trace(traces: Path) -> None:
    secret = "zebra-unique-token-9931"
    pipeline.answer_question(
        f"what is the expense ratio of HDFC Large Cap Fund {secret}?",
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    raw = traces.read_text(encoding="utf-8")
    assert secret not in raw


def test_trace_records_hash_and_bounded_preview(traces: Path) -> None:
    query = "What is the expense ratio of HDFC Large Cap Fund?"
    pipeline.answer_question(
        query,
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    record = read_traces(traces)[0]
    assert record["query_sha256"] == pipeline.query_hash(query)
    assert record["query_redacted"] == pipeline.redacted_preview(query)
    assert record["query_redacted"] != query
    assert record["intent"] == "factual"
    assert record["refused"] is False
    assert record["generator"]
    assert record["embed_model"]
    assert record["corpus_version"]


def test_every_path_writes_exactly_one_trace(traces: Path) -> None:
    pipeline.answer_question(
        "PAN ABCDE1234F", retriever=FakeRetriever(make_result()), traces_path=traces
    )
    pipeline.answer_question(
        "Should I buy HDFC Small Cap Fund?",
        retriever=FakeRetriever(make_result()),
        traces_path=traces,
    )
    pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=FakeRetriever(make_result(passed_floor=False, chunks=[])),
        traces_path=traces,
    )
    pipeline.answer_question(
        "What is the exit load on HDFC ELSS Tax Saver Fund?",
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    assert len(read_traces(traces)) == 4


def test_trace_appends_rather_than_overwrites(traces: Path) -> None:
    for _ in range(3):
        pipeline.answer_question(
            "What is the expense ratio of HDFC Large Cap Fund?",
            retriever=FakeRetriever(make_result()),
            answerer=FakeAnswerer(FACTUAL_ANSWER),
            traces_path=traces,
        )
    assert len(read_traces(traces)) == 3


def test_trace_lines_are_valid_json_with_ordered_keys(traces: Path) -> None:
    from app.models import TRACE_KEY_ORDER

    pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    line = traces.read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(line)
    assert list(payload) == list(TRACE_KEY_ORDER)


def test_trace_records_retrieved_chunk_scores(traces: Path) -> None:
    pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    record = read_traces(traces)[0]
    assert record["retrieved"]
    assert "best_score" in record["retrieved"][0]


def test_trace_records_citations(traces: Path) -> None:
    pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    record = read_traces(traces)[0]
    assert record["citations"][0]["source_id"] == "groww_large_cap"
    assert record["citations"][0]["section"] == "Fees"
    assert record["authority"] == AUTHORITY_MIRROR


def test_freshness_uses_newest_cited_chunk(traces: Path) -> None:
    older = make_chunk(source_id="groww_small_cap", scheme_id="S4", retrieved_at=BASE)
    newer = make_chunk(
        source_id="groww_large_cap", scheme_id="S1", retrieved_at=BASE + timedelta(days=10)
    )
    retriever = FakeRetriever(make_result(chunks=[older, newer]))
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=retriever,
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    assert result.freshness_date == (BASE + timedelta(days=10)).date()


def test_official_authority_is_preserved(traces: Path) -> None:
    chunk = make_chunk(authority=AUTHORITY_OFFICIAL)
    retriever = FakeRetriever(make_result(chunks=[chunk]))
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=retriever,
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    assert result.authority == AUTHORITY_OFFICIAL


def test_result_is_a_query_result(traces: Path) -> None:
    result = pipeline.answer_question(
        "What is the expense ratio of HDFC Large Cap Fund?",
        retriever=FakeRetriever(make_result()),
        answerer=FakeAnswerer(FACTUAL_ANSWER),
        traces_path=traces,
    )
    assert isinstance(result, QueryResult)
    assert result.trace_id


def test_empty_query_is_refused_not_crashed(traces: Path) -> None:
    result = pipeline.answer_question(
        "", retriever=FakeRetriever(make_result()), traces_path=traces
    )
    assert result.refused is True
    assert result.refusal_kind == "out_of_scope"


def test_none_query_is_refused_not_crashed(traces: Path) -> None:
    result = pipeline.answer_question(
        None, retriever=FakeRetriever(make_result()), traces_path=traces
    )
    assert result.refused is True


def test_traces_directory_is_created(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "traces.jsonl"
    pipeline.answer_question(
        "PAN ABCDE1234F",
        retriever=FakeRetriever(make_result()),
        traces_path=nested,
    )
    assert nested.exists()


def test_default_trace_path_is_the_eval_directory() -> None:
    assert pipeline.TRACES_PATH == pipeline.config.EVAL_DIR / "traces.jsonl"


def test_redacted_preview_is_truncated() -> None:
    long_query = "word " * 200
    preview = pipeline.redacted_preview(long_query)
    assert len(preview) <= pipeline.REDACTED_PREVIEW_CHARS + 3
    assert preview.endswith("...")


def test_redacted_preview_of_empty_query() -> None:
    assert pipeline.redacted_preview("") == ""


def test_query_hash_is_stable() -> None:
    assert pipeline.query_hash("abc") == pipeline.query_hash("abc")
    assert pipeline.query_hash("abc") != pipeline.query_hash("abd")


def test_refusal_copy_uses_canonical_sections() -> None:
    copy = pipeline.refusal_copy("not_found", ["Fees", "Exit load", "Benchmark"])
    assert "Fees" in copy
    assert "Benchmark" not in copy


def test_unknown_refusal_kind_falls_back_to_not_found() -> None:
    assert pipeline.refusal_copy("mystery", []) == pipeline.REFUSAL_NOT_FOUND.format(
        sections="none"
    )
