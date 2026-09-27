from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from app.index.report import (
    write_chunks_txt,
    write_embeddings_txt,
    write_reports,
)
from app.models import AUTHORITY_MIRROR, Chunk


def make_chunk(chunk_id: str = "S1_groww_c0001", text: str = "Expense ratio is 1.03 percent") -> Chunk:
    from datetime import date, datetime, timezone

    return Chunk(
        chunk_id=chunk_id,
        source_id="S1_groww",
        scheme_id="S1",
        scheme_name="HDFC Large Cap Fund",
        category="Large Cap",
        section_title="Expense ratio",
        heading_path="Fund > Expense ratio",
        text=text,
        ordinal=1,
        char_start=0,
        char_end=len(text),
        url="https://groww.in/funds/x",
        retrieved_at=datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc),
        authority=AUTHORITY_MIRROR,
        corpus_version="cvtest",
        page=None,
        token_count=6,
        document_date=date(2026, 6, 30),
    )


def unit_vector(dim: int) -> list[float]:
    vector = [0.0] * dim
    vector[0] = 1.0
    return vector


def test_chunks_txt_contains_metadata_and_full_text(tmp_path) -> None:
    chunk = make_chunk(text="Expense ratio is 1.03 percent")
    path = write_chunks_txt([chunk], tmp_path / "chunks.txt", {"corpus_version": "cvtest"})
    body = path.read_text(encoding="utf-8")
    assert "S1_groww_c0001" in body
    assert "S1" in body
    assert "HDFC Large Cap Fund" in body
    assert "Expense ratio" in body
    assert f"0-{len(chunk.text)}" in body
    assert "Expense ratio is 1.03 percent" in body
    assert "cvtest" in body
    assert "2026-06-30" in body


def test_chunks_txt_lists_every_chunk_in_order(tmp_path) -> None:
    chunks = [make_chunk(f"S{i}_groww_c0001", f"chunk body {i}") for i in range(1, 4)]
    body = write_chunks_txt(chunks, tmp_path / "chunks.txt").read_text(encoding="utf-8")
    for index, chunk in enumerate(chunks, start=1):
        assert f"[{index}] chunk_id     : {chunk.chunk_id}" in body
    assert body.index("S1_groww_c0001") < body.index("S2_groww_c0001") < body.index("S3_groww_c0001")
    assert "chunks: 3" in body


def test_embeddings_txt_writes_every_dimension(tmp_path) -> None:
    dim = 384
    chunks = [make_chunk(f"S{i}_groww_c0001") for i in range(1, 3)]
    vectors = [unit_vector(dim), unit_vector(dim)]
    path = write_embeddings_txt(chunks, vectors, tmp_path / "embeddings.txt")
    body = path.read_text(encoding="utf-8")
    assert "dimensions: 384" in body
    assert "dim          : 384" in body
    assert "l2_norm      : 1.000000" in body
    blocks = [b for b in body.split("=" * 78) if b.strip().startswith("chunk_id")]
    assert len(blocks) == 2
    for block in blocks:
        values = re.findall(r"[-+]\d\.\d{6}", block.split("vector:")[1])
        assert len(values) == dim
        indices = [int(i) for i in re.findall(r"\[\s*(\d+)\]", block)]
        assert indices == list(range(0, dim, 8))


def test_embeddings_txt_reports_real_norm(tmp_path) -> None:
    vector = [0.6, 0.8] + [0.0] * 2
    path = write_embeddings_txt([make_chunk()], [vector], tmp_path / "embeddings.txt")
    body = path.read_text(encoding="utf-8")
    assert "l2_norm      : 1.000000" in body
    assert "+0.600000" in body


def test_embeddings_txt_rejects_count_mismatch(tmp_path) -> None:
    with pytest.raises(ValueError):
        write_embeddings_txt([make_chunk()], [], tmp_path / "embeddings.txt")


def test_write_reports_creates_both_files(tmp_path) -> None:
    chunks = [make_chunk()]
    vectors = [unit_vector(384)]
    written = write_reports(chunks, vectors, tmp_path)
    assert [p.name for p in written] == ["chunks.txt", "embeddings.txt"]
    assert all(p.is_file() for p in written)


def test_write_reports_can_skip_vectors(tmp_path) -> None:
    written = write_reports([make_chunk()], None, tmp_path)
    assert [p.name for p in written] == ["chunks.txt"]
    assert not (tmp_path / "embeddings.txt").exists()


def test_reports_preserve_unicode(tmp_path) -> None:
    chunk = make_chunk(text="Direct growth expense ratio 1.03% — निवेश")
    body = write_chunks_txt([chunk], tmp_path / "chunks.txt").read_text(encoding="utf-8")
    assert "निवेश" in body
    assert "—" in body
