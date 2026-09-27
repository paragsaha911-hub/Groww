from __future__ import annotations

import json
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import (
    AUTHORITY_MIRROR,
    AUTHORITY_OFFICIAL,
    TRACE_KEY_ORDER,
    Chunk,
    Citation,
    Document,
    QueryResult,
    RetrievalResult,
    ScoredChunk,
    Scheme,
    TraceRecord,
    approx_token_count,
    as_utc,
    freshness_date_from,
    iso_date,
    make_chunk_id,
    utcnow,
)

SCHEME = Scheme(
    scheme_id="S1",
    name="HDFC Large Cap Fund",
    category="Large Cap",
    plan="Direct Growth",
    url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
)


def make_document(**overrides: object) -> Document:
    base: dict[str, object] = {
        "source_id": "s1_factsheet_2026-08",
        "scheme_id": "S1",
        "url": SCHEME.url,
        "title": "HDFC Large Cap Fund - Factsheet",
        "source_type": "factsheet",
        "authority": AUTHORITY_OFFICIAL,
        "extraction_method": "pdf",
        "retrieved_at": utcnow(),
        "content_hash": "a" * 64,
    }
    base.update(overrides)
    return Document(**base)  # type: ignore[arg-type]


def make_chunk(**overrides: object) -> Chunk:
    base: dict[str, object] = {
        "chunk_id": make_chunk_id("s1", 4),
        "source_id": "s1_factsheet_2026-08",
        "scheme_id": "S1",
        "scheme_name": SCHEME.name,
        "category": SCHEME.category,
        "section_title": "Fees",
        "heading_path": "HDFC Large Cap Fund>Fees",
        "text": "Expense ratio: 1.35% p.a.",
        "ordinal": 4,
        "char_start": 100,
        "char_end": 125,
        "url": SCHEME.url,
        "retrieved_at": utcnow(),
        "authority": AUTHORITY_OFFICIAL,
        "corpus_version": "20260927T101204Z",
    }
    base.update(overrides)
    return Chunk(**base)  # type: ignore[arg-type]


def field_names(cls: type) -> set[str]:
    return {f.name for f in fields(cls)}


def test_make_chunk_id_is_deterministic_and_zero_padded() -> None:
    assert make_chunk_id("s1", 4) == "s1_c0004"
    assert make_chunk_id("s1", 0) == "s1_c0000"
    assert make_chunk_id("s1", 12) == "s1_c0012"
    assert make_chunk_id("s1_factsheet_2026-08", 7) == "s1_factsheet_2026-08_c0007"
    assert make_chunk_id("s1", 4) == make_chunk_id("s1", 4)


def test_make_chunk_id_rejects_negative_ordinal() -> None:
    with pytest.raises(ValueError):
        make_chunk_id("s1", -1)


def test_approx_token_count_never_returns_zero() -> None:
    assert approx_token_count("") == 1
    assert approx_token_count("a") == 1
    assert approx_token_count("a" * 4) == 1
    assert approx_token_count("a" * 5) == 2
    assert approx_token_count("a" * 400) == 100


def test_naive_datetimes_are_coerced_to_utc() -> None:
    naive = datetime(2026, 9, 27, 10, 12, 4)
    assert as_utc(naive).tzinfo is timezone.utc

    doc = make_document(retrieved_at=naive)
    assert doc.retrieved_at.tzinfo is timezone.utc

    chunk = make_chunk(retrieved_at=naive)
    assert chunk.retrieved_at.tzinfo is timezone.utc

    trace = make_trace(ts=naive)
    assert trace.ts.tzinfo is timezone.utc


