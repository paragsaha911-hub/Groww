from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, NamedTuple

DETECTOR_PAN = "pan"
DETECTOR_AADHAAR = "aadhaar"
DETECTOR_BANK_ACCOUNT = "bank_account"
DETECTOR_IFSC = "ifsc"
DETECTOR_CARD = "card"
DETECTOR_OTP = "otp"
DETECTOR_EMAIL = "email"
DETECTOR_PHONE = "phone"

DETECTOR_NAMES = (
    DETECTOR_PAN,
    DETECTOR_AADHAAR,
    DETECTOR_BANK_ACCOUNT,
    DETECTOR_IFSC,
    DETECTOR_CARD,
    DETECTOR_OTP,
    DETECTOR_EMAIL,
    DETECTOR_PHONE,
)

OTP_KEYWORDS = ("otp", "one time", "one-time", "verification code")
OTP_CONTEXT_CHARS = 40

NUMERIC_PREFIX = r"(?<![A-Za-z0-9])(?<![0-9]\.)"
NUMERIC_SUFFIX = r"(?![A-Za-z0-9])(?!\.[0-9])"

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

PAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])")
AADHAAR_RE = re.compile(NUMERIC_PREFIX + r"(?:\d{4}[ \t]?){2}\d{4}" + NUMERIC_SUFFIX)
BANK_ACCOUNT_RE = re.compile(NUMERIC_PREFIX + r"\d{8,18}" + NUMERIC_SUFFIX)
IFSC_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Za-z0-9])")
CARD_RE = re.compile(NUMERIC_PREFIX + r"\d(?:[ \t-]?\d){12,18}" + NUMERIC_SUFFIX)
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
PHONE_RE = re.compile(r"(?<![0-9])(?:\+91[ \t-]?)?[6-9]\d{9}(?![0-9])")
OTP_DIGITS_RE = re.compile(r"(?<![0-9])\d{4,6}(?![0-9])")


def verhoeff_valid(digits: str) -> bool:
    if len(digits) != 12 or not digits.isdigit():
        return False
    checksum = 0
    for position, char in enumerate(digits):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[(position + 1) % 8][int(char)]]
    return checksum == 0


def luhn_valid(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _digits_only(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


def _aadhaar_ok(match: re.Match[str]) -> bool:
    return verhoeff_valid(_digits_only(match.group(0)))


def _card_ok(match: re.Match[str]) -> bool:
    digits = _digits_only(match.group(0))
    return 13 <= len(digits) <= 19 and luhn_valid(digits)


def _otp_ok(match: re.Match[str], text: str) -> bool:
    start, end = match.span()
    window = text[max(0, start - OTP_CONTEXT_CHARS) : min(len(text), end + OTP_CONTEXT_CHARS)]
    lowered = window.lower()
    return any(keyword in lowered for keyword in OTP_KEYWORDS)


class _Rule(NamedTuple):
    name: str
    pattern: re.Pattern[str]
    validator: Callable[[re.Match[str]], bool] | None = None


class _OtpRule(NamedTuple):
    name: str
    pattern: re.Pattern[str]
    keywords: tuple[str, ...] = OTP_KEYWORDS
    context: int = OTP_CONTEXT_CHARS


RULES: tuple[_Rule, ...] = (
    _Rule(DETECTOR_EMAIL, EMAIL_RE),
    _Rule(DETECTOR_IFSC, IFSC_RE),
    _Rule(DETECTOR_PAN, PAN_RE),
    _Rule(DETECTOR_CARD, CARD_RE, _card_ok),
    _Rule(DETECTOR_AADHAAR, AADHAAR_RE, _aadhaar_ok),
    _Rule(DETECTOR_PHONE, PHONE_RE),
    _Rule(DETECTOR_BANK_ACCOUNT, BANK_ACCOUNT_RE),
)

OTP_RULE = _OtpRule(DETECTOR_OTP, OTP_DIGITS_RE)


class Match(NamedTuple):
    start: int
    end: int
    detector: str
    raw: str

    def redacted(self) -> str:
        return f"[REDACTED:{self.detector}]"


@dataclass
class PiiScan:
    detected: list[str] = field(default_factory=list)
    matches: list[tuple[str, str]] = field(default_factory=list)
    has_pii: bool = False


def _overlaps(start: int, end: int, taken: list[Match]) -> bool:
    return any(start < match.end and end > match.start for match in taken)


def locate(text: str) -> list[Match]:
    found: list[Match] = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            if rule.validator is not None and not rule.validator(match):
                continue
            start, end = match.span()
            if _overlaps(start, end, found):
                continue
            found.append(Match(start, end, rule.name, match.group(0)))
    found.sort(key=lambda item: (item.start, item.end))
    for match in OTP_RULE.pattern.finditer(text):
        if not _otp_ok(match, text):
            continue
        start, end = match.span()
        if _overlaps(start, end, found):
            continue
        found.append(Match(start, end, OTP_RULE.name, match.group(0)))
    found.sort(key=lambda item: (item.start, item.end))
    return found


def scan(text: str) -> PiiScan:
    located = locate(text or "")
    if not located:
        return PiiScan(detected=[], matches=[], has_pii=False)
    seen: list[str] = []
    for match in located:
        if match.detector not in seen:
            seen.append(match.detector)
    return PiiScan(
        detected=seen,
        matches=[(match.detector, match.redacted()) for match in located],
        has_pii=True,
    )


def scrub(text: str) -> str:
    if not text:
        return text
    located = locate(text)
    if not located:
        return text
    pieces: list[str] = []
    cursor = 0
    for match in located:
        pieces.append(text[cursor : match.start])
        pieces.append(match.redacted())
        cursor = match.end
    pieces.append(text[cursor:])
    return "".join(pieces)


def has_pii(text: str) -> bool:
    return bool(locate(text or ""))
