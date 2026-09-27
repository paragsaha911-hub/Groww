from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

import pytest

from app import config
from app.generate.groq import GroqAnswerer, is_retryable
from app.generate.prompts import (
    NOT_FOUND,
    SYSTEM_PROMPT,
    build_user_prompt,
    count_sentences,
    is_refusal,
    resolve_citations,
)
from app.models import Chunk

RETRIEVED_AT = datetime(2026, 9, 25, 4, 0, tzinfo=timezone.utc)

CHUNK = Chunk(
    chunk_id="S1_groww_c0001",
    source_id="S1_groww",
    scheme_id="S1",
    scheme_name="HDFC Large Cap Fund",
    category="Large Cap",
    section_title="Expenses",
    heading_path="HDFC Large Cap Fund > Direct Growth > Fees and Expenses",
    text=(
        "The expense ratio of the direct growth plan is 1.35% of average daily assets. "
        "Exit load is 1.00% for the direct plan."
    ),
    ordinal=1,
    char_start=0,
    char_end=150,
    url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    retrieved_at=RETRIEVED_AT,
    authority="mirror",
    corpus_version="cv-test-0001",
    document_date=date(2026, 9, 25),
)

GROQ_KEY_PRESENT = bool(config.llm_api_key())
needs_key = pytest.mark.skipif(
    not GROQ_KEY_PRESENT, reason="GROQ_API_KEY is not set"
)


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, behaviour: Any) -> None:
        self.behaviour = behaviour
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        result = self.behaviour(len(self.calls))
        if isinstance(result, BaseException):
            raise result
        return FakeResponse(result)


class FakeClient:
    def __init__(self, behaviour: Any) -> None:
        self.completions = FakeCompletions(behaviour)
        self.chat = type("Chat", (), {"completions": self.completions})()


def build(behaviour: Any, **kwargs: Any) -> GroqAnswerer:
    return GroqAnswerer(client=FakeClient(behaviour), sleeper=lambda _: None, **kwargs)


def user_prompt() -> str:
    return build_user_prompt("factual", "what is the expense ratio", [CHUNK])


def test_request_payload_has_no_sampling_keys() -> None:
    answerer = build(lambda _: "The expense ratio is 1.35%.")
    answerer.generate(SYSTEM_PROMPT, user_prompt())
    payload = answerer.client.completions.calls[0]
    for banned in ("temperature", "top_p", "top_k", "seed", "presence_penalty"):
        assert banned not in payload
    assert payload["model"] == config.LLM_MODEL
    assert payload["max_tokens"] == config.LLM_MAX_TOKENS
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"


def test_successful_call_records_groq_as_the_generator() -> None:
    answerer = build(lambda _: "The expense ratio is 1.35%.")
    answer = answerer.generate(SYSTEM_PROMPT, user_prompt())
    assert answer == "The expense ratio is 1.35%."
    assert answerer.served_by == "groq"
    assert answerer.attempts == 1
    assert answerer.last_error is None


def test_timeout_is_retried_once_then_falls_back() -> None:
    def behaviour(call: int) -> Any:
        if call == 1:
            return TimeoutError("timed out")
        return "recovered answer."

    answerer = build(behaviour)
    answer = answerer.generate(SYSTEM_PROMPT, user_prompt())
    assert answer == "recovered answer."
    assert answerer.attempts == 2
    assert answerer.served_by == "groq"


def test_repeated_timeout_falls_back_to_extractive() -> None:
    answerer = build(lambda _: TimeoutError("timed out"))
    answer = answerer.generate(SYSTEM_PROMPT, user_prompt())
    assert answerer.served_by == "extractive"
    assert "SOURCE_ID: S1_groww" in answer
    assert count_sentences(answer) <= 3
    assert answerer.last_error
    assert "TimeoutError" in answerer.last_error


def test_non_retryable_error_falls_back_without_retrying() -> None:
    answerer = build(lambda _: ValueError("bad request"))
    answerer.generate(SYSTEM_PROMPT, user_prompt())
    assert answerer.attempts == 1
    assert answerer.served_by == "extractive"
    assert len(answerer.client.completions.calls) == 1


def test_fallback_error_is_recorded_in_the_trace() -> None:
    answerer = build(lambda _: TimeoutError("nope"))
    answerer.generate(SYSTEM_PROMPT, user_prompt())
    assert answerer.served_by != "groq"
    assert answerer.last_error is not None


def test_is_retryable_classification() -> None:
    assert is_retryable(TimeoutError("x")) is True
    assert is_retryable(ConnectionError("x")) is True
    assert is_retryable(ValueError("x")) is False


