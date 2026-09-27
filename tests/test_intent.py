from __future__ import annotations

import pytest

from app.guardrails.intent import (
    INTENT_ADVICE,
    INTENT_COMPARATIVE_FACTUAL,
    INTENT_FACTUAL,
    INTENT_NPI,
    INTENT_OUT_OF_SCOPE,
    INTENT_PERFORMANCE,
    RULES,
    IntentResult,
    classify,
)

ADVICE_PROBES = [
    "Should I buy HDFC Small Cap Fund?",
    "Should I sell my HDFC Flexi Cap Fund?",
    "Is HDFC ELSS a nice one to hold?",
    "my friend says I should add this, what do you think?",
    "which fund should I choose for the next 5 years?",
    "suggest a good HDFC scheme for me",
    "recommend a scheme for my portfolio",
    "how should I allocate my money across HDFC funds?",
    "is now a good time to invest in HDFC Large Cap?",
    "what is the right timing to buy HDFC ELSS?",
    "I want to start an SIP, which scheme is suitable?",
    "should I switch from HDFC Flexi Cap to HDFC Small Cap?",
    "help me choose between Large Cap and Small Cap for me",
    "is HDFC Balanced Advantage a good fit for my goals?",
    "what do you think about HDFC Large Cap Fund?",
    "is this fund worth investing in for the long term?",
    "would you advise holding this scheme?",
    "tell me which scheme is best for me personally",
    "I have 5 lakhs, where should I put it?",
    "should my parents buy this ELSS?",
    "any advice on which HDFC scheme to buy for a child?",
    "what's your opinion on HDFC Flexi Cap Fund?",
    "how do I build a portfolio with these schemes?",
    "should I invest lump sum or via SIP in HDFC Large Cap?",
]

PERFORMANCE_PROBES = [
    "which of these grew most last year?",
    "what is the 3-year return?",
    "what are the 1-year returns of HDFC Large Cap Fund?",
    "how has HDFC Flexi Cap performed?",
    "what is the NAV history of HDFC ELSS?",
    "which scheme has the best performing track record?",
    "what is the XIRR of HDFC Small Cap?",
    "what is the alpha of this fund?",
    "which is the top performer among HDFC schemes?",
    "has HDFC Large Cap outperformed its benchmark?",
    "what has this fund earned so far?",
    "what is the return since inception?",
    "which fund gave the highest gain?",
    "how much profit did HDFC Flexi Cap make last year?",
    "is HDFC Large Cap beating the NIFTY 50?",
    "what is the annualized return?",
    "which one should have performed better?",
    "tell me the performance of the ELSS tax saver fund",
]

OUT_OF_SCOPE_PROBES = [
    "what is the weather in mumbai tomorrow?",
    "write a python function to reverse a string",
    "tell me about Mirae Asset Large Cap Fund",
    "who won the 1998 world cup?",
    "what is the capital of France?",
    "tell me about SBI Bluechip Fund",
    "translate this sentence to Spanish",
    "what time does the market open in London?",
]

REFERENCE_QUESTIONS = [
    "What is the expense ratio of HDFC Large Cap Fund?",
    "Is there an exit load on HDFC ELSS Tax Saver Fund?",
    "What is the minimum SIP amount for HDFC Small Cap Fund?",
    "What is the lock-in period for the HDFC ELSS Tax Saver Fund?",
    "What is the riskometer level of HDFC Balanced Advantage Fund?",
    "What is the benchmark of HDFC Equity (Flexi Cap) Fund?",
    "How do I download my capital gains statement?",
]


def test_rules_table_is_exported() -> None:
    assert isinstance(RULES, list)
    assert RULES[0][0] == INTENT_NPI
    assert [rule[0] for rule in RULES] == [
        INTENT_NPI,
        INTENT_ADVICE,
        INTENT_PERFORMANCE,
        INTENT_OUT_OF_SCOPE,
        INTENT_FACTUAL,
    ]


def test_evaluation_order_is_fixed() -> None:
    order = [rule[0] for rule in RULES]
    assert order.index(INTENT_ADVICE) < order.index(INTENT_PERFORMANCE)
    assert order.index(INTENT_PERFORMANCE) < order.index(INTENT_OUT_OF_SCOPE)
    assert order.index(INTENT_OUT_OF_SCOPE) < order.index(INTENT_FACTUAL)


@pytest.mark.parametrize("probe", ADVICE_PROBES)
def test_advice_probes_never_reach_factual(probe: str) -> None:
    result = classify(probe)
    assert result.intent == INTENT_ADVICE, f"{probe!r} -> {result.intent}"


