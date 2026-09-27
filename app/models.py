from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

AUTHORITY_OFFICIAL = "official"
AUTHORITY_MIRROR = "mirror"

EXTRACTION_METHODS = ("pdf", "static", "mirror", "manual")

INTENTS = (
    "npi",
    "advice",
    "performance",
    "out_of_scope",
    "factual",
    "comparative_factual",
    "not_found",
)

TRACE_KEY_ORDER = (
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
    "refusal_kind",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_date(value: datetime) -> str:
    return as_utc(value).date().isoformat()


def approx_token_count(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def make_chunk_id(source_id: str, ordinal: int) -> str:
    if ordinal < 0:
        raise ValueError(f"ordinal must be non-negative, got {ordinal}")
    return f"{source_id}_c{ordinal:04d}"


def freshness_date_from(values: list[datetime]) -> date | None:
    if not values:
        return None
    return max(as_utc(v) for v in values).date()


@dataclass
class Scheme:
    scheme_id: str
    name: str
    category: str
    plan: str
    url: str


@dataclass
class Document:
    source_id: str
    scheme_id: str
    url: str
    title: str
    source_type: str
    authority: str
    extraction_method: str
    retrieved_at: datetime
    content_hash: str
    document_date: date | None = None
    fields: dict[str, str] = field(default_factory=dict)
    is_complete: bool = True
    text: str = ""
    sections: list[Section] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.retrieved_at = as_utc(self.retrieved_at)


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    scheme_id: str
    scheme_name: str
    category: str
    section_title: str
    heading_path: str
    text: str
    ordinal: int
    char_start: int
    char_end: int
    url: str
    retrieved_at: datetime
    authority: str
    corpus_version: str
    page: int | None = None
    token_count: int = 0
    document_date: date | None = None

    def __post_init__(self) -> None:
        self.retrieved_at = as_utc(self.retrieved_at)
        if self.token_count == 0:
            self.token_count = approx_token_count(self.text)

    @classmethod
    def from_document(
        cls,
        doc: Document,
        ordinal: int,
        text: str,
        section_title: str,
        heading_path: str,
        scheme_name: str,
        category: str,
        char_start: int,
        char_end: int,
        corpus_version: str,
        page: int | None = None,
    ) -> "Chunk":
        return cls(
            chunk_id=make_chunk_id(doc.source_id, ordinal),
            source_id=doc.source_id,
            scheme_id=doc.scheme_id,
            scheme_name=scheme_name,
            category=category,
            section_title=section_title,
            heading_path=heading_path,
            text=text,
            ordinal=ordinal,
            char_start=char_start,
            char_end=char_end,
            url=doc.url,
            retrieved_at=doc.retrieved_at,
            authority=doc.authority,
            corpus_version=corpus_version,
            page=page,
            document_date=doc.document_date,
        )


@dataclass
class Section:
    title: str
    level: int
    text: str
    heading_path: str
    char_start: int
    char_end: int
    page: int | None = None
    ordinal: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "level": self.level,
            "text": self.text,
            "heading_path": self.heading_path,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page": self.page,
            "ordinal": self.ordinal,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Section":
        return cls(
            title=payload["title"],
            level=int(payload["level"]),
            text=payload.get("text", ""),
            heading_path=payload.get("heading_path", ""),
            char_start=int(payload.get("char_start", 0)),
            char_end=int(payload.get("char_end", 0)),
            page=payload.get("page"),
            ordinal=int(payload.get("ordinal", 0)),
        )


@dataclass
class ParsedDocument:
    text: str
    sections: list[Section] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    is_complete: bool = True
    extraction_method: str = "static"
    document_date: str | None = None

    def section_titles(self) -> list[str]:
        return [section.title for section in self.sections]

    def section_by_title(self, title: str) -> Section | None:
        for section in self.sections:
            if section.title == title:
                return section
        return None


@dataclass
class Citation:
    source_id: str
    url: str
    section_title: str
    authority: str
    page: int | None = None

    def label(self) -> str:
        parts = [p for p in (self.section_title,) if p]
        if self.page is not None:
            parts.append(f"page {self.page}")
        detail = ", ".join(parts)
        return f"{self.url} ({detail})" if detail else self.url


@dataclass
class ScoredChunk:
    chunk: Chunk
    rank: int
    fused_score: float
    cosine_score: float
    lexical_score: float = 0.0
    rerank_score: float = 0.0
    best_score: float = 0.0

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    def to_trace(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "chunk_id": self.chunk.chunk_id,
            "score": round(self.best_score or self.fused_score, 4),
            "fused_score": round(self.fused_score, 4),
            "cosine_score": round(self.cosine_score, 4),
            "lexical_score": round(self.lexical_score, 4),
            "rerank_score": round(self.rerank_score, 4),
            "best_score": round(self.best_score, 4),
            "scheme_id": self.chunk.scheme_id,
            "section": self.chunk.section_title,
        }


@dataclass
class RetrievalResult:
    query: str
    intent: str = ""
    candidates: list[ScoredChunk] = field(default_factory=list)
    chunks: list[ScoredChunk] = field(default_factory=list)
    best_score: float = 0.0
    floor: float = 0.0
    passed_floor: bool = False
    scheme_filter: str | None = None
    reranked: bool = False
    reranker: str = ""
    lexical_backend: str = ""
    pii_detected: bool = False
    nearest: list[ScoredChunk] = field(default_factory=list)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    def to_trace(self) -> list[dict[str, Any]]:
        return [chunk.to_trace() for chunk in self.chunks]


@dataclass
class QueryResult:
    answer: str
    intent: str
    refused: bool = False
    refusal_kind: str | None = None
    sentences: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    freshness_date: date | None = None
    authority: str = AUTHORITY_OFFICIAL
    generator: str = ""
    latency_ms: int = 0
    trace_id: str = ""

    def render_plain(self) -> str:
        lines = [self.answer.rstrip()]
        lines.extend(f"Source: {citation.label()}" for citation in self.citations)
        if self.freshness_date is not None:
            lines.append(f"Last updated from sources: {self.freshness_date.isoformat()}")
        return "\n".join(lines)


@dataclass
class TraceRecord:
    ts: datetime
    query_sha256: str
    query_redacted: str
    pii_detected: list[str]
    intent: str
    retrieved: list[dict[str, Any]]
    answer: str
    citations: list[dict[str, Any]]
    sentence_count: int
    generator: str
    embed_model: str
    authority: str
    corpus_version: str
    latency_ms: int
    refused: bool
    refusal_kind: str | None = None

    def __post_init__(self) -> None:
        self.ts = as_utc(self.ts)

    def to_json_line(self) -> str:
        payload: dict[str, Any] = {
            "ts": self.ts.isoformat(),
            "query_sha256": self.query_sha256,
            "query_redacted": self.query_redacted,
            "pii_detected": list(self.pii_detected),
            "intent": self.intent,
            "retrieved": self.retrieved,
            "answer": self.answer,
            "citations": self.citations,
            "sentence_count": self.sentence_count,
            "generator": self.generator,
            "embed_model": self.embed_model,
            "authority": self.authority,
            "corpus_version": self.corpus_version,
            "latency_ms": self.latency_ms,
            "refused": self.refused,
            "refusal_kind": self.refusal_kind,
        }
        ordered = {key: payload[key] for key in TRACE_KEY_ORDER}
        return json.dumps(ordered, ensure_ascii=False)
