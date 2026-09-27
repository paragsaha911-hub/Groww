from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.guardrails import pii
from app.guardrails.pii import (
    DETECTOR_AADHAAR,
    DETECTOR_BANK_ACCOUNT,
    DETECTOR_CARD,
    DETECTOR_EMAIL,
    DETECTOR_IFSC,
    DETECTOR_OTP,
    DETECTOR_PAN,
    DETECTOR_PHONE,
    luhn_valid,
    scrub,
    scan,
    verhoeff_valid,
)

VALID_PAN = "ABCDE1234F"
VALID_AADHAAR = "234567890018"
VALID_AADHAAR_SPACED = "2345 6789 0018"
VALID_IFSC = "HDFC0001234"
VALID_CARD = "4111111111111111"
VALID_ACCOUNT = "123456789012"
VALID_OTP = "482913"
VALID_EMAIL = "ravi.kumar@example.co.in"
VALID_PHONE = "9876543210"

POSITIVES = [
    (DETECTOR_PAN, f"My PAN is {VALID_PAN} and that is all"),
    (DETECTOR_AADHAAR, f"Aadhaar number is {VALID_AADHAAR}"),
    (DETECTOR_AADHAAR, f"Aadhaar number is {VALID_AADHAAR_SPACED}"),
    (DETECTOR_IFSC, f"Transfer to IFSC {VALID_IFSC} today"),
    (DETECTOR_CARD, f"card number {VALID_CARD}"),
    (DETECTOR_CARD, f"card number 4111 1111 1111 1111"),
    (DETECTOR_BANK_ACCOUNT, f"account number is {VALID_ACCOUNT}"),
    (DETECTOR_OTP, f"Your OTP is {VALID_OTP}"),
    (DETECTOR_OTP, f"one-time password {VALID_OTP}"),
    (DETECTOR_OTP, f"verification code: {VALID_OTP}"),
    (DETECTOR_EMAIL, f"write to {VALID_EMAIL} for help"),
    (DETECTOR_PHONE, f"call me on +91 {VALID_PHONE}"),
    (DETECTOR_PHONE, f"call me on {VALID_PHONE}"),
    (DETECTOR_PHONE, "call +919876543210 now"),
]

NEGATIVES = [
    "The expense ratio is 1.35",
    "Section 80C deductions apply",
    "As of 2026 the fund had AUM of 1234.56 Cr",
    "What is the minimum SIP amount?",
    "What is the expense ratio of HDFC Large Cap Fund?",
    "Is there an exit load on HDFC ELSS Tax Saver Fund?",
    "What is the lock-in period for the HDFC ELSS Tax Saver Fund?",
    "What is the minimum SIP for HDFC Large Cap Fund?",
    "Compare the expense ratio of HDFC Large Cap Fund and HDFC Small Cap Fund",
    "Regular 1.56% / Direct 1.03%; the Direct value is the one to use",
    "Rs 500 lump sum. S3 is the only scheme whose minimum differs from Rs 100.",
    "Benchmark is NIFTY 250 TRI, distinct from NIFTY 100 TRI and NIFTY 500 TRI",
    "1% if redeemed within 1 year",
    "lock-in is 3 years for the ELSS scheme",
    "ISIN: INF179K01YS4",
    "ISIN: INF179K01YV8 and INF0J0G8ZG9",
    "- document_date: 2026-09-25",
    "- retrieved_at: 2026-09-27T08:06:00.214373+00:00",
    "- tokens: 174",
    "- is_complete: True",
    "NAV as of 2026-09-25 was 12.3456",
    "AUM 1,23,456.78 Cr across 174 folios",
    "80C and 80D both have limits",
    "The fund manager changed in 2026 and AUM fell to 9876.54 Cr",
    '"aum": "113,606.46602051"',
    '"nav": "2,214.572"',
    "balance 123456789012.50",
    "expense ratio 1.35 and AUM 113,606.46602051",
]


