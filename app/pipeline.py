from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from app import config
from app.generate.extractive import ExtractiveAnswerer
from app.generate.groq import GroqAnswerer
from app.generate.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
    count_sentences,
    enforce_length,
    is_refusal,
    resolve_citations,
    strip_source_markers,
)
from app.guardrails import intent as intent_router
from app.guardrails.pii import scan as pii_scan
from app.guardrails.pii import scrub as pii_scrub
from app.models import (
    AUTHORITY_OFFICIAL,
    Citation,
    QueryResult,
    ScoredChunk,
    TraceRecord,
    utcnow,
)
from app.retrieve.retriever import HybridRetriever

TRACES_PATH = config.EVAL_DIR / "traces.jsonl"
REDACTED_PREVIEW_CHARS = 48
MAX_ANSWER_SENTENCES = 3

REFUSAL_ADVICE = (
    "I only share published facts and do not give investment advice. To weigh this "
    "yourself, read the official scheme documents: {educational}"
)
REFUSAL_PERFORMANCE = (
    "I do not state or compare returns. The official factsheet carries the scheme's "
    "published performance: {factsheet}"
)
REFUSAL_OUT_OF_SCOPE = (
    "I only cover HDFC AMC's Large Cap, Flexi Cap, ELSS, Small Cap and Balanced "
    "Advantage funds. Sources: {sources}"
)
REFUSAL_NPI = (
    "I can't accept personal identifiers such as PAN, Aadhaar, account numbers, OTPs, "
    "email addresses or phone numbers. Please re-ask without them."
)
REFUSAL_NOT_FOUND = (
    "I could not find that in my sources. Closest matches: {sections}. Try asking about "
    "expense ratio, exit load, minimum SIP, lock-in, riskometer or benchmark."
)

EDUCATIONAL_URL = "https://www.hdfcfund.com/mutual-funds"
SOURCES_URL = config.OFFICIAL_FACTSHEET_INDEX_URL

REFUSAL_COPY = {
    "npi": REFUSAL_NPI,
    "advice": REFUSAL_ADVICE,
    "performance": REFUSAL_PERFORMANCE,
    "out_of_scope": REFUSAL_OUT_OF_SCOPE,
    "not_found": REFUSAL_NOT_FOUND,
}


@dataclass
class _Context:
    query: str
    query_sha256: str
    pii_detected: list[str] = field(default_factory=list)
    intent: str = ""
    candidates: list[ScoredChunk] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    answer: str = ""
    generator: str = "none"
    authority: str = AUTHORITY_OFFICIAL
    refused: bool = False
    refusal_kind: str | None = None
    nearest: Any = None

    @property
    def chunks(self) -> list[Any]:
        return [item.chunk for item in self.candidates]

    @property
    def sections(self) -> list[str]:
        seen: list[str] = []
        for chunk in (*self.chunks, self.nearest):
            title = getattr(chunk, "section_title", "")
            if title and title not in seen:
                seen.append(title)
        return seen


def query_hash(query: str) -> str:
    return sha256((query or "").encode("utf-8")).hexdigest()


def redacted_preview(query: str) -> str:
    collapsed = " ".join(pii_scrub(query or "").split())
    if len(collapsed) <= REDACTED_PREVIEW_CHARS:
        return collapsed
    return collapsed[:REDACTED_PREVIEW_CHARS] + "..."


def refusal_copy(refusal_kind: str, sections: Sequence[str] | None = None) -> str:
    template = REFUSAL_COPY.get(refusal_kind, REFUSAL_NOT_FOUND)
    listed = [section for section in (sections or []) if section]
    return template.format(
        educational=EDUCATIONAL_URL,
        factsheet=config.OFFICIAL_FACTSHEET_URL,
        sources=SOURCES_URL,
        sections=", ".join(listed[:2]) if listed else "none",
    )


