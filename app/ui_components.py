from __future__ import annotations

from html import escape
from typing import Iterable
from urllib.parse import quote_plus

from app import ui_data
from app.models import AUTHORITY_MIRROR, Citation, QueryResult

COMPLIANCE_RIBBON = (
    "This tool shares published facts only and does not provide investment "
    "advice or recommendations."
)

MICRO_FOOTNOTE = (
    "Answers strictly cited from official SEBI/AMFI SID, KIM & Monthly Factsheets."
)

REFUSAL_LABEL = "Refused"
NOT_ANSWERABLE_LABEL = "Not answerable from the current sources"
MIRROR_LABEL = "Mirror source"
OFFICIAL_LABEL = "Official source"
PII_LABEL = "Identifiers removed"

GUARDRAIL_LABEL = "Advisory guardrail triggered"
PII_GUARDRAIL_LABEL = "PII guardrail triggered"
NOT_FOUND_GUARDRAIL_LABEL = "Not answerable"
SCOPE_GUARDRAIL_LABEL = "Out of scope"

INTENT_TITLES = {
    "advice": GUARDRAIL_LABEL,
    "performance": GUARDRAIL_LABEL,
    "out_of_scope": SCOPE_GUARDRAIL_LABEL,
    "npi": PII_GUARDRAIL_LABEL,
    "not_found": NOT_FOUND_GUARDRAIL_LABEL,
}

INTENT_ICONS = {
    "advice": "&#9873;",
    "performance": "&#9873;",
    "out_of_scope": "&#8709;",
    "npi": "&#9888;",
    "not_found": "&#8709;",
}

FACT_LABELS = {
    "expense_ratio": "Direct plan TER",
    "min_sip": "Min SIP",
    "min_amount": "Lumpsum minimum",
    "exit_load": "Exit load",
    "benchmark": "Benchmark",
    "riskometer": "Riskometer",
    "nav": "NAV",
    "aum": "AUM",
    "lock_in": "Lock-in",
}


def _e(value: object) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def highlight(text: str) -> str:
    import re

    pattern = re.compile(
        r"(\d[\d,]*(?:\.\d+)?\s*%|\u20b9\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]{2,}\b)"
    )
    return pattern.sub(lambda match: f"<b>{match.group(0)}</b>", escape(text or ""))


def compliance_ribbon() -> str:
    return (
        '<div class="gfa-html"><div class="gfa-compliance">'
        '<span class="gfa-shield">&#9878;</span>'
        f"<span>{escape(COMPLIANCE_RIBBON)}</span>"
        "</div></div>"
    )


def banner(text: str) -> str:
    return (
        f'<div class="gfa-html"><div class="gfa-banner">'
        f'<span>&#9878;</span><span>{_e(text)}</span></div></div>'
    )


def _stamp(text: str) -> str:
    return f'<span class="gfa-stamp">{_e(text)}</span>'


def user_turn(question: str, clock: str) -> str:
    return (
        '<div class="gfa-html"><div class="gfa-turn gfa-turn-user">'
        f'<div class="gfa-bubble">{_e(question)}</div>{_stamp(clock)}'
        "</div></div>"
    )


