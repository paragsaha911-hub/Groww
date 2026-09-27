from __future__ import annotations

import re
from dataclasses import dataclass

from app import config

INTENT_NPI = "npi"
INTENT_ADVICE = "advice"
INTENT_PERFORMANCE = "performance"
INTENT_OUT_OF_SCOPE = "out_of_scope"
INTENT_FACTUAL = "factual"
INTENT_COMPARATIVE_FACTUAL = "comparative_factual"

STRONG_SCHEME_MARKERS = (
    r"hdfc",
    r"hdfc\s+amc",
    r"hdfc\s+mutual\s+fund",
)

WEAK_SCHEME_ALIASES = (
    r"large\s+cap",
    r"flexi\s+cap",
    r"equity\s+flexi\s+cap",
    r"small\s+cap",
    r"\belss\b",
    r"tax\s+saver",
    r"balanced\s+advantage",
)

FINANCE_TERMS = (
    r"expense\s+ratio",
    r"\bter\b",
    r"exit\s+load",
    r"minimum\s+sip",
    r"\bmin(?:imum)?\s+(?:sip|amount|investment)\b",
    r"lock[\s-]?in",
    r"riskometer",
    r"benchmark",
    r"\bnav\b",
    r"\baum\b",
    r"assets\s+under\s+management",
    r"capital\s+gains?",
    r"statement",
    r"\btax\b",
    r"taxation",
    r"\b80c\b",
    r"\belss\b",
    r"inception\s+date",
    r"fund\s+manager",
    r"direct\s+growth",
    r"plan\s+variant",
    r"risk\s+profile",
    r"dividend",
    r"\bsip\b",
    r"folio",
    r"registrar",
    r"amc\b",
    r"category",
    r"isin",
    r"\bexpense[s]?\b",
)

ADVICE_PATTERNS = (
    r"\bbuy\b",
    r"\bsell\b",
    r"\bhold\b",
    r"\bswitch\b",
    r"\bsip\s+into\b",
    r"\brecommend",
    r"\bsuggest",
    r"\bsuitab",
    r"\bshould\s+i\b",
    r"\bshould\s+we\b",
    r"\bshould\s+you\b",
    r"\bi\s+want\s+to\b",
    r"\bi\s+need\s+to\b",
    r"\bwhich\s+should\s+i\b",
    r"\bportfolio\b",
    r"\ballocat",
    r"\btiming\b",
    r"\bgood\s+for\s+me\b",
    r"\bnice\s+one\s+to\b",
    r"\bworth\b",
    r"\bopinion\b",
    r"\bwhat\s+do\s+you\s+think\b",
    r"\badvi[cs]",
    r"\bgood\s+time\b",
    r"\bgood\s+fit\b",
    r"\bfit\s+for\s+(?:my|your)\b",
    r"\bbest\b[^.?!]{0,25}\bfor\s+me\b",
    r"\bplan\s+to\s+invest\b",
    r"\bmake\s+it\s+my\b",
    r"\badd\s+this\b",
    r"\bfriend\s+says\b",
    r"\bthink\s+i\s+should\b",
    r"\bhelp\s+me\s+choose\b",
    r"\bbest\s+(?:scheme|fund|option)\s+for\b",
)

PERFORMANCE_PATTERNS = (
    r"\breturns?\b",
    r"\byield(?:ed|s)?\b",
    r"\bperform",
    r"\bnav\s+history\b",
    r"\bwhich\s+grew\b",
    r"\bgrew\s+most\b",
    r"\bbest\s+perform",
    r"\bxirr\b",
    r"\balpha\b",
    r"\btop\s+perform",
    r"\bhow\s+much\s+(?:did|has)\s+it\s+(?:grow|earn)",
    r"\bpercent\s+return\b",
    r"\bannualis",
    r"\bannualiz",
    r"\bcagr\b",
    r"\bhas\s+it\s+done\b",
    r"\bright\s+now\b",
    r"\blast\s+year\b",
    r"\bthis\s+year\b",
    r"\bover\s+the\s+past\b",
    r"\bearn(?:ed|s|ings)?\b",
    r"\bprofitable?\b",
    r"\bbeat(?:ing|en)?\b",
    r"\bgain\b",
    r"\boutperform",
    r"\bvs\s+benchmark\b",
)

COMPARATIVE_MARKERS = (
    r"\bvs\b",
    r"\bversus\b",
    r"\bcompared\s+to\b",
    r"\bcomparison\s+of\b",
    r"\bdifference\s+between\b",
    r"\bbetter\b",
    r"\bwhich\s+is\s+better\b",
)

_RULES: list[tuple[str, str, re.Pattern]] = [
    (INTENT_NPI, "npi", re.compile(r"(?!x)x")),
    (
        INTENT_ADVICE,
        "advice",
        re.compile("|".join(ADVICE_PATTERNS), re.IGNORECASE),
    ),
    (
        INTENT_PERFORMANCE,
        "performance",
        re.compile("|".join(PERFORMANCE_PATTERNS), re.IGNORECASE),
    ),
    (
        INTENT_OUT_OF_SCOPE,
        "out_of_scope_allowlist",
        re.compile(
            "|".join(
                [
                    *(f"(?:{term})" for term in FINANCE_TERMS),
                    *STRONG_SCHEME_MARKERS,
                ]
            ),
            re.IGNORECASE,
        ),
    ),
    (INTENT_FACTUAL, "factual", re.compile(r".+")),
]

RULES: list[tuple[str, str, re.Pattern]] = _RULES

_COMPARATIVE_RE = re.compile("|".join(COMPARATIVE_MARKERS), re.IGNORECASE)
_WEAK_ALIAS_RE = re.compile("|".join(WEAK_SCHEME_ALIASES), re.IGNORECASE)


@dataclass
class IntentResult:
    intent: str
    matched_rule: str | None

    @property
    def is_factual(self) -> bool:
        return self.intent in (INTENT_FACTUAL, INTENT_COMPARATIVE_FACTUAL)

    @property
    def is_refusal(self) -> bool:
        return not self.is_factual


def scheme_names_in(query: str) -> set[str]:
    from app.retrieve.retriever import scheme_aliases

    haystack = " ".join((query or "").lower().split())
    padded = f" {haystack} "
    found: set[str] = set()
    for scheme in config.SCHEMES:
        for alias in scheme_aliases(scheme.scheme_id):
            if f" {alias} " in padded:
                found.add(scheme.scheme_id)
    return found


def _matches_factual_allowlist(query: str) -> bool:
    text = query or ""
    if _RULES[3][2].search(text):
        return True
    if scheme_names_in(text):
        return True
    return bool(_WEAK_ALIAS_RE.search(text) and _RULES[3][2].search(text))


def classify(query: str, pii_hit: bool = False) -> IntentResult:
    text = query or ""
    if pii_hit:
        return IntentResult(INTENT_NPI, "npi")
    for intent, name, pattern in _RULES[1:3]:
        if pattern.search(text):
            return IntentResult(intent, name)
    if not _matches_factual_allowlist(text):
        return IntentResult(INTENT_OUT_OF_SCOPE, "out_of_scope_allowlist")
    if _COMPARATIVE_RE.search(text) and len(scheme_names_in(text)) >= 2:
        return IntentResult(INTENT_COMPARATIVE_FACTUAL, "comparative_factual")
    return IntentResult(INTENT_FACTUAL, "factual")
