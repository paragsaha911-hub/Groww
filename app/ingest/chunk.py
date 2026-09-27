from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from app import config
from app.models import Chunk, Document, approx_token_count

TABLE_ROW = re.compile(r"\s\|\s")


@runtime_checkable
class Chunker(Protocol):
    name: str

    def split(self, doc: Document) -> list[Chunk]: ...


def table_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    end = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        is_row = bool(TABLE_ROW.search(line))
        if is_row:
            if start is None:
                start = offset
            end = offset + len(line.rstrip("\r\n"))
        elif start is not None:
            spans.append((start, end))
            start = None
        offset += len(line)
    if start is not None:
        spans.append((start, end))
    return spans


def protect_tables(text: str, start: int, end: int) -> int:
    for span_start, span_end in table_spans(text):
        if span_start < end < span_end:
            end = span_end
    return end


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if end <= start:
            continue
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def section_at(sections: list[Any], position: int) -> Any | None:
    for section in sections:
        if section.char_start <= position < section.char_end:
            return section
    if sections and position >= sections[-1].char_end:
        return sections[-1]
    return sections[0] if sections else None


def _make_chunks(
    doc: Document,
    spans: list[tuple[int, int]],
    corpus_version: str,
) -> list[Chunk]:
    scheme = config.scheme_by_id(doc.scheme_id)
    scheme_name = scheme.name if scheme else doc.scheme_id
    category = scheme.category if scheme else ""
    chunks: list[Chunk] = []
    for ordinal, (start, end) in enumerate(spans, start=1):
        if end <= start:
            continue
        section = section_at(doc.sections, start)
        text = doc.text[start:end].strip()
        if not text:
            continue
        chunks.append(
            Chunk.from_document(
                doc,
                ordinal=ordinal,
                text=text,
                section_title=section.title if section else "",
                heading_path=section.heading_path if section else "",
                scheme_name=scheme_name,
                category=category,
                char_start=start,
                char_end=end,
                corpus_version=corpus_version,
                page=section.page if section else None,
            )
        )
    return chunks


