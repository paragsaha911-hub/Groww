from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app import config, ui_components as ui, ui_data
from app.guardrails import intent as intent_router
from app.guardrails.pii import scan as pii_scan
from app.guardrails.pii import scrub as pii_scrub
from app.models import QueryResult
from app.pipeline import answer_question, load_trace

SCREEN_QA = "qa"
SCREEN_FACTS = "facts"
SCREEN_SCOPE = "scope"

SCREENS = (
    (SCREEN_QA, "Q&A Assistant"),
    (SCREEN_FACTS, "Scheme Facts"),
    (SCREEN_SCOPE, "Scope & Rules"),
)

EXAMPLES = (
    "What is the expense ratio of HDFC Large Cap Fund?",
    "Is there an exit load on HDFC ELSS Tax Saver Fund?",
    "What is the riskometer level of HDFC Balanced Advantage Fund?",
)

PLACEHOLDER = "Ask fact (e.g. exit load, TER, lock-in, riskometer)..."

SANDBOX_PROBES = (
    ("What is the exit load of HDFC Large Cap Fund?", "published fact, in scope"),
    ("Should I buy HDFC Small Cap today?", "advice is refused"),
    ("What is the price of Bitcoin?", "out-of-scope is declined"),
)

REFUSAL_STATUS = {
    "advice": "REFUSED - ADVISORY GUARDRAIL",
    "performance": "REFUSED - PERFORMANCE GUARDRAIL",
    "out_of_scope": "DECLINED - OUT OF SCOPE",
    "npi": "REFUSED - PII GUARDRAIL",
    "not_found": "NOT ANSWERABLE - RETRIEVAL FLOOR",
}

REFUSAL_EXPLANATION = {
    "advice": (
        "Asking whether to buy is an advisory request, which the non-advisory "
        "guardrail blocks before retrieval."
    ),
    "performance": (
        "Return figures and performance comparisons are outside the published-fact scope."
    ),
    "out_of_scope": (
        "The assistant only indexes the five HDFC Mutual Fund schemes in scope."
    ),
    "npi": "Personal identifiers are detected and removed before anything else runs.",
    "not_found": (
        "No retrieved chunk cleared the similarity floor for this question."
    ),
}


@dataclass
class Turn:
    question: str
    result: QueryResult
    clock: str
    scheme_id: str


def now_clock() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


def get_asker() -> object:
    return answer_question


def ask(question: str, offline: bool, debug: bool, scheme_id: str = "") -> Turn:
    record = ui_data.scheme_by_id(scheme_id) if scheme_id else None
    submitted = question
    if record is not None and not _names_scheme(question, record):
        submitted = f"{question} (regarding {record.name})"
    result = get_asker()(submitted, debug=debug, offline=offline)
    return Turn(
        question=question,
        result=result,
        clock=now_clock(),
        scheme_id=record.scheme_id if record else "",
    )


def _names_scheme(question: str, record: ui_data.SchemeFacts) -> bool:
    haystack = question.lower()
    return record.name.lower() in haystack or record.scheme_id.lower() in haystack


def _scheme_for(turn: Turn) -> ui_data.SchemeFacts | None:
    if turn.scheme_id:
        return ui_data.scheme_by_id(turn.scheme_id)
    if turn.result.citations:
        wanted = turn.result.citations[0].source_id.split("_")[0]
        return ui_data.scheme_by_id(wanted)
    return None


def _card_note(result: QueryResult) -> str:
    if result.refused:
        return "Guardrail"
    if result.generator.startswith("groq"):
        return "Source grounded"
    return "Offline extractive"


def render_qa_history(turns: list[Turn], records: list[ui_data.SchemeFacts]) -> str:
    parts: list[str] = []
    for turn in turns:
        parts.append(ui.user_turn(turn.question, turn.clock))
        record = _scheme_for(turn)
        name = record.name if record else "HDFC scheme"
        parts.append(
            ui.answer_turn(
                turn.result,
                turn.question,
                turn.clock,
                name,
                _card_note(turn.result),
                record,
            )
        )
    return "".join(parts)


def clear_conversation(st: object) -> None:
    st.session_state["turns"] = []
    st.session_state["last_debug_trace"] = None
    st.session_state["example_applied"] = None
    st.session_state.pop("example_pill", None)
    st.session_state.pop("question", None)