def append_trace(record: TraceRecord, path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else TRACES_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(record.to_json_line() + "\n")


def freshness_date(
    citations: Sequence[Citation], candidates: Sequence[ScoredChunk]
) -> date | None:
    stamps = [item.chunk.retrieved_at for item in candidates if item.chunk.retrieved_at]
    if not stamps:
        return None
    if citations:
        cited = {citation.source_id for citation in citations}
        scoped = [
            item.chunk.retrieved_at
            for item in candidates
            if item.chunk.retrieved_at and item.chunk.source_id in cited
        ]
        if scoped:
            return max(scoped).date()
    return max(stamps).date()


def build_trace(
    context: _Context,
    latency_ms: int,
    corpus_version: str,
    sentence_count: int,
) -> TraceRecord:
    return TraceRecord(
        ts=utcnow(),
        query_sha256=context.query_sha256,
        query_redacted=redacted_preview(context.query),
        pii_detected=list(context.pii_detected),
        intent=context.intent,
        retrieved=[item.to_trace() for item in context.candidates],
        answer=context.answer,
        citations=[
            {
                "source_id": citation.source_id,
                "url": citation.url,
                "section": citation.section_title,
                "authority": citation.authority,
                "page": citation.page,
            }
            for citation in context.citations
        ],
        sentence_count=sentence_count,
        generator=context.generator,
        embed_model=config.EMBED_MODEL,
        authority=context.authority,
        corpus_version=corpus_version,
        latency_ms=latency_ms,
        refused=context.refused,
        refusal_kind=context.refusal_kind,
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _finish(
    context: _Context,
    started: float,
    traces_path: str | Path | None = None,
) -> None:
    append_trace(
        build_trace(
            context,
            _elapsed_ms(started),
            config.corpus_version(),
            count_sentences(context.answer) if context.answer else 0,
        ),
        traces_path,
    )


def _refuse(
    context: _Context,
    refusal_kind: str,
    started: float,
    traces_path: str | Path | None = None,
) -> QueryResult:
    context.refused = True
    context.refusal_kind = refusal_kind
    context.generator = "none"
    context.answer = refusal_copy(refusal_kind, context.sections)
    _finish(context, started, traces_path)
    return QueryResult(
        answer=context.answer,
        intent=context.intent,
        refused=True,
        refusal_kind=refusal_kind,
        sentences=[],
        citations=[],
        freshness_date=freshness_date([], context.candidates),
        authority=context.authority,
        generator=context.generator,
        latency_ms=_elapsed_ms(started),
        trace_id=context.query_sha256[:16],
    )


def get_retriever() -> Any:
    return _retriever()


@lru_cache(maxsize=1)
def _retriever() -> Any:
    return HybridRetriever()


def _select_answerer(offline: bool, answerer: Any) -> Any:
    if answerer is not None:
        return answerer
    if offline or not config.llm_api_key():
        return ExtractiveAnswerer()
    return GroqAnswerer()


def load_trace(trace_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    target = Path(path) if path is not None else TRACES_PATH
    if not target.exists():
        return None
    for line in reversed(target.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        digest = str(record.get("query_sha256", ""))
        if digest and trace_id and digest.startswith(str(trace_id)[:16]):
            return record
    return None


def answer_question(
    query: str,
    debug: bool = False,
    offline: bool = False,
    retriever: Any = None,
    answerer: Any = None,
    traces_path: str | Path | None = None,
) -> QueryResult:
    started = time.perf_counter()
    raw_query = query or ""

    context = _Context(query=raw_query, query_sha256=query_hash(raw_query))

    pii = pii_scan(raw_query)
    context.pii_detected = list(pii.detected)
    if pii.has_pii:
        context.intent = "npi"
        return _refuse(context, "npi", started, traces_path)

    intent = intent_router.classify(raw_query, pii_hit=False)
    context.intent = intent.intent
    if intent.intent in ("advice", "performance", "out_of_scope"):
        return _refuse(context, intent.intent, started, traces_path)

    scrubbed = pii_scrub(raw_query)
    active_retriever = retriever if retriever is not None else get_retriever()
    retrieval = active_retriever.retrieve(scrubbed, config.TOP_K)
    context.candidates = list(retrieval.candidates or [])

    if not context.candidates or not getattr(retrieval, "passed_floor", False):
        context.nearest = getattr(retrieval, "nearest", None)
        return _refuse(context, "not_found", started, traces_path)

    active_answerer = _select_answerer(offline, answerer)
    is_groq = getattr(active_answerer, "name", "") == "groq"
    context.generator = (
        f"groq:{config.llm_model(config.LLM_MODEL)}" if is_groq else "extractive"
    )

    user_prompt = build_user_prompt(intent.intent, scrubbed, context.chunks)
    raw_answer = active_answerer.generate(SYSTEM_PROMPT, user_prompt)

    answer, shortened = enforce_length(
        raw_answer,
        max_sentences=MAX_ANSWER_SENTENCES,
        regenerate=(
            None
            if not hasattr(active_answerer, "regenerate_short")
            else (
                lambda instruction: active_answerer.regenerate_short(
                    SYSTEM_PROMPT, user_prompt, instruction
                )
            )
        ),
        extractive=lambda: ExtractiveAnswerer().generate(SYSTEM_PROMPT, user_prompt),
    )
    if shortened:
        context.generator = f"{context.generator}+shortened"
    context.answer = answer.strip()

    if is_refusal(context.answer):
        return _refuse(context, "not_found", started, traces_path)

    context.citations = resolve_citations(context.answer, context.chunks)
    if context.citations:
        context.authority = context.citations[0].authority

    context.answer = strip_source_markers(context.answer)

    _finish(context, started, traces_path)
    return QueryResult(
        answer=context.answer,
        intent=context.intent,
        refused=False,
        refusal_kind=None,
        sentences=[],
        citations=list(context.citations),
        freshness_date=freshness_date(context.citations, context.candidates),
        authority=context.authority,
        generator=context.generator,
        latency_ms=_elapsed_ms(started),
        trace_id=context.query_sha256[:16],
    )