DECIMAL_GUARD_CASES = [
    ("aum 113,606.46602051", []),
    ("nav 2,214.572", []),
    ("balance 123456789012.50", []),
    ("fraction 46602051 alone", [DETECTOR_BANK_ACCOUNT]),
    ("account number is 123456789012.", [DETECTOR_BANK_ACCOUNT]),
    ("account 123456789012", [DETECTOR_BANK_ACCOUNT]),
    ("Aadhaar 234567890018", [DETECTOR_AADHAAR]),
    ("Aadhaar 2345 6789 0018", [DETECTOR_AADHAAR]),
    ("card 4111 1111 1111 1111", [DETECTOR_CARD]),
    ("ref 234567890123", [DETECTOR_BANK_ACCOUNT]),
    (
        '"content_hash": "037ab82025036427934f3e31a82f5d3fe082d366bb017b5f234b5384a6a"',
        [],
    ),
    ("ISIN INF179K01YS4", []),
]


@pytest.mark.parametrize("text,expected", DECIMAL_GUARD_CASES)
def test_decimal_fractions_are_not_numeric_pii(text: str, expected: list[str]) -> None:
    result = scan(text)
    assert result.detected == expected, f"{text!r} -> {result.detected}"


def test_sentence_final_period_does_not_hide_an_account() -> None:
    assert scan("account number is 123456789012.").detected == [DETECTOR_BANK_ACCOUNT]
    assert scan("account number is 123456789012!").detected == [DETECTOR_BANK_ACCOUNT]


def test_digit_runs_inside_alphanumeric_tokens_are_not_standalone() -> None:
    hashed = '"content_hash": "037ab82025036427934f3e31a82f5d3fe082d366bb017b5f234b5384a6a"'
    assert scan(hashed).has_pii is False
    assert scan("ref82025036427934suffix").has_pii is False
    assert scan("ISIN INF179K01YS4").has_pii is False


def test_punctuation_separated_account_is_detected() -> None:
    assert scan("Acct:12345678").detected == [DETECTOR_BANK_ACCOUNT]
    assert scan("(12345678)").detected == [DETECTOR_BANK_ACCOUNT]
    assert scan("account=12345678").detected == [DETECTOR_BANK_ACCOUNT]


@pytest.mark.parametrize("detector,text", POSITIVES)
def test_positive_fixtures_are_detected(detector: str, text: str) -> None:
    result = scan(text)
    assert result.has_pii is True
    assert detector in result.detected


@pytest.mark.parametrize("text", NEGATIVES)
def test_negative_fixtures_are_clean(text: str) -> None:
    result = scan(text)
    assert result.has_pii is False, f"false positive: {result.detected} in {text!r}"
    assert result.detected == []
    assert result.matches == []


@pytest.mark.parametrize("text", NEGATIVES)
def test_scrub_leaves_negatives_untouched(text: str) -> None:
    assert scrub(text) == text


@pytest.mark.parametrize("detector,text", POSITIVES)
def test_scrub_removes_the_value(detector: str, text: str) -> None:
    cleaned = scrub(text)
    assert f"[REDACTED:{detector}]" in cleaned
    assert "REDACTED" in cleaned
    for secret in (VALID_PAN, VALID_AADHAAR, VALID_IFSC, VALID_CARD, VALID_OTP, VALID_EMAIL):
        assert secret not in cleaned or secret in VALID_ACCOUNT
    assert scan(cleaned).has_pii is False


@pytest.mark.parametrize("detector,text", POSITIVES)
def test_scrub_is_idempotent(detector: str, text: str) -> None:
    once = scrub(text)
    assert scrub(once) == once
    assert scrub(scrub(once)) == once


def test_scan_reports_detector_and_redacted_form() -> None:
    result = scan(f"pan {VALID_PAN} and email {VALID_EMAIL}")
    assert result.has_pii is True
    assert set(result.detected) == {DETECTOR_PAN, DETECTOR_EMAIL}
    for detector, redacted in result.matches:
        assert redacted == f"[REDACTED:{detector}]"


def test_scan_preserves_surrounding_text() -> None:
    text = f"before {VALID_PAN} after"
    assert scrub(text) == "before [REDACTED:pan] after"


def test_empty_and_blank_input() -> None:
    for value in ("", "   ", "\n\t"):
        assert scan(value).has_pii is False
        assert scrub(value) == value