def render_qa(
    st: object,
    turns: list[Turn],
    records: list[ui_data.SchemeFacts],
    offline: bool,
    debug: bool,
) -> None:
    st.markdown(ui.compliance_ribbon(), unsafe_allow_html=True)

    labels = {ui_data.ALL_SCHEMES: f"All {len(records)} Schemes"}
    labels.update({record.scheme_id: record.short for record in records})
    order = [ui_data.ALL_SCHEMES, *[record.scheme_id for record in records]]
    picked = st.pills(
        "Scheme",
        options=order,
        selection_mode="single",
        format_func=lambda value: labels.get(value, value),
        key="scheme_pill",
        label_visibility="collapsed",
    )
    scheme_id = picked if picked in labels and picked != ui_data.ALL_SCHEMES else ""
    st.session_state["scheme_filter"] = scheme_id

    chosen = st.pills(
        "Try a question",
        options=list(EXAMPLES),
        selection_mode="single",
        key="example_pill",
        label_visibility="collapsed",
    )
    if chosen and chosen != st.session_state.get("example_applied"):
        st.session_state["question"] = chosen
        st.session_state["example_applied"] = chosen

    linked = st.query_params.get("q", "")
    if linked and linked != st.session_state.get("example_applied"):
        st.session_state["question"] = linked
        st.session_state["example_applied"] = linked

    if not turns:
        st.markdown(
            '<div class="gfa-html"><div class="gfa-empty">'
            '<div style="font-size:22px">&#128172;</div>'
            '<div class="gfa-empty-title">Ask a published fact</div>'
            '<div class="gfa-empty-body">Expense ratio, exit load, minimum SIP, '
            "lock-in, riskometer and benchmark are answerable. Advice, returns and "
            "out-of-scope questions are declined.</div></div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(render_qa_history(turns, records), unsafe_allow_html=True)

    question = st.text_input(
        "Your question", key="question", placeholder=PLACEHOLDER
    )
    columns = st.columns([4, 1, 1, 1])
    ask_clicked = columns[1].button("Ask", type="primary", use_container_width=True)
    clear_clicked = columns[2].button(
        "Clear", on_click=lambda: clear_conversation(st), use_container_width=True
    )
    columns[3].markdown(
        f'<div class="gfa-html"><p class="gfa-footnote">{ui.MICRO_FOOTNOTE}</p></div>',
        unsafe_allow_html=True,
    )

    if clear_clicked:
        st.rerun()

    if ask_clicked and question.strip():
        with st.spinner("Searching the corpus..."):
            turn = ask(question, offline, debug, scheme_id)
        turns.append(turn)
        if debug:
            st.session_state["last_debug_trace"] = turn.result.trace_id
        st.rerun()

    trace_id = st.session_state.get("last_debug_trace")
    if debug and trace_id:
        render_debug(st, trace_id)


def render_facts(st: object, records: list[ui_data.SchemeFacts]) -> None:
    st.markdown(ui.banner("Audit-ready statutory facts"), unsafe_allow_html=True)
    st.markdown(
        '<div class="gfa-html"><h1 class="gfa-title">Covered HDFC Schemes</h1>'
        '<p class="gfa-lede">Factual metrics extracted from the indexed scheme '
        "documents. No performance or return figures.</p></div>",
        unsafe_allow_html=True,
    )

    term = st.text_input(
        "Search facts, category or plan", value="", placeholder="Search facts, category, plan type..."
    )
    matches = ui_data.filter_records(records, term)
    as_of = ui_data.corpus_as_of(records)
    st.markdown(
        f'<div class="gfa-html"><div class="gfa-counter">'
        f"<span>Showing {len(matches)} of {len(records)} indexed files</span>"
        f'<span class="gfa-live"><span class="gfa-live-dot"></span> '
        f"Corpus {as_of.isoformat() if as_of else 'unknown'}</span></div></div>",
        unsafe_allow_html=True,
    )

    if not matches:
        st.markdown(
            ui.empty_state(
                f"Only {len(records)} HDFC Mutual Fund schemes are indexed in this release."
            ),
            unsafe_allow_html=True,
        )
        return

    for record in matches:
        st.markdown(ui.scheme_card(record), unsafe_allow_html=True)

    st.markdown(
        ui.callout(
            f"{config.SCOPE_STATEMENT} Every figure above is a published fact, not a "
            "recommendation, and is labelled with its source authority."
        ),
        unsafe_allow_html=True,
    )


def _sandbox_verdict(query: str) -> str:
    scan = pii_scan(query)
    shown = pii_scrub(query)
    if scan.has_pii:
        return ui.verdict(
            "npi",
            shown,
            f"Status: <b>{REFUSAL_STATUS['npi']}</b>. Detected "
            f"{', '.join(scan.detected)} and removed it before any retrieval or "
            "generation.",
        )
    result = intent_router.classify(query)
    if result.is_factual:
        return ui.verdict(
            result.intent,
            shown,
            "Status: <b>PERMITTED FACTUAL RETRIEVAL</b>. Routed to the indexed scheme "
            "documents and answered with a citation.",
        )
    status = REFUSAL_STATUS.get(result.intent, REFUSAL_STATUS["out_of_scope"])
    detail = REFUSAL_EXPLANATION.get(result.intent, REFUSAL_EXPLANATION["out_of_scope"])
    return ui.verdict(result.intent, shown, f"Status: <b>{status}</b>. {detail}")


def render_scope(st: object, records: list[ui_data.SchemeFacts]) -> None:
    st.markdown(ui.banner("SEBI compliance-safe fact retrieval engine"), unsafe_allow_html=True)
    st.markdown(
        '<div class="gfa-html"><h1 class="gfa-title">Scope, Compliance &amp; Rules</h1>'
        '<p class="gfa-lede">A strict factual retrieval tool built on indexed public '
        "scheme documents. It has no advisory capability.</p></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="gfa-html"><div class="gfa-panel"><div class="gfa-panel-head">'
        '<div class="gfa-panel-title"><span class="gfa-ico-warn">&#129302;</span>'
        "Guardrail policy preview</div>"
        '<span class="gfa-chip-note">Interactive</span></div>'
        '<p class="gfa-panel-sub">Test a prompt against the automated compliance '
        "filter to see the boundary in action.</p></div></div>",
        unsafe_allow_html=True,
    )
    probe = st.selectbox(
        "Test a prompt",
        [text for text, _ in SANDBOX_PROBES],
        key="sandbox_query",
        label_visibility="collapsed",
    )
    st.markdown(_sandbox_verdict(probe), unsafe_allow_html=True)

    can_do = "".join(
        ui.list_item(
            text.replace(key, f"<b>{key}</b>") if key in text else f"<b>{text}</b>",
            "&#10003;",
            "ok",
        )
        for text, key in ui_data.CAN_DO
    )
    cannot_do = "".join(
        ui.list_item(f"<b>Never</b> {text}" if text.startswith("provides") else f"<b>{text}</b>", "&#10005;", "no")
        for text in ui_data.CANNOT_DO
    )
    st.markdown(
        '<div class="gfa-html"><div class="gfa-panel"><div class="gfa-panel-title">'
        '<span class="gfa-ico-ok">&#10003;</span>What this assistant CAN do</div>'
        f'<div class="gfa-list">{can_do}</div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="gfa-html"><div class="gfa-panel"><div class="gfa-panel-title">'
        '<span class="gfa-ico-no">&#9873;</span>What this assistant CANNOT do</div>'
        f'<div class="gfa-list">{cannot_do}</div></div></div>',
        unsafe_allow_html=True,
    )

    rows = "".join(
        ui.scope_row(index, record.name, record.category)
        for index, record in enumerate(records, start=1)
    )
    st.markdown(
        '<div class="gfa-html"><div class="gfa-panel">'
        '<div class="gfa-panel-head"><div class="gfa-panel-title">'
        '<span class="gfa-ico-info">&#128196;</span>Covered schemes boundary</div>'
        f'<span class="gfa-chip-note">{len(records)} active schemes</span></div>'
        f'<div class="gfa-list">{rows}</div>'
        '<div class="gfa-callout"><span class="gfa-ico-warn">&#8505;</span>'
        "<span>Questions about any other mutual fund, stock or crypto are declined."
        "</span></div></div></div>",
        unsafe_allow_html=True,
    )

    tiers = "".join(
        ui.list_item(f"<b>{name}</b> - {detail}", "&#9312;", "info")
        for name, detail in ui_data.source_tiers()
    )
    st.markdown(
        '<div class="gfa-html"><div class="gfa-panel">'
        '<div class="gfa-panel-title"><span class="gfa-ico-ok">&#128293;</span>'
        "Where does the data come from?</div>"
        f'<div class="gfa-list">{tiers}</div>'
        f'<div class="gfa-fresh"><span>&#128337;</span><span>Documents pinned at '
        f"{_as_of_text(records)}</span></div></div></div>",
        unsafe_allow_html=True,
    )

    st.markdown(ui.legal_notice(), unsafe_allow_html=True)


def _as_of_text(records: list[ui_data.SchemeFacts]) -> str:
    as_of = ui_data.corpus_as_of(records)
    return as_of.isoformat() if as_of else "unknown"


def render_debug(st: object, trace_id: str) -> None:
    record = load_trace(trace_id) or {}
    rows = [
        {
            "rank": item.get("rank"),
            "chunk_id": item.get("chunk_id"),
            "fused": item.get("fused_score"),
            "cosine": item.get("cosine_score"),
            "lexical": item.get("lexical_score"),
            "rerank": item.get("rerank_score"),
            "best": item.get("best_score"),
            "section": item.get("section"),
        }
        for item in (record.get("retrieved") or [])
    ]
    st.markdown("**Debug: ranked chunks**", unsafe_allow_html=True)
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        f"trace_id={trace_id} · corpus={record.get('corpus_version', '?')} · "
        f"embed={record.get('embed_model', '?')}"
    )
