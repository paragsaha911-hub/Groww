from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app import config

MISSING = "Not in current sources"

METRIC_ORDER = ("expense_ratio", "min_sip", "exit_load", "benchmark")

METRIC_LABELS = {
    "expense_ratio": "Expense Ratio (TER)",
    "min_sip": "Min SIP / Lumpsum",
    "exit_amount": "Min SIP / Lumpsum",
    "exit_load": "Exit Load",
    "benchmark": "Benchmark",
    "riskometer": "Riskometer",
    "nav": "NAV",
    "aum": "AUM",
    "lock_in": "Statutory Lock-in",
}

METRIC_UNITS = {
    "expense_ratio": "%",
    "min_sip": "INR / month",
    "min_amount": "INR",
}

RISK_TONE = {
    "very high": "warn",
    "moderately high": "warn",
    "high": "high",
    "moderate": "high",
    "low": "ok",
    "very low": "ok",
}


@dataclass
class SchemeFacts:
    scheme_id: str
    name: str
    category: str
    plan: str
    url: str
    source_id: str
    authority: str
    document_date: date | None
    fields: dict[str, str] = field(default_factory=dict)
    missing_facts: list[str] = field(default_factory=list)
    official_url: str | None = None
    official_title: str | None = None
    official_as_of: str | None = None

    def value(self, key: str) -> str:
        raw = (self.fields.get(key) or "").strip()
        return raw or MISSING

    @property
    def short(self) -> str:
        return self.name.replace(" Fund", "").replace(" Mutual Fund", "")

    def has(self, key: str) -> bool:
        return bool((self.fields.get(key) or "").strip())

    def percent(self, key: str = "expense_ratio") -> str:
        raw = (self.fields.get(key) or "").strip()
        if not raw:
            return MISSING
        return raw if raw.endswith("%") else f"{raw}%"

    def rupees(self, key: str) -> str:
        raw = (self.fields.get(key) or "").strip()
        if not raw:
            return MISSING
        return raw if raw.startswith("₹") else f"₹{raw}"

    def risk_tone(self) -> str:
        return RISK_TONE.get(self.value("riskometer").lower(), "warn")

    def is_complete(self) -> bool:
        return not self.missing_facts

    def searchable(self) -> str:
        parts = [self.name, self.category, self.plan]
        parts.extend(f"{key} {value}" for key, value in self.fields.items())
        return " ".join(parts).lower()

    def official_link(self) -> tuple[str, str]:
        if self.official_url:
            label = self.official_title or "Official AMC source"
            return self.official_url, label
        return self.url, "Mirror scheme page"


def _processed_dir() -> Path:
    return config.PROCESSED_DIR


def _read_fields(source_id: str) -> dict:
    path = _processed_dir() / f"{source_id}.fields.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _official_for(scheme_id: str) -> dict | None:
    for source in config.OFFICIAL_SOURCES:
        if source.get("scheme_id") == scheme_id:
            return source
    return None


def _parse_date(raw: object) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def load_scheme_facts() -> list[SchemeFacts]:
    records: list[SchemeFacts] = []
    for scheme in config.SCHEMES:
        official = _official_for(scheme.scheme_id)
        source_id = f"{scheme.scheme_id}_groww"
        payload = _read_fields(source_id)
        records.append(
            SchemeFacts(
                scheme_id=scheme.scheme_id,
                name=scheme.name,
                category=scheme.category,
                plan=scheme.plan,
                url=scheme.url,
                source_id=source_id,
                authority=payload.get("authority", "mirror"),
                document_date=_parse_date(payload.get("document_date")),
                fields=dict(payload.get("fields") or {}),
                missing_facts=list(payload.get("missing_facts") or []),
                official_url=(official or {}).get("url"),
                official_title=(official or {}).get("title"),
                official_as_of=(official or {}).get("as_of"),
            )
        )
    return records


def scheme_by_id(scheme_id: str) -> SchemeFacts | None:
    for record in load_scheme_facts():
        if record.scheme_id == scheme_id:
            return record
    return None


def filter_records(
    records: list[SchemeFacts], term: str
) -> list[SchemeFacts]:
    needle = (term or "").strip().lower()
    if not needle:
        return list(records)
    return [record for record in records if needle in record.searchable()]


def corpus_as_of(records: list[SchemeFacts]) -> date | None:
    stamps = [record.document_date for record in records if record.document_date]
    return max(stamps) if stamps else None


ALL_SCHEMES = "__all__"


def scheme_label(scheme_id: str) -> str:
    record = scheme_by_id(scheme_id)
    return record.name if record else "All schemes"


def facts_mentioned(record: SchemeFacts, answer: str) -> list[tuple[str, str]]:
    text = (answer or "").lower()
    hits: list[tuple[str, str]] = []
    for key in METRIC_ORDER:
        raw = (record.fields.get(key) or "").strip()
        if not raw:
            continue
        probes = [raw.lower()]
        if key == "expense_ratio":
            probes.append(f"{raw.rstrip('%')}%")
        if key in ("min_sip", "min_amount"):
            probes.append(f"₹{raw}")
        if any(probe and probe in text for probe in probes):
            display = record.percent() if key == "expense_ratio" else record.rupees(key)
            if key == "min_sip":
                display = f"{record.rupees('min_sip')} / {record.rupees('min_amount')}"
            hits.append((METRIC_LABELS[key], display))
    return hits


def source_tiers() -> list[tuple[str, str]]:
    return [
        (
            "Scheme Information Document (SID)",
            "Legal statutory charter approved by SEBI, establishing the investment "
            "mandate and asset bounds.",
        ),
        (
            "Key Information Memorandum (KIM)",
            "Concise statutory summary of fees, risk category and minimum "
            "application amounts.",
        ),
        (
            "Monthly Factsheets",
            "Operational disclosures and expense ratios published each month by "
            "HDFC Asset Management.",
        ),
        (
            "AMFI categorisation master",
            "Standardised taxonomy used for uniform scheme classification.",
        ),
    ]


CAN_DO = (
    ("Retrieve verified total expense ratios for the indexed plans.", "expense_ratio"),
    ("State published exit load terms and redemption cut-offs.", "exit_load"),
    ("Disclose statutory lock-in obligations such as the ELSS 3-year rule.", "lock_in"),
    ("Report the certified SEBI riskometer level.", "riskometer"),
    ("State the designated benchmark index.", "benchmark"),
    ("State minimum SIP and lumpsum application amounts.", "min_sip"),
    ("Cite the exact AMC source filing with a page anchor.", "citations"),
)

CANNOT_DO = (
    "Never provides financial, tax or investment advice, or portfolio suitability.",
    "Never recommends or endorses any scheme or asset allocation pattern.",
    "Never predicts future returns or ranks funds by historical returns.",
    "Never answers subjective questions such as which fund is best to buy.",
    "Does not answer questions about schemes outside the indexed HDFC funds.",
    "Does not execute buy, sell, switch, STP or SIP orders.",
)
