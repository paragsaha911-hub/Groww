from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from app.models import Chunk

DIVIDER = "=" * 78
SEPARATOR = "-" * 78
VALUES_PER_LINE = 8


def _header(title: str, counts: dict[str, Any]) -> list[str]:
    lines = [DIVIDER, title, DIVIDER]
    for key, value in counts.items():
        lines.append(f"{key}: {value}")
    lines.append("")
    return lines


def write_chunks_txt(
    chunks: Sequence[Chunk], path: Path, counts: dict[str, Any] | None = None
) -> Path:
    lines = _header("CHUNKS", dict(counts or {}) | {"chunks": len(chunks)})
    for position, chunk in enumerate(chunks, start=1):
        lines.append(DIVIDER)
        lines.append(f"[{position}] chunk_id     : {chunk.chunk_id}")
        lines.append(f"    source_id     : {chunk.source_id}")
        lines.append(f"    scheme_id     : {chunk.scheme_id}")
        lines.append(f"    scheme_name   : {chunk.scheme_name}")
        lines.append(f"    category      : {chunk.category}")
        lines.append(f"    section_title : {chunk.section_title}")
        lines.append(f"    heading_path  : {chunk.heading_path}")
        lines.append(f"    ordinal       : {chunk.ordinal}")
        lines.append(f"    char_span     : {chunk.char_start}-{chunk.char_end}")
        lines.append(f"    token_count   : {chunk.token_count}")
        lines.append(f"    authority     : {chunk.authority}")
        lines.append(f"    document_date : {chunk.document_date or '-'}")
        lines.append(f"    retrieved_at  : {chunk.retrieved_at.isoformat()}")
        lines.append(f"    corpus_version: {chunk.corpus_version}")
        lines.append(f"    chars         : {len(chunk.text)}")
        lines.append("")
        lines.append(chunk.text)
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_embeddings_txt(
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
    path: Path,
    counts: dict[str, Any] | None = None,
    decimals: int = 6,
) -> Path:
    if len(chunks) != len(vectors):
        raise ValueError(f"got {len(chunks)} chunks but {len(vectors)} vectors; they must match")
    dimensions = {len(vector) for vector in vectors}
    header = dict(counts or {})
    header["vectors"] = len(vectors)
    header["dimensions"] = sorted(dimensions)[0] if len(dimensions) == 1 else "mixed"
    lines = _header("EMBEDDINGS", header)
    for chunk, vector in zip(chunks, vectors):
        norm = sum(float(value) ** 2 for value in vector) ** 0.5
        lines.append(DIVIDER)
        lines.append(f"chunk_id     : {chunk.chunk_id}")
        lines.append(f"source_id    : {chunk.source_id}")
        lines.append(f"scheme_id    : {chunk.scheme_id}")
        lines.append(f"section_title: {chunk.section_title}")
        lines.append(f"dim          : {len(vector)}")
        lines.append(f"l2_norm      : {norm:.6f}")
        lines.append(f"chars        : {len(chunk.text)}")
        lines.append("")
        lines.append("vector:")
        for offset in range(0, len(vector), VALUES_PER_LINE):
            window = vector[offset : offset + VALUES_PER_LINE]
            rendered = " ".join(f"{float(value):+.{decimals}f}" for value in window)
            lines.append(f"  [{offset:>3}] {rendered}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_reports(
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]] | None,
    directory: Path,
    counts: dict[str, Any] | None = None,
) -> list[Path]:
    written = [write_chunks_txt(chunks, directory / "chunks.txt", counts)]
    if vectors is not None:
        written.append(
            write_embeddings_txt(chunks, vectors, directory / "embeddings.txt", counts)
        )
    return written


def iter_chunk_text(chunks: Iterable[Chunk]) -> Iterable[str]:
    for chunk in chunks:
        yield chunk.text
