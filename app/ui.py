from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="HDFC AMC Scheme Facts",
    page_icon="📄",
    layout="centered",
)

from app import config
from app.models import AUTHORITY_MIRROR, QueryResult
from app.pipeline import answer_question, load_trace

WELCOME = "Ask a factual question about HDFC AMC's Large Cap, Flexi Cap, ELSS, Small Cap and Balanced Advantage funds."
EXAMPLES = (
    "What is the expense ratio of HDFC Large Cap Fund?",
    "Is there an exit load on HDFC ELSS Tax Saver Fund?",
    "What is the riskometer level of HDFC Balanced Advantage Fund?",
)
REFUSAL_LABEL = "Refused"
NOT_ANSWERABLE_LABEL = "Not answerable from the current sources"
MIRROR_LABEL = "Mirror source"
DEBUG_HEADERS = ("#", "chunk_id", "fused", "cosine", "lexical", "rerank", "best", "section")


@st.cache_resource(show_spinner=False)
def get_pipeline() -> object:
    return answer_question


def debug_enabled() -> bool:
    params = st.query_params
    if str(params.get("debug", "")).lower() in ("1", "true", "yes"):
        return True
    return bool(st.session_state.get("debug", False))


def render_answer(result: QueryResult) -> None:
    if result.refused:
        if result.refusal_kind == "not_found":
            st.warning(f"**{REFUSAL_LABEL}: {NOT_ANSWERABLE_LABEL}**")
        else:
            st.warning(f"**{REFUSAL_LABEL}: {result.refusal_kind}**")
        st.write(result.answer)
        return
    st.write(result.answer)
    if result.citations:
        st.markdown("**Sources**")
        for citation in result.citations:
            label = citation.label()
            if citation.authority == AUTHORITY_MIRROR:
                st.caption(f"⚠ {MIRROR_LABEL}: {label}")
            st.markdown(f"[{label}]({citation.url})")
    if result.freshness_date:
        st.caption(f"Freshness: {result.freshness_date.isoformat()}")
    st.caption(
        f"intent={result.intent} · generator={result.generator} · "
        f"authority={result.authority} · {result.latency_ms}ms"
    )


def render_debug(result: QueryResult) -> None:
    record = load_trace(result.trace_id) or {}
    st.markdown("**Debug: ranked chunks**")
    st.dataframe(
        [
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
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        f"trace_id={result.trace_id} · corpus={record.get('corpus_version', '?')} · "
        f"embed={record.get('embed_model', '?')}"
    )


def render_footer() -> None:
    st.divider()
    st.caption(config.SCOPE_STATEMENT)
    st.caption(config.DISCLAIMER)


def main() -> None:
    st.title("HDFC AMC Scheme Facts")
    st.write(WELCOME)
    st.info(config.DISCLAIMER_SHORT)

    offline = st.sidebar.toggle("Offline mode (extractive answers)", value=False)
    st.sidebar.toggle("Debug", value=False, key="debug")

    st.sidebar.markdown("**Try one of these**")
    chosen = None
    for example in EXAMPLES:
        if st.sidebar.button(example, key=f"example_{example[:24]}"):
            chosen = example

    question = st.text_input(
        "Your question",
        value=chosen or "",
        placeholder=EXAMPLES[0],
    )

    if not question.strip():
        render_footer()
        return

    asker = get_pipeline()
    with st.spinner("Searching the corpus..."):
        result = asker(question, debug=debug_enabled(), offline=offline)

    render_answer(result)
    if debug_enabled():
        render_debug(result)
    render_footer()


main()
