from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app import config
from app.ingest import chunk as chunk_mod
from app.ingest.chunk import (
    CHUNKERS,
    HeadingAwareChunker,
    RecursiveCharChunker,
    SectionChunker,
    get_chunker,
    merge_spans,
    protect_tables,
    table_spans,
)
from app.models import Chunk, Document, Section, approx_token_count, make_chunk_id

ALL = sorted(CHUNKERS)


def build_doc(
    sections: list[tuple[str, int, str]],
    scheme_id: str = "S1",
    source_id: str | None = None,
) -> Document:
    lines: list[str] = []
    offset = 0
    built: list[Section] = []
    for ordinal, (title, level, body) in enumerate(sections):
        rendered = f"{'#' * level} {title}\n{body}"
        lines.append(rendered)
        built.append(
            Section(
                title=title,
                level=level,
                text=rendered,
                heading_path=title,
                char_start=offset,
                char_end=offset + len(rendered),
                page=ordinal + 1,
                ordinal=ordinal,
            )
        )
        offset += len(rendered) + 1
    return Document(
        source_id=source_id or f"{scheme_id}_test",
        scheme_id=scheme_id,
        url="https://groww.in/funds/hdfc-test",
        title="Test",
        source_type="factsheet",
        authority="mirror",
        extraction_method="html",
        retrieved_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
        content_hash="abc",
        document_date=date(2026, 9, 30),
        fields={"expense_ratio": "1.03"},
        is_complete=True,
        text="\n".join(lines),
        sections=built,
    )


def long_sections(count: int = 8, body_chars: int = 300) -> list[tuple[str, int, str]]:
    return [
        (
            f"Scheme {index}",
            2,
            f"Body {index}. " + ("filler words about the scheme " * 30)[:body_chars],
        )
        for index in range(count)
    ]


def covered(doc: Document, chunks: list[Chunk]) -> set[int]:
    seen: set[int] = set()
    for item in chunks:
        seen.update(range(item.char_start, min(item.char_end, len(doc.text))))
    return seen


def test_get_chunker_returns_each_registered_strategy() -> None:
    for name in ALL:
        assert isinstance(get_chunker(name), CHUNKERS[name])


def test_get_chunker_defaults_to_config_and_rejects_unknown() -> None:
    assert isinstance(get_chunker(), CHUNKERS[config.CHUNKER])
    with pytest.raises(ValueError):
        get_chunker("C99")


def test_c4_emits_one_chunk_per_section() -> None:
    doc = build_doc(long_sections(5))
    chunks = SectionChunker().split(doc)
    assert len(chunks) == 5
    assert [chunk.section_title for chunk in chunks] == [f"Scheme {i}" for i in range(5)]


def test_c4_falls_back_when_no_sections() -> None:
    doc = build_doc(long_sections(2))
    doc.sections = []
    assert SectionChunker().split(doc)


def test_every_strategy_respects_token_budget_on_sectioned_input() -> None:
    doc = build_doc(long_sections(10))
    for name in ALL:
        chunks = get_chunker(name).split(doc)
        assert chunks, name
        budget = config.CHUNK_SIZE
        oversized = [c for c in chunks if c.token_count > budget * 1.5]
        assert not oversized, f"{name} produced {len(oversized)} oversized chunks"


def test_c3_splits_a_document_that_exceeds_the_budget() -> None:
    doc = build_doc(long_sections(10))
    chunks = HeadingAwareChunker().split(doc)
    assert len(chunks) > 1
    assert all(chunk.token_count <= config.CHUNK_SIZE * 1.5 for chunk in chunks)


def test_c3_never_merges_across_a_top_level_scheme_heading() -> None:
    doc = build_doc(
        [
            ("HDFC Large Cap Fund", 1, "A" * 200),
            ("Objective", 2, "B" * 200),
            ("HDFC Flexi Cap Fund", 1, "C" * 200),
            ("Objective", 2, "D" * 200),
        ]
    )
    chunks = HeadingAwareChunker(chunk_size=200).split(doc)
    assert len(chunks) == 2
    first, second = chunks
    assert "A" * 200 in first.text and "B" * 200 in first.text
    assert "C" * 200 not in first.text
    assert "C" * 200 in second.text and "D" * 200 in second.text
    assert "A" * 200 not in second.text


def test_c3_covers_every_character_without_gaps() -> None:
    doc = build_doc(long_sections(12))
    for name in ("C2", "C3", "C4"):
        chunks = get_chunker(name).split(doc)
        missing = set(range(len(doc.text))) - covered(doc, chunks)
        lost = [i for i in missing if not doc.text[i].isspace()]
        assert not lost, f"{name} dropped {len(lost)} non-whitespace characters"


def test_c2_does_not_consume_separators() -> None:
    doc = build_doc(long_sections(8))
    chunks = RecursiveCharChunker().split(doc)
    missing = {i for i in set(range(len(doc.text))) - covered(doc, chunks)}
    assert not [i for i in missing if not doc.text[i].isspace()]


def test_chunk_text_matches_its_declared_offsets() -> None:
    doc = build_doc(long_sections(8))
    for name in ALL:
        for chunk in get_chunker(name).split(doc):
            sliced = doc.text[chunk.char_start : chunk.char_end]
            assert chunk.text == sliced.strip(), name