def metric_tile(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<span class="gfa-metric-sub">{_e(sub)}</span>' if sub else ""
    return (
        '<div class="gfa-metric">'
        f'<span class="gfa-metric-label">{_e(label)}</span>'
        f'<span class="gfa-metric-value">{_e(value)}</span>{sub_html}</div>'
    )


def metric_grid(tiles: list[str]) -> str:
    return f'<div class="gfa-metrics">{"".join(tiles)}</div>'


def source_row(url: str, label: str, mirror: bool) -> str:
    tag = f" &#9888; {MIRROR_LABEL}" if mirror else ""
    return (
        f'<a class="gfa-source" href="{_e(url)}" target="_blank" rel="noopener noreferrer">'
        f"<span>{_e(label)}{tag}</span><span>&#8599;</span></a>"
    )


def freshness_row(when: str) -> str:
    return (
        f'<div class="gfa-fresh"><span>&#128197;</span>'
        f"<span>{_e(when)}</span></div>"
    )


def callout(text: str, icon: str = "&#128274;") -> str:
    return (
        f'<div class="gfa-callout"><span>{icon}</span>'
        f"<span>{_e(text)}</span></div>"
    )


def ask_link(label: str, question: str) -> str:
    return (
        f'<a class="gfa-link" href="?q={_e(quote_plus(question))}" target="_self">'
        f"<span>{_e(label)}</span><span>&#8599;</span></a>"
    )


def action_row(actions: list[tuple[str, str]]) -> str:
    if not actions:
        return ""
    chips = "".join(
        f'<a class="gfa-action" href="?q={_e(quote_plus(question))}" target="_self">'
        f'<span>&#8226;</span>{_e(label)}</a>'
        for label, question in actions
    )
    return f'<div class="gfa-actions">{chips}</div>'


def _card_head(title: str, note: str, secondary: bool = False) -> str:
    dot = "gfa-dot gfa-dot-secondary" if secondary else "gfa-dot"
    scheme = "gfa-scheme gfa-scheme-secondary" if secondary else "gfa-scheme"
    note_html = f'<span class="gfa-chip-note">{_e(note)}</span>' if note else ""
    return (
        '<div class="gfa-card-head"><div class="gfa-card-title">'
        f'<span class="{dot}"></span>'
        f'<span class="{scheme}">{_e(title)}</span></div>{note_html}</div>'
    )


def citation_pill(citation: Citation) -> str:
    return source_row(citation.url, f"Source: {citation.label()}", citation.authority == AUTHORITY_MIRROR)


def answer_card(
    result: QueryResult,
    scheme_name: str,
    clock: str,
    note: str,
    record: ui_data.SchemeFacts | None = None,
) -> str:
    tiles: list[str] = []
    if record is not None:
        for label, value in ui_data.facts_mentioned(record, result.answer)[:4]:
            tiles.append(metric_tile(label, value))
    grid = metric_grid(tiles) if tiles else ""
    freshness = (
        freshness_row(f"Freshness: {result.freshness_date.isoformat()}")
        if result.freshness_date
        else freshness_row("Freshness: not recorded for this answer")
    )
    sources = "".join(citation_pill(citation) for citation in result.citations)
    actions = action_row(
        [
            ("Exit load", f"What is the exit load of {scheme_name}?"),
            ("Minimum SIP", f"What is the minimum SIP for {scheme_name}?"),
        ]
        if not result.refused
        else []
    )
    body = [
        '<div class="gfa-html"><div class="gfa-card">',
        _card_head(scheme_name, note),
        f'<p class="gfa-answer">{highlight(result.answer)}</p>',
        grid,
        f'<div class="gfa-foot">{freshness}{sources}</div>',
        actions,
        "</div></div>",
    ]
    return "".join(body)


def refusal_card(result: QueryResult, clock: str) -> str:
    kind = result.refusal_kind or "advice"
    label = INTENT_TITLES.get(kind, REFUSAL_LABEL)
    icon = INTENT_ICONS.get(kind, "&#9873;")
    is_pii = kind == "npi"
    tone = "gfa-tag gfa-tag-error" if is_pii else "gfa-tag"
    extra_class = " gfa-pii" if is_pii else ""
    return (
        f'<div class="gfa-html"><div class="gfa-refusal{extra_class}">'
        f'<span class="{tone}"><span>{icon}</span>{_e(label)}</span>'
        f'<p class="gfa-answer">{highlight(result.answer)}</p>'
        "</div></div>"
    )


def turn_stamp(result: QueryResult, clock: str) -> str:
    if result.refused:
        tail = {
            "advice": "Non-advisory guardrail",
            "performance": "Non-advisory guardrail",
            "out_of_scope": "Scope boundary",
            "npi": "PII redacted",
            "not_found": "Below similarity floor",
        }.get(result.refusal_kind or "advice", "Refused")
    else:
        tail = "RAG verified" if result.authority != AUTHORITY_MIRROR else "RAG verified (mirror)"
    return _stamp(f"{clock} • {tail}")


def answer_turn(
    result: QueryResult,
    question: str,
    clock: str,
    scheme_name: str,
    note: str,
    record: ui_data.SchemeFacts | None = None,
) -> str:
    if result.refused:
        body = refusal_card(result, clock)
    else:
        body = answer_card(result, scheme_name, clock, note, record)
    return (
        '<div class="gfa-html"><div class="gfa-turn gfa-turn-bot">'
        f"{body}{turn_stamp(result, clock)}</div></div>"
    )


def scheme_card(record: ui_data.SchemeFacts) -> str:
    tone = record.risk_tone()
    risk_class = "gfa-tag-risk gfa-tag-risk-high" if tone == "high" else "gfa-tag-risk"
    lock = record.value("lock_in")
    lock_html = (
        f'<span class="gfa-lock">{_e(lock)}</span>' if lock != ui_data.MISSING else "Nil"
    )
    tags = [
        f'<span class="gfa-tag-cat">{_e(record.category)}</span>',
        f'<span class="gfa-tag-cat">{_e(record.plan)}</span>',
    ]
    if record.has("lock_in"):
        tags.append('<span class="gfa-tag-cat gfa-tag-lock">3-Yr Statutory Lock</span>')
    tiles = [
        metric_tile("Expense Ratio (TER)", record.percent(), "direct growth"),
        metric_tile(
            "Min SIP / Lumpsum",
            f"{record.rupees('min_sip')} / {record.rupees('min_amount')}",
        ),
        metric_tile("Exit Load", record.value("exit_load")),
        metric_tile("Benchmark", record.value("benchmark")),
    ]
    url, label = record.official_link()
    return (
        '<div class="gfa-html"><div class="gfa-scheme-card">'
        '<div class="gfa-scheme-top"><div>'
        f'<div class="gfa-tags">{"".join(tags)}</div>'
        f'<div class="gfa-scheme-meta"><span class="gfa-metric-value" '
        f'style="font-size:15px">{_e(record.name)}</span></div>'
        "</div>"
        '<div style="display:flex;flex-direction:column;align-items:flex-end">'
        f'<span class="{risk_class}"><span class="gfa-live-dot" '
        f'style="background:currentColor"></span> {_e(record.value("riskometer"))}</span>'
        '<span class="gfa-risk-cap">Riskometer</span></div></div>'
        f"{metric_grid(tiles)}"
        '<div class="gfa-scheme-meta">'
        f"<span>Statutory Lock-in: {lock_html}</span>"
        f"<span>Source as of {_e(record.document_date.isoformat() if record.document_date else ui_data.MISSING)}</span>"
        "</div>"
        '<div class="gfa-card-foot">'
        f"{ask_link('Ask about this scheme', f'What is the expense ratio of {record.name}?')}"
        f'<a class="gfa-link-quiet" href="{_e(url)}" target="_blank" '
        f'rel="noopener noreferrer">{_e(label)}<span>&#8599;</span></a>'
        f'<span class="gfa-link-quiet">{MIRROR_LABEL if record.authority == AUTHORITY_MIRROR else OFFICIAL_LABEL}</span>'
        "</div></div></div>"
    )


def empty_state(message: str) -> str:
    return (
        '<div class="gfa-html"><div class="gfa-empty">'
        '<div style="font-size:22px">&#9906;</div>'
        f'<div class="gfa-empty-title">No statutory match</div>'
        f'<div class="gfa-empty-body">{_e(message)}</div></div></div>'
    )


def list_item(text: str, icon: str, tone: str) -> str:
    return (
        f'<div class="gfa-list-item"><span class="gfa-ico gfa-ico-{tone}">'
        f"{icon}</span><span>{text}</span></div>"
    )


def scope_row(index: int, name: str, tag: str) -> str:
    return (
        '<div class="gfa-scope-row"><div class="gfa-scope-name">'
        f'<span class="gfa-scope-num">{index}</span>'
        f"<span>{_e(name)}</span></div>"
        f'<span class="gfa-scope-tag">{_e(tag)}</span></div>'
    )


def verdict(intent: str, query: str, description: str) -> str:
    permitted = intent in ("factual", "comparative_factual")
    tone_class = "gfa-verdict-ok" if permitted else "gfa-verdict-blocked"
    icon = "&#10003;" if permitted else "&#9873;"
    return (
        '<div class="gfa-html"><div class="gfa-verdict">'
        f'<span class="gfa-verdict-ico {tone_class}">{icon}</span>'
        f'<span><div class="gfa-verdict-query">Query: "{_e(query)}"</div>'
        f'<div class="gfa-verdict-body">{description}</div></span></div></div>'
    )


def legal_notice(extra: str = "") -> str:
    body = escape(config_disclaimer()) + (f" {escape(extra)}" if extra else "")
    return (
        '<div class="gfa-html"><div class="gfa-legal">'
        '<span class="gfa-ico-warn">&#9888;</span>'
        '<div><div class="gfa-legal-head">Mandatory regulatory notice</div>'
        f'<div class="gfa-legal-body">{body}</div>'
        '<div class="gfa-legal-meta">'
        "<span>Facts only</span><span>Non-advisory</span></div></div></div></div>"
    )


def config_disclaimer() -> str:
    from app import config

    return config.DISCLAIMER