class SizedChunker:
    def __init__(self, chunk_size: int | None = None, overlap: int | None = None) -> None:
        self.chunk_size = chunk_size or config.CHUNK_SIZE
        self.overlap = config.CHUNK_OVERLAP if overlap is None else overlap

    @property
    def char_budget(self) -> int:
        return max(1, self.chunk_size) * 4

    @property
    def step_chars(self) -> int:
        budget = self.char_budget
        overlap = min(max(0, self.overlap) * 4, max(0, budget // 2))
        return max(1, budget - overlap)


class FixedWindowChunker(SizedChunker):
    name = "C1"

    def split(self, doc: Document) -> list[Chunk]:
        text = doc.text
        if not text.strip():
            return []
        window_chars = self.char_budget
        step_chars = self.step_chars
        spans: list[tuple[int, int]] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(length, start + window_chars)
            if end < length:
                end = protect_tables(text, start, end)
                if end >= length:
                    end = length
            spans.append((start, end))
            if end >= length:
                break
            start += step_chars
        return _make_chunks(doc, spans, config.corpus_version())


class RecursiveCharChunker(SizedChunker):
    name = "C2"
    SEPARATORS = ("\n## ", "\n\n", ". ", " ")

    def _split(self, text: str, start_offset: int, out: list[tuple[int, int]], depth: int = 0) -> None:
        limit = self.char_budget
        if len(text) <= limit:
            out.append((start_offset, start_offset + len(text)))
            return
        if depth >= len(self.SEPARATORS):
            step = self.step_chars
            position = 0
            while position < len(text):
                end = min(len(text), position + limit)
                if end < len(text):
                    end = protect_tables(text, start_offset + position, start_offset + end)
                out.append((start_offset + position, start_offset + end))
                if end >= len(text):
                    return
                position += step
            return
        separator = self.SEPARATORS[depth]
        if separator not in text:
            self._split(text, start_offset, out, depth + 1)
            return
        raw = text.split(separator)
        spans: list[tuple[int, int]] = []
        cursor = 0
        for index, piece in enumerate(raw):
            start = cursor
            end = cursor + len(piece)
            cursor = end + len(separator)
            if index < len(raw) - 1:
                end += len(separator)
            if end > start:
                spans.append((start, end))
        if not spans:
            self._split(text, start_offset, out, depth + 1)
            return

        group: list[tuple[int, int]] = []
        group_len = 0

        def flush_group() -> None:
            nonlocal group, group_len
            if not group:
                return
            out.append((group[0][0], group[-1][1]))
            group = []
            group_len = 0

        for span in spans:
            span_len = span[1] - span[0]
            if group and group_len + span_len > limit:
                flush_group()
            if span_len > limit:
                self._split(
                    text[span[0] : span[1]], start_offset + span[0], out, depth + 1
                )
                continue
            group.append(span)
            group_len += span_len
        flush_group()

    def split(self, doc: Document) -> list[Chunk]:
        if not doc.text.strip():
            return []
        out: list[tuple[int, int]] = []
        self._split(doc.text, 0, out)
        cleaned: list[tuple[int, int]] = []
        for start, end in out:
            if end <= start:
                continue
            cleaned.append((start, protect_tables(doc.text, start, end)))
        return _make_chunks(doc, merge_spans(cleaned), config.corpus_version())


class HeadingAwareChunker(SizedChunker):
    name = "C3"

    def _roots(self, sections: list[Any]) -> list[str]:
        roots: list[str] = []
        current = ""
        for section in sections:
            if section.level <= 1:
                current = section.title
            if not current:
                current = section.title
            roots.append(current)
        return roots

    def _window(self, text: str, start: int, end: int) -> list[tuple[int, int]]:
        limit = self.char_budget
        step = self.step_chars
        spans: list[tuple[int, int]] = []
        cursor = start
        while cursor < end:
            stop = min(end, cursor + limit)
            if stop < end:
                grown = protect_tables(text, cursor, stop)
                stop = min(end, grown) if grown > cursor else stop
            if stop <= cursor:
                stop = min(end, cursor + limit)
            spans.append((cursor, stop))
            if stop >= end:
                break
            cursor += step
        return spans

    def split(self, doc: Document) -> list[Chunk]:
        sections = [section for section in doc.sections if section.text.strip()]
        if not sections:
            return FixedWindowChunker(self.chunk_size, self.overlap).split(doc)

        budget = self.char_budget
        roots = self._roots(sections)
        spans: list[tuple[int, int]] = []
        windows: list[tuple[int, int]] = []
        group: list[Any] = []
        group_chars = 0
        group_root: str | None = None

        def emit(start: int, end: int) -> None:
            if end > start:
                spans.append((start, end))

        def flush() -> None:
            nonlocal group, group_chars
            if not group:
                return
            start = group[0].char_start
            end = group[-1].char_end
            if end - start > budget and len(group) == 1:
                windows.extend(self._window(doc.text, start, end))
            else:
                emit(start, end)
            group = []
            group_chars = 0

        for section, root in zip(sections, roots):
            section_chars = section.char_end - section.char_start
            if group and (root != group_root or group_chars + section_chars > budget):
                flush()
                group_root = root
            elif not group:
                group_root = root
            group.append(section)
            group_chars += section_chars
        flush()

        last = sections[-1].char_end
        if not spans and not windows:
            emit(sections[0].char_start, last)

        protected = [
            (start, protect_tables(doc.text, start, end)) for start, end in spans
        ]
        return _make_chunks(
            doc, merge_spans(protected) + windows, config.corpus_version()
        )


class SectionChunker:
    name = "C4"

    def split(self, doc: Document) -> list[Chunk]:
        if not doc.sections:
            return FixedWindowChunker().split(doc)
        spans = [
            (section.char_start, section.char_end)
            for section in doc.sections
            if section.text.strip()
        ]
        return _make_chunks(doc, spans, config.corpus_version())


CHUNKERS: dict[str, type] = {
    "C1": FixedWindowChunker,
    "C2": RecursiveCharChunker,
    "C3": HeadingAwareChunker,
    "C4": SectionChunker,
}


def get_chunker(name: str | None = None, **kwargs: Any) -> Chunker:
    key = (name or config.CHUNKER).upper()
    if key not in CHUNKERS:
        raise ValueError(f"unknown chunker {key!r}; expected one of {sorted(CHUNKERS)}")
    factory = CHUNKERS[key]
    if key in ("C1", "C2", "C3"):
        return factory(**kwargs)
    return factory()