def test_chunk_ids_are_deterministic_and_ordered() -> None:
    doc = build_doc(long_sections(8))
    for name in ALL:
        chunks = get_chunker(name).split(doc)
        expected = [
            make_chunk_id(doc.source_id, index) for index in range(1, len(chunks) + 1)
        ]
        assert [chunk.chunk_id for chunk in chunks] == expected, name


def test_chunks_carry_source_and_scheme_provenance() -> None:
    doc = build_doc(long_sections(6), scheme_id="S3")
    for name in ALL:
        for chunk in get_chunker(name).split(doc):
            assert chunk.scheme_id == "S3"
            assert chunk.source_id == doc.source_id
            assert chunk.document_date == doc.document_date
            assert chunk.page is not None
            assert chunk.heading_path


def test_table_spans_exclude_the_trailing_newline() -> None:
    text = "intro\nA | B\nC | D\nafter"
    spans = table_spans(text)
    assert len(spans) == 1
    start, end = spans[0]
    assert text[start:end] == "A | B\nC | D"
    assert text[end] == "\n"


def test_protect_tables_never_truncates_content() -> None:
    text = "head\nA | B\nC | D\ntail content here"
    span = table_spans(text)[0]
    assert protect_tables(text, 0, len(text)) == len(text)
    assert protect_tables(text, 0, span[0] + 2) == span[1]
    assert protect_tables(text, 0, 4) == 4


def test_merge_spans_keeps_adjacent_spans_separate() -> None:
    assert merge_spans([(0, 10), (10, 20)]) == [(0, 10), (10, 20)]
    assert merge_spans([(0, 10), (5, 20)]) == [(0, 20)]
    assert merge_spans([(0, 0), (5, 20)]) == [(5, 20)]


def test_no_strategy_splits_a_table_across_chunks() -> None:
    rows = "\n".join(f"Holding {i} | {i}.11%" for i in range(30))
    doc = build_doc([("Holdings", 2, rows)])
    table = table_spans(doc.text)[0]
    for name in ALL:
        for chunk in get_chunker(name).split(doc):
            covered_table = chunk.char_start <= table[0] and chunk.char_end >= table[1]
            straddles = chunk.char_start < table[1] and table[0] < chunk.char_end
            assert covered_table or not straddles, f"{name} split a table"


def test_empty_document_yields_no_chunks() -> None:
    doc = build_doc(long_sections(2))
    doc.text = ""
    doc.sections = []
    for name in ALL:
        assert get_chunker(name).split(doc) == []


def test_whitespace_only_document_yields_no_chunks() -> None:
    doc = build_doc(long_sections(2))
    doc.text = "   \n\n  "
    for name in ALL:
        assert get_chunker(name).split(doc) == []


def test_single_oversized_section_is_windowed_with_overlap() -> None:
    doc = build_doc([("Huge", 1, "word " * 3000)])
    chunks = HeadingAwareChunker(chunk_size=100, overlap=20).split(doc)
    assert len(chunks) > 1
    assert all(chunk.token_count <= 400 for chunk in chunks)
    starts = [chunk.char_start for chunk in chunks]
    assert starts == sorted(starts)


def test_overlap_larger_than_budget_does_not_collapse_the_step() -> None:
    doc = build_doc([("Huge", 1, "word " * 400)])
    for name in ("C1", "C2", "C3"):
        for chunk_size, overlap in ((50, 100), (10, 500), (200, 1000)):
            chunker = get_chunker(name, chunk_size=chunk_size, overlap=overlap)
            assert chunker.step_chars * 2 >= chunker.char_budget, name
            chunks = chunker.split(doc)
            assert len(chunks) < 200, f"{name} {chunk_size}/{overlap} exploded"
            assert chunks, name


def test_extreme_overlap_is_clamped_for_every_sized_chunker() -> None:
    for name in ("C1", "C2", "C3"):
        for chunk_size in (10, 100, 500):
            chunker = get_chunker(name, chunk_size=chunk_size, overlap=10_000)
            assert chunker.char_budget // 2 <= chunker.step_chars <= chunker.char_budget


def test_chunking_is_deterministic_across_repeated_runs() -> None:
    doc = build_doc(long_sections(10))
    for name in ALL:
        first = [(c.chunk_id, c.char_start, c.char_end) for c in get_chunker(name).split(doc)]
        second = [(c.chunk_id, c.char_start, c.char_end) for c in get_chunker(name).split(doc)]
        assert first == second, name


def test_chunk_token_count_matches_text() -> None:
    doc = build_doc(long_sections(6))
    for name in ALL:
        for chunk in get_chunker(name).split(doc):
            assert chunk.token_count == approx_token_count(chunk.text), name


def test_synthetic_corpus_is_usable_by_every_strategy() -> None:
    from scripts.synthetic_corpus import build_synthetic_documents

    documents = build_synthetic_documents()
    assert len(documents) == len(config.SCHEMES)
    for document in documents:
        assert document.is_complete
        assert document.sections
        for name in ALL:
            chunks = get_chunker(name).split(document)
            assert chunks, f"{document.source_id} {name}"
            for chunk in chunks:
                assert chunk.scheme_id == document.scheme_id
                assert chunk.text.strip()