def test_offset_datetimes_are_normalised_to_utc() -> None:
    aware = datetime(2026, 9, 27, 15, 42, 4, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    normalised = as_utc(aware)
    assert normalised.tzinfo is timezone.utc
    assert normalised.hour == 10
    assert normalised.minute == 12
    assert iso_date(aware) == "2026-09-27"


def test_chunk_dataclass_matches_architecture_contract() -> None:
    expected = {
        "chunk_id",
        "source_id",
        "scheme_id",
        "scheme_name",
        "category",
        "section_title",
        "heading_path",
        "text",
        "ordinal",
        "char_start",
        "char_end",
        "url",
        "retrieved_at",
        "authority",
        "corpus_version",
        "page",
        "token_count",
        "document_date",
    }
    assert field_names(Chunk) == expected


def test_document_dataclass_matches_architecture_contract() -> None:
    expected = {
        "source_id",
        "scheme_id",
        "url",
        "title",
        "source_type",
        "authority",
        "extraction_method",
        "retrieved_at",
        "content_hash",
        "document_date",
        "fields",
        "is_complete",
        "text",
        "sections",
    }
    assert field_names(Document) == expected


def test_chunk_token_count_autofills_from_text() -> None:
    chunk = make_chunk(text="a" * 400, token_count=0)
    assert chunk.token_count == 100
    explicit = make_chunk(text="a" * 400, token_count=7)
    assert explicit.token_count == 7


def test_chunk_from_document_inherits_provenance() -> None:
    doc = make_document()
    chunk = Chunk.from_document(
        doc,
        ordinal=0,
        text="Benchmark: Nifty 100 TRI",
        section_title="Benchmark",
        heading_path="HDFC Large Cap Fund>Benchmark",
        scheme_name=SCHEME.name,
        category=SCHEME.category,
        char_start=0,
        char_end=28,
        corpus_version="20260927T101204Z",
        page=2,
    )
    assert chunk.chunk_id == "s1_factsheet_2026-08_c0000"
    assert chunk.source_id == doc.source_id
    assert chunk.scheme_id == doc.scheme_id
    assert chunk.url == doc.url
    assert chunk.retrieved_at == doc.retrieved_at
    assert chunk.authority == doc.authority
    assert chunk.page == 2
    assert chunk.corpus_version == "20260927T101204Z"


def test_citation_label_includes_section_and_page() -> None:
    with_page = Citation(
        source_id="s1",
        url="https://example.invalid/x",
        section_title="Fees",
        authority=AUTHORITY_OFFICIAL,
        page=3,
    )
    assert with_page.label() == "https://example.invalid/x (Fees, page 3)"

    without_page = Citation(
        source_id="s1",
        url="https://example.invalid/x",
        section_title="Fees",
        authority=AUTHORITY_MIRROR,
    )
    assert without_page.label() == "https://example.invalid/x (Fees)"


def test_scored_chunk_exposes_all_six_score_fields_in_trace() -> None:
    scored = ScoredChunk(
        chunk=make_chunk(),
        rank=1,
        fused_score=0.7123456,
        cosine_score=0.654321,
        lexical_score=0.1,
        rerank_score=0.2,
    )
    assert scored.chunk_id == "s1_c0004"
    trace = scored.to_trace()
    for key in (
        "rank",
        "chunk_id",
        "score",
        "fused_score",
        "cosine_score",
        "lexical_score",
        "rerank_score",
        "scheme_id",
        "section",
    ):
        assert key in trace
    assert trace["score"] == trace["fused_score"] == 0.7123


def test_retrieval_result_defaults_to_failing_the_floor() -> None:
    result = RetrievalResult(query="q", intent="factual")
    assert result.candidates == []
    assert result.passed_floor is False
    assert result.best_score == 0.0


def test_freshness_date_uses_latest_cited_value() -> None:
    older = utcnow() - timedelta(days=5)
    newer = utcnow()
    assert freshness_date_from([]) is None
    assert freshness_date_from([older, newer]) == newer.date()
    assert freshness_date_from([older]) == older.date()
    assert isinstance(freshness_date_from([newer]), date)


def test_query_result_render_plain_matches_contract() -> None:
    result = QueryResult(
        answer="The expense ratio is 1.35% p.a.",
        intent="factual",
        sentences=["The expense ratio is 1.35% p.a."],
        citations=[
            Citation(
                source_id="s1",
                url="https://hdfcamc.com/factsheet.pdf",
                section_title="Fees",
                authority=AUTHORITY_OFFICIAL,
                page=2,
            )
        ],
        freshness_date=date(2026, 9, 27),
        generator="claude:claude-sonnet-5",
    )
    rendered = result.render_plain()
    assert rendered.startswith("The expense ratio is 1.35% p.a.")
    assert "Source: https://hdfcamc.com/factsheet.pdf (Fees, page 2)" in rendered
    assert rendered.endswith("Last updated from sources: 2026-09-27")


def test_query_result_render_plain_omits_freshness_when_absent() -> None:
    result = QueryResult(answer="Not found in sources.", intent="factual", refused=True)
    assert result.render_plain() == "Not found in sources."


def make_trace(**overrides: object) -> TraceRecord:
    base: dict[str, object] = {
        "ts": utcnow(),
        "query_sha256": "f" * 64,
        "query_redacted": "expense ratio of hdfc large cap fund",
        "pii_detected": [],
        "intent": "factual",
        "retrieved": [
            {
                "rank": 1,
                "chunk_id": "s1_c0004",
                "score": 0.71,
                "scheme_id": "S1",
                "section": "Fees",
            }
        ],
        "answer": "The expense ratio is 1.35% p.a.",
        "citations": [
            {
                "source_id": "s1",
                "url": "https://hdfcamc.com/factsheet.pdf",
                "section": "Fees",
            }
        ],
        "sentence_count": 1,
        "generator": "claude:claude-sonnet-5",
        "embed_model": "all-MiniLM-L6-v2",
        "authority": AUTHORITY_OFFICIAL,
        "corpus_version": "20260927T101204Z",
        "latency_ms": 2380,
        "refused": False,
    }
    base.update(overrides)
    return TraceRecord(**base)  # type: ignore[arg-type]


def test_trace_json_line_has_prd_key_order() -> None:
    payload = json.loads(make_trace().to_json_line())
    assert list(payload.keys()) == list(TRACE_KEY_ORDER)
    prd_15_2_keys = [
        "ts",
        "query_sha256",
        "query_redacted",
        "pii_detected",
        "intent",
        "retrieved",
        "answer",
        "citations",
        "sentence_count",
        "generator",
        "embed_model",
        "authority",
        "corpus_version",
        "latency_ms",
        "refused",
    ]
    assert list(payload.keys())[: len(prd_15_2_keys)] == prd_15_2_keys


def test_trace_has_no_field_that_could_hold_a_raw_query() -> None:
    payload = json.loads(make_trace().to_json_line())
    assert "query" not in payload
    queryish = [k for k in payload if "query" in k]
    assert queryish == ["query_sha256", "query_redacted"]


def test_trace_serialises_timestamp_as_iso_utc() -> None:
    payload = json.loads(make_trace().to_json_line())
    assert payload["ts"].endswith("+00:00")
    assert datetime.fromisoformat(payload["ts"]).tzinfo is timezone.utc


def test_trace_refusal_path_serialises_with_refusal_kind() -> None:
    trace = make_trace(
        intent="npi",
        query_redacted="[REDACTED:pan]",
        pii_detected=["pan"],
        answer="I can't accept personal identifiers like PAN, Aadhaar, account numbers, OTPs, email or phone.",
        citations=[],
        sentence_count=1,
        refused=True,
        refusal_kind="npi",
    )
    payload = json.loads(trace.to_json_line())
    assert payload["refused"] is True
    assert payload["refusal_kind"] == "npi"
    assert payload["pii_detected"] == ["pan"]
    assert payload["citations"] == []


def test_trace_does_not_mutate_caller_lists() -> None:
    detected = ["email"]
    retrieved = [{"rank": 1}]
    citations = [{"source_id": "s1"}]
    trace = make_trace(pii_detected=detected, retrieved=retrieved, citations=citations)
    trace.to_json_line()
    assert detected == ["email"]
    assert retrieved == [{"rank": 1}]
    assert citations == [{"source_id": "s1"}]


def test_all_dataclasses_are_importable_and_constructible() -> None:
    for cls in (Scheme, Document, Chunk, ScoredChunk, RetrievalResult, Citation, QueryResult, TraceRecord):
        assert dataclass_fields_present(cls)


def dataclass_fields_present(cls: type) -> bool:
    return bool(fields(cls)) and hasattr(cls, "__dataclass_fields__")