@pytest.mark.parametrize("probe", PERFORMANCE_PROBES)
def test_performance_probes_never_reach_factual(probe: str) -> None:
    result = classify(probe)
    assert result.intent == INTENT_PERFORMANCE, f"{probe!r} -> {result.intent}"


@pytest.mark.parametrize("probe", OUT_OF_SCOPE_PROBES)
def test_out_of_scope_probes_are_rejected(probe: str) -> None:
    result = classify(probe)
    assert result.intent == INTENT_OUT_OF_SCOPE, f"{probe!r} -> {result.intent}"


@pytest.mark.parametrize("probe", REFERENCE_QUESTIONS)
def test_reference_questions_are_factual(probe: str) -> None:
    result = classify(probe)
    assert result.intent in (INTENT_FACTUAL, INTENT_COMPARATIVE_FACTUAL), (
        f"{probe!r} -> {result.intent}"
    )


def test_advice_probes_count_meets_the_release_gate() -> None:
    assert len(ADVICE_PROBES) >= 20


def test_performance_probes_count() -> None:
    assert len(PERFORMANCE_PROBES) >= 15


def test_out_of_scope_probes_count() -> None:
    assert len(OUT_OF_SCOPE_PROBES) >= 5


def test_zero_advice_probes_reach_factual() -> None:
    leaked = [p for p in ADVICE_PROBES if classify(p).intent == INTENT_FACTUAL]
    assert leaked == []


def test_zero_performance_probes_reach_factual() -> None:
    leaked = [p for p in PERFORMANCE_PROBES if classify(p).intent == INTENT_FACTUAL]
    assert leaked == []


def test_advice_beats_performance() -> None:
    result = classify("should I buy the one with better returns?")
    assert result.intent == INTENT_ADVICE


def test_pii_hit_short_circuits_to_npi() -> None:
    result = classify("what is the expense ratio of HDFC Large Cap Fund?", pii_hit=True)
    assert result.intent == INTENT_NPI
    assert result.matched_rule == "npi"


def test_empty_query_is_out_of_scope() -> None:
    assert classify("").intent == INTENT_OUT_OF_SCOPE


def test_whitespace_query_is_out_of_scope() -> None:
    assert classify("     ").intent == INTENT_OUT_OF_SCOPE


def test_comparative_needs_two_schemes() -> None:
    result = classify("compare HDFC Large Cap Fund versus HDFC Flexi Cap Fund")
    assert result.intent == INTENT_COMPARATIVE_FACTUAL


def test_comparative_with_one_scheme_is_plain_factual() -> None:
    result = classify("is HDFC Large Cap Fund versus the benchmark factual?")
    assert result.intent == INTENT_FACTUAL


def test_matched_rule_is_recorded() -> None:
    assert classify("Should I buy HDFC ELSS?").matched_rule == "advice"
    assert classify("What is the exit load?").matched_rule == "factual"
    assert classify("tell me about SBI Bluechip Fund").matched_rule == (
        "out_of_scope_allowlist"
    )


def test_intent_result_helpers() -> None:
    assert IntentResult(INTENT_FACTUAL, None).is_factual is True
    assert IntentResult(INTENT_COMPARATIVE_FACTUAL, None).is_factual is True
    assert IntentResult(INTENT_ADVICE, None).is_factual is False
    assert IntentResult(INTENT_ADVICE, None).is_refusal is True
    assert IntentResult(INTENT_FACTUAL, None).is_refusal is False


def test_out_of_scope_is_an_allowlist_not_a_blocklist() -> None:
    novel = "what is the TER of the HDFC Flexi Cap Fund?"
    assert classify(novel).intent == INTENT_FACTUAL
    nonsense = "purple monkey dishwasher xyzzy plugh"
    assert classify(nonsense).intent == INTENT_OUT_OF_SCOPE


def test_allowlist_covers_every_intent_path() -> None:
    assert classify("what is the AUM of HDFC Large Cap Fund?").intent == INTENT_FACTUAL
    assert classify("what is the riskometer level?").intent == INTENT_FACTUAL
    assert classify("what is the benchmark?").intent == INTENT_FACTUAL
    assert classify("what is the 80C benefit?").intent == INTENT_FACTUAL
    assert classify("what is the lock-in period?").intent == INTENT_FACTUAL
    assert classify("what is the minimum SIP?").intent == INTENT_FACTUAL