def test_model_is_configurable() -> None:
    answerer = build(lambda _: "ok", model="openai/gpt-oss-20b")
    answerer.generate(SYSTEM_PROMPT, user_prompt())
    assert answerer.client.completions.calls[0]["model"] == "openai/gpt-oss-20b"


def test_regenerate_short_appends_the_trim_instruction() -> None:
    answerer = build(lambda _: "Short.")
    answerer.regenerate_short(SYSTEM_PROMPT, user_prompt(), "Trim it.")
    sent = answerer.client.completions.calls[0]["messages"][1]["content"]
    assert sent.endswith("Trim it.")


def test_resolve_citations_ignores_a_hallucinated_url() -> None:
    answer = (
        "The expense ratio is 1.35%, see https://evil.test/fake.\nSOURCE_ID: S1_groww"
    )
    citations = resolve_citations(answer, [CHUNK])
    assert citations[0].url == CHUNK.url
    assert "evil.test" not in citations[0].label()


def test_resolve_citations_raises_on_unknown_source_id() -> None:
    with pytest.raises(ValueError):
        resolve_citations("Answer.\nSOURCE_ID: S99_nope", [CHUNK])


def test_not_found_is_passed_through_untouched() -> None:
    answerer = build(lambda _: NOT_FOUND)
    assert answerer.generate(SYSTEM_PROMPT, user_prompt()) == NOT_FOUND


def numbers_in(text: str) -> set[str]:
    prose = re.sub(r"^[ \t]*SOURCE_ID:.*$", "", text or "", flags=re.MULTILINE)
    return set(re.findall(r"\d+(?:\.\d+)?", prose))


@needs_key
@pytest.mark.llm
def test_live_groq_call_answers_from_sources() -> None:
    answerer = GroqAnswerer()
    prompt = build_user_prompt("factual", "what is the expense ratio", [CHUNK])
    answer = answerer.generate(SYSTEM_PROMPT, prompt)
    assert answerer.served_by == "groq"
    assert answer
    assert answer != NOT_FOUND
    citations = resolve_citations(answer, [CHUNK])
    assert citations and citations[0].url == CHUNK.url
    assert count_sentences(answer) <= 3
    assert "1.35" in answer
    assert numbers_in(answer) <= numbers_in(CHUNK.text)


@needs_key
@pytest.mark.llm
def test_live_groq_call_refuses_when_sources_do_not_answer() -> None:
    answerer = GroqAnswerer()
    prompt = build_user_prompt(
        "factual", "what is the CEO's home address", [CHUNK]
    )
    answer = answerer.generate(SYSTEM_PROMPT, prompt)
    assert is_refusal(answer), f"expected a refusal, got: {answer!r}"


@needs_key
@pytest.mark.llm
def test_live_groq_echoes_no_numbers_it_was_not_given() -> None:
    answerer = GroqAnswerer()
    prompt = build_user_prompt("factual", "what is the AUM", [CHUNK])
    answer = answerer.generate(SYSTEM_PROMPT, prompt)
    assert "1.35" not in answer or "AUM" not in answer


@needs_key
@pytest.mark.llm
@pytest.mark.slow
def test_live_end_to_end_answer_invents_no_numbers() -> None:
    from app.retrieve.retriever import HybridRetriever

    retriever = HybridRetriever()
    result = retriever.retrieve("what is the expense ratio of HDFC Large Cap Fund")
    assert result.passed_floor is True
    chunks = [item.chunk for item in result.chunks]
    answerer = GroqAnswerer()
    answer = answerer.generate(
        SYSTEM_PROMPT, build_user_prompt("factual", result.query, chunks)
    )
    assert answerer.served_by == "groq"
    assert count_sentences(answer) <= 3
    resolve_citations(answer, chunks)
    grounded = set().union(*(numbers_in(chunk.text) for chunk in chunks))
    assert numbers_in(answer) <= grounded


@needs_key
@pytest.mark.llm
@pytest.mark.slow
def test_live_end_to_end_never_emits_a_url() -> None:
    from app.retrieve.retriever import HybridRetriever

    retriever = HybridRetriever()
    result = retriever.retrieve("what is the exit load of HDFC Large Cap Fund")
    if not result.passed_floor:
        pytest.skip("floor rejected the query")
    chunks = [item.chunk for item in result.chunks]
    answer = GroqAnswerer().generate(
        SYSTEM_PROMPT, build_user_prompt("factual", result.query, chunks)
    )
    assert "http" not in answer.lower()
