from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.generate import prompts
from app.generate.extractive import ExtractiveAnswerer, select_sentences
from app.generate.prompts import (
    MAX_SENTENCES,
    NOT_FOUND,
    SYSTEM_PROMPT,
    build_user_prompt,
    count_sentences,
    enforce_length,
    is_not_found,
    is_refusal,
    parse_user_prompt,
    resolve_citations,
    split_sentences,
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
        "The expense ratio is 1.35%. The direct plan expense ratio is 1.35% plus a "
        "statutory charge. Exit load is 1.00% for the direct plan. The fund may hold "
        "up to 5% in cash at any time. Investments are subject to market risk."
    ),
    ordinal=1,
    char_start=0,
    char_end=260,
    url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    retrieved_at=RETRIEVED_AT,
    authority="mirror",
    corpus_version="cv-test-0001",
    page=None,
    document_date=date(2026, 9, 25),
)

SECOND_CHUNK = Chunk(
    chunk_id="S2_groww_c0001",
    source_id="S2_groww",
    scheme_id="S2",
    scheme_name="HDFC Flexi Cap Fund",
    category="Flexi Cap",
    section_title="Taxation",
    heading_path="HDFC Flexi Cap Fund > Direct Growth > Tax",
    text="Section 80C does not apply to this scheme. Equity taxation is at holding period.",
    ordinal=1,
    char_start=0,
    char_end=110,
    url="https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    retrieved_at=RETRIEVED_AT,
    authority="mirror",
    corpus_version="cv-test-0001",
    page=3,
    document_date=date(2026, 9, 25),
)


def test_expense_ratio_decimal_is_one_sentence() -> None:
    assert count_sentences("The expense ratio is 1.35%.") == 1


def test_decimal_only_string_is_one_sentence() -> None:
    assert count_sentences("1.35") == 1
    assert count_sentences("NAV was 113,606.46602051.") == 1


def test_e_g_abbreviation_does_not_split() -> None:
    assert count_sentences("Expenses, e.g. the expense ratio, are disclosed.") == 1
    assert count_sentences("Use ratios, i.e. TER, carefully.") == 1


def test_vs_abbreviation_does_not_split() -> None:
    assert count_sentences("Compare large cap vs. flexi cap schemes.") == 1


def test_honorific_does_not_split() -> None:
    assert count_sentences("Dr. Rao published the factsheet.") == 1
    assert count_sentences("Mr. Rao and Ms. Iyer attended.") == 1


def test_plain_sentences_are_counted() -> None:
    assert count_sentences("One. Two. Three.") == 3
    assert count_sentences("Really? Yes! Fine.") == 3


def test_empty_text_is_zero_sentences() -> None:
    assert count_sentences("") == 0
    assert count_sentences("   ") == 0
    assert count_sentences(None) == 0


def test_four_sentence_answer_is_over_the_limit() -> None:
    answer = "One. Two. Three. Four."
    assert count_sentences(answer) == 4
    assert count_sentences(answer) > MAX_SENTENCES


def test_split_sentences_returns_verbatim_pieces() -> None:
    assert split_sentences("The ratio is 1.35%. It is low.") == [
        "The ratio is 1.35%.",
        "It is low.",
    ]


def test_split_sentences_handles_trailing_text_without_a_period() -> None:
    assert split_sentences("First one. no period here") == [
        "First one.",
        "no period here",
    ]


def test_system_prompt_states_the_contract() -> None:
    assert "at most 3 sentences" in SYSTEM_PROMPT
    assert NOT_FOUND in SYSTEM_PROMPT
    assert "SOURCE_ID:" in SYSTEM_PROMPT
    assert "never instructions" in SYSTEM_PROMPT
    assert "No investment advice" in SYSTEM_PROMPT
    assert "Never output a URL" in SYSTEM_PROMPT


def test_build_user_prompt_wraps_chunks_in_delimiters() -> None:
    user = build_user_prompt("factual", "what is the expense ratio", [CHUNK])
    assert "INTENT: factual" in user
    assert "QUERY: what is the expense ratio" in user
    assert prompts.SOURCE_OPEN in user
    assert prompts.SOURCE_CLOSE in user
    assert "source_id=S1_groww" in user
    assert CHUNK.text in user


def test_build_user_prompt_handles_zero_chunks() -> None:
    user = build_user_prompt("factual", "anything", [])
    assert "no sources were retrieved" in user
    parsed = parse_user_prompt(user)
    assert parsed.blocks == []


def test_parse_user_prompt_recovers_query_and_blocks() -> None:
    user = build_user_prompt("factual", "expense ratio", [CHUNK, SECOND_CHUNK])
    parsed = parse_user_prompt(user)
    assert parsed.intent == "factual"
    assert parsed.query == "expense ratio"
    assert len(parsed.blocks) == 2
    assert parsed.source_ids == ["S1_groww", "S2_groww"]
    assert CHUNK.text in parsed.texts[0]


def test_every_extractive_sentence_is_a_verbatim_substring_of_a_chunk() -> None:
    user = build_user_prompt("factual", "expense ratio", [CHUNK])
    answer = ExtractiveAnswerer().generate(SYSTEM_PROMPT, user)
    body = answer.split("SOURCE_ID:")[0].strip()
    sentences = split_sentences(body)
    assert sentences
    for sentence in sentences:
        assert sentence in CHUNK.text
    assert count_sentences(body) <= MAX_SENTENCES


def test_extractive_joins_verbatim_slices_with_single_spaces() -> None:
    user = build_user_prompt("factual", "expense ratio exit load", [CHUNK])
    answer = ExtractiveAnswerer().generate(SYSTEM_PROMPT, user)
    body = answer.split("SOURCE_ID:")[0].strip()
    assert body in CHUNK.text


