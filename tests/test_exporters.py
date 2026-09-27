from __future__ import annotations

import csv
import json

from app import config
from scripts import export_sources


def test_every_configured_source_appears_in_the_export() -> None:
    rows = export_sources.build_rows()
    assert {row["source_id"] for row in rows} == {s["source_id"] for s in config.SOURCES}
    assert len(rows) == len(config.SOURCES)


def test_rows_carry_the_csv_columns() -> None:
    for row in export_sources.build_rows():
        assert set(row) == set(export_sources.CSV_COLUMNS)


def test_incomplete_sources_are_visible_not_hidden() -> None:
    rows = export_sources.build_rows()
    for row in rows:
        if not row["is_complete"]:
            assert row["source_id"]


def test_csv_round_trips(tmp_path) -> None:
    rows = export_sources.build_rows()
    path = tmp_path / "sources.csv"
    export_sources.write_csv(rows, path)
    with path.open(encoding="utf-8", newline="") as handle:
        parsed = list(csv.DictReader(handle))
    assert len(parsed) == len(rows)
    assert parsed[0].keys() == set(export_sources.CSV_COLUMNS)


def test_markdown_flags_incomplete_sources(tmp_path) -> None:
    rows = export_sources.build_rows()
    path = tmp_path / "sources.md"
    export_sources.write_markdown(rows, path)
    text = path.read_text(encoding="utf-8")
    for scheme in config.SCHEMES:
        assert scheme.name in text
        assert scheme.url in text
    for row in rows:
        if not row["is_complete"] and row["fields_extracted"]:
            assert "INCOMPLETE" in text


def test_loaders_tolerate_missing_and_corrupt_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    assert export_sources.load_raw_index() == {}
    assert export_sources.load_processed() == {}
    assert export_sources.load_chunk_counts() == {}
    (tmp_path / "raw").mkdir(parents=True)
    (config.RAW_DIR / "index.json").write_text("{not json", encoding="utf-8")
    assert export_sources.load_raw_index() == {}


def test_golden_set_is_wellformed_and_unique() -> None:
    entries = json.loads(
        (config.EVAL_DIR / "golden_set.json").read_text(encoding="utf-8")
    )
    assert isinstance(entries, list) and entries
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))
    queries = [entry["query"].strip().lower() for entry in entries]
    assert len(queries) == len(set(queries))
    scheme_ids = {scheme.scheme_id for scheme in config.SCHEMES}
    for entry in entries:
        assert entry["query"].strip()
        assert entry["expected_scheme"] is None or entry["expected_scheme"] in scheme_ids
        assert "expected_section" in entry
        if entry["expected_scheme"] is None:
            assert entry.get("kind") or entry.get("expected_scheme") is None


def test_golden_set_covers_every_scheme_and_an_out_of_scope_case() -> None:
    entries = json.loads(
        (config.EVAL_DIR / "golden_set.json").read_text(encoding="utf-8")
    )
    covered = {entry["expected_scheme"] for entry in entries} - {None}
    assert covered == {scheme.scheme_id for scheme in config.SCHEMES}
    assert any(entry["expected_scheme"] is None for entry in entries)


def test_expected_sections_match_a_real_document_section() -> None:
    from app.ingest import parse

    documents = parse.load_corpus()
    if not documents:
        return
    known = {section.title for document in documents for section in document.sections}
    entries = json.loads(
        (config.EVAL_DIR / "golden_set.json").read_text(encoding="utf-8")
    )
    for entry in entries:
        expected = entry.get("expected_section")
        if expected:
            assert expected in known, f"{entry['id']}: {expected!r} is not a real section"