def test_multiple_pii_in_one_text() -> None:
    text = f"{VALID_PAN} {VALID_EMAIL} {VALID_CARD}"
    result = scan(text)
    assert result.has_pii is True
    assert len(result.detected) == 3
    assert len(result.matches) == 3
    assert scrub(text).count("[REDACTED:") == 3


def test_verhoeff_rejects_invalid_aadhaar() -> None:
    assert verhoeff_valid(VALID_AADHAAR) is True
    assert verhoeff_valid("234567890123") is False
    assert verhoeff_valid("1234") is False
    assert verhoeff_valid("abcdefghijkl") is False


def test_luhn_rejects_invalid_card() -> None:
    assert luhn_valid(VALID_CARD) is True
    assert luhn_valid("4111111111111112") is False
    assert luhn_valid("") is False
    assert luhn_valid("abcdef") is False


def test_aadhaar_beats_bank_account_for_same_digits() -> None:
    result = scan(f"number {VALID_AADHAAR}")
    assert result.detected == [DETECTOR_AADHAAR]


def test_non_verhoeff_twelve_digits_fall_back_to_bank_account() -> None:
    result = scan("ref 234567890123")
    assert result.detected == [DETECTOR_BANK_ACCOUNT]


def test_card_beats_bank_account_for_same_digits() -> None:
    result = scan(f"card {VALID_CARD}")
    assert result.detected == [DETECTOR_CARD]


def test_otp_requires_nearby_keyword() -> None:
    assert scan("the number is 482913 in the form").has_pii is False
    assert scan(f"the number is 482913 and otp is nearby").has_pii is True
    assert scan(f"otp {VALID_OTP}").detected == [DETECTOR_OTP]


def test_otp_keyword_must_be_within_context_window() -> None:
    far = "otp" + (" " * 80) + "482913"
    assert scan(far).has_pii is False
    near = "otp" + (" " * 20) + "482913"
    assert scan(near).has_pii is True


def test_digit_runs_shorter_than_eight_are_never_accounts() -> None:
    for value in ("1", "12", "123", "1234", "12345", "123456", "1234567"):
        assert scan(f"value {value} here").has_pii is False
    assert scan("value 12345678 here").has_pii is True


def test_patterns_are_compiled_at_module_import() -> None:
    assert isinstance(pii.PAN_RE, re.Pattern)
    assert isinstance(pii.AADHAAR_RE, re.Pattern)
    assert isinstance(pii.BANK_ACCOUNT_RE, re.Pattern)
    assert isinstance(pii.IFSC_RE, re.Pattern)
    assert isinstance(pii.CARD_RE, re.Pattern)
    assert isinstance(pii.EMAIL_RE, re.Pattern)
    assert isinstance(pii.PHONE_RE, re.Pattern)
    assert isinstance(pii.OTP_DIGITS_RE, re.Pattern)
    assert isinstance(pii.RULES, tuple)
    assert all(isinstance(rule.pattern, re.Pattern) for rule in pii.RULES)
    assert len(pii.RULES) + 1 == len(pii.DETECTOR_NAMES) == 8


def test_all_eight_detectors_have_a_positive_case() -> None:
    covered = {detector for detector, _ in POSITIVES}
    assert covered == set(pii.DETECTOR_NAMES)


def test_golden_set_queries_and_notes_are_clean() -> None:
    path = Path("data/eval/golden_set.json")
    if not path.is_file():
        pytest.skip("golden set not present")
    items = json.loads(path.read_text(encoding="utf-8"))
    for item in items:
        for key in ("query", "notes", "expected_section"):
            value = item.get(key)
            if not isinstance(value, str) or not value:
                continue
            result = scan(value)
            assert result.has_pii is False, f"{key}={value!r} -> {result.detected}"


def test_real_corpus_chunks_are_clean() -> None:
    path = Path("data/processed/chunks.txt")
    if not path.is_file():
        pytest.skip("chunks report not built")
    text = path.read_text(encoding="utf-8")
    assert text.strip()
    result = scan(text)
    assert result.has_pii is False, f"false positive on real corpus: {result.detected}"


def test_real_corpus_fields_are_clean() -> None:
    paths = sorted(Path("data/processed").glob("*.fields.json"))
    if not paths:
        pytest.skip("processed fields not present")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        result = scan(text)
        assert result.has_pii is False, f"{path.name} -> {result.detected}"