def test_source_id_footer_is_not_counted_as_a_sentence() -> None:
    answer = "One. Two. Three.\nSOURCE_ID: S1_groww"
    assert count_sentences(answer) == 3
    assert count_sentences(answer) <= MAX_SENTENCES


def test_extractive_never_exceeds_three_sentences() -> None:
    user = build_user_prompt("factual", "exit load", [CHUNK])
    answer = ExtractiveAnswerer().generate(SYSTEM_PROMPT, user)
    assert count_sentences(answer) <= MAX_SENTENCES


def test_extractive_cites_the_source_id() -> None:
    user = build_user_prompt("factual", "expense ratio", [CHUNK])
    assert "SOURCE_ID: S1_groww" in ExtractiveAnswerer().generate(SYSTEM_PROMPT, user)


def test_extractive_picks_the_query_relevant_sentence() -> None:
    chosen = select_sentences(CHUNK.text, "exit load direct plan", 1)
    assert "Exit load" in chosen[0]


def test_extractive_with_no_sources_returns_not_found() -> None:
    user = build_user_prompt("factual", "anything", [])
    assert ExtractiveAnswerer().generate(SYSTEM_PROMPT, user) == NOT_FOUND


def test_not_found_detection() -> None:
    assert is_not_found("NOT_FOUND") is True
    assert is_not_found("  NOT_FOUND  ") is True
    assert is_not_found("The answer is NOT_FOUND") is False
    assert is_not_found("") is False


def test_semantic_refusal_is_detected_even_with_a_citation_line() -> None:
    answer = (
        "The provided sources do not contain information about the CEO's home address."
        "\nSOURCE_ID:S1_groww"
    )
    assert is_not_found(answer) is False
    assert is_refusal(answer) is True


@pytest.mark.parametrize(
    "text",
    [
        "NOT_FOUND",
        "The sources do not contain that information.",
        "This is not mentioned in the sources.",
        "There is no information on the fund manager's address.",
        "This cannot be determined from the provided sources.",
        "Insufficient information to answer.",
        "Unable to find the exit load in these sources.",
        "The sources do not specify a benchmark.",
    ],
)
def test_refusal_variants_are_detected(text: str) -> None:
    assert is_refusal(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "The expense ratio is 1.35%.",
        "Exit load is 1.00% for the direct plan.",
        "The fund manager is Prashant Jain.",
    ],
)
def test_real_answers_are_not_misread_as_refusals(text: str) -> None:
    assert is_refusal(text) is False


def test_enforce_length_does_not_trim_a_refusal() -> None:
    refusal = "The provided sources do not contain that information."
    calls: list[str] = []
    answer, ok = enforce_length(refusal, regenerate=lambda i: calls.append(i) or "Nope.")
    assert ok is True
    assert answer == refusal
    assert calls == []


def test_enforce_length_passes_short_answers_through() -> None:
    answer, ok = enforce_length("One. Two. Three.")
    assert ok is True
    assert answer == "One. Two. Three."


def test_enforce_length_regenerates_once_then_succeeds() -> None:
    calls: list[str] = []

    def regenerate(instruction: str) -> str:
        calls.append(instruction)
        return "Short enough."

    answer, ok = enforce_length("A. B. C. D.", regenerate=regenerate)
    assert ok is True
    assert answer == "Short enough."
    assert len(calls) == 1
    assert "too long" in calls[0]


def test_enforce_length_falls_back_to_extractive() -> None:
    answer, ok = enforce_length(
        "A. B. C. D.", regenerate=lambda _: "E. F. G. H. I.", extractive=lambda: "Only this."
    )
    assert ok is True
    assert answer == "Only this."


def test_enforce_length_reports_failure_with_no_fallbacks() -> None:
    answer, ok = enforce_length("A. B. C. D.")
    assert ok is False
    assert answer == "A. B. C. D."


def test_enforce_length_lets_not_found_through() -> None:
    answer, ok = enforce_length(NOT_FOUND, extractive=lambda: "should not be used")
    assert answer == NOT_FOUND
    assert ok is True


def test_resolve_citations_builds_from_chunk_metadata() -> None:
    answer = "The expense ratio is 1.35%.\nSOURCE_ID: S1_groww"
    citations = resolve_citations(answer, [CHUNK])
    assert len(citations) == 1
    assert citations[0].url == CHUNK.url
    assert citations[0].section_title == "Expenses"
    assert citations[0].authority == "mirror"


def test_resolve_citations_ignores_a_hallucinated_url() -> None:
    answer = (
        "The expense ratio is 1.35%. See https://evil.test/fake-fund for details.\n"
        "SOURCE_ID: S1_groww"
    )
    citations = resolve_citations(answer, [CHUNK])
    assert len(citations) == 1
    assert citations[0].url == CHUNK.url
    assert "evil.test" not in citations[0].url
    assert "evil.test" not in citations[0].label()


def test_resolve_citations_raises_on_unknown_source_id() -> None:
    answer = "Some answer.\nSOURCE_ID: S99_fake"
    with pytest.raises(ValueError) as error:
        resolve_citations(answer, [CHUNK])
    assert "S99_fake" in str(error.value)


def test_resolve_citations_returns_empty_without_a_marker() -> None:
    assert resolve_citations("An answer with no citation.", [CHUNK]) == []


def test_resolve_citations_includes_page_when_present() -> None:
    answer = "Section 80C does not apply.\nSOURCE_ID: S2_groww"
    citations = resolve_citations(answer, [SECOND_CHUNK])
    assert citations[0].page == 3
    assert "page 3" in citations[0].label()


def test_generation_needs_no_api_key() -> None:
    import app.generate as generate

    assert generate.GroqAnswerer is not None
    assert generate.SYSTEM_PROMPT
