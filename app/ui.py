from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="HDFC AMC Scheme Facts",
    page_icon="\U0001F4C4",
    layout="centered",
)

from app import config, ui_components as ui, ui_data, ui_screens
from app.pipeline import answer_question

EXAMPLES = ui_screens.EXAMPLES
REFUSAL_LABEL = ui.REFUSAL_LABEL
NOT_ANSWERABLE_LABEL = ui.NOT_ANSWERABLE_LABEL
MIRROR_LABEL = ui.MIRROR_LABEL
DEBUG_HEADERS = ("#", "chunk_id", "fused", "cosine", "lexical", "rerank", "best", "section")
SCREENS = ui_screens.SCREENS


@st.cache_resource(show_spinner=False)
def get_records() -> tuple:
    return tuple(ui_data.load_scheme_facts())


def debug_enabled() -> bool:
    if str(st.query_params.get("debug", "")).lower() in ("1", "true", "yes"):
        return True
    return bool(st.session_state.get("debug", False))


def get_turns() -> list:
    return st.session_state.setdefault("turns", [])


def main() -> None:
    from app import ui_theme

    ui_theme.inject(st)
    st.sidebar.markdown("**Controls**")
    st.sidebar.toggle("Offline mode (extractive answers)", value=False, key="offline")
    st.sidebar.toggle("Debug", value=False, key="debug")
    st.sidebar.caption(ui.MICRO_FOOTNOTE)

    records = get_records()
    tabs = st.tabs([label for _, label in SCREENS])
    by_key = {key: tab for (key, _), tab in zip(SCREENS, tabs)}

    with by_key[ui_screens.SCREEN_QA]:
        ui_screens.render_qa(
            st,
            get_turns(),
            list(records),
            bool(st.session_state.get("offline", False)),
            debug_enabled(),
        )

    with by_key[ui_screens.SCREEN_FACTS]:
        ui_screens.render_facts(st, list(records))

    with by_key[ui_screens.SCREEN_SCOPE]:
        ui_screens.render_scope(st, list(records))

    st.divider()
    st.caption(config.SCOPE_STATEMENT)
    st.caption(config.DISCLAIMER)


main()
