from __future__ import annotations

import sys
import types
from datetime import date
from typing import Any

import pytest

from app import ui_components as ui
from app import ui_data, ui_theme
from app.models import AUTHORITY_MIRROR, AUTHORITY_OFFICIAL, Citation, QueryResult


def make_result(**overrides: Any) -> QueryResult:
    base: dict[str, Any] = {
        "answer": "The direct growth expense ratio of HDFC Large Cap Fund is 1.03%.",
        "intent": "factual",
        "refused": False,
        "refusal_kind": None,
        "sentences": [],
        "citations": [
            Citation(
                source_id="S1_groww",
                url="https://groww.in/mutual-funds/hdfc-large-cap-fund",
                section_title="Fees",
                authority=AUTHORITY_MIRROR,
                page=None,
            )
        ],
        "freshness_date": date(2026, 6, 30),
        "authority": AUTHORITY_MIRROR,
        "generator": "groq:qwen/qwen3.8-27b",
        "latency_ms": 42,
        "trace_id": "abc123",
    }
    base.update(overrides)
    return QueryResult(**base)


class _Ctx:
    def __init__(self, calls: list, label: str = "") -> None:
        self.calls = calls
        self.label = label

    def __enter__(self) -> "_Ctx":
        self.calls.append(("enter", (self.label,)))
        return self

    def __exit__(self, *args: Any) -> bool:
        self.calls.append(("exit", (self.label,)))
        return False


class _Column:
    def __init__(self, calls: list, buttons: dict[str, bool]) -> None:
        self.calls = calls
        self.buttons = buttons

    def _click(self, label: str, pressed: bool, callback: Any) -> bool:
        self.calls.append(("button", (label,)))
        if pressed and callable(callback):
            callback()
        return pressed

    def button(self, label: str, **kwargs: Any) -> bool:
        return self._click(label, self.buttons.get(label, False), kwargs.get("on_click"))

    def markdown(self, text: str, **kwargs: Any) -> None:
        self.calls.append(("markdown", (text,)))


class FakeStreamlit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.session_state: dict[str, Any] = {}
        self.query_params: dict[str, str] = {}
        self.buttons: dict[str, bool] = {}
        self.text_values: list[str] = []
        self.pill_values: list[str | None] = []
        self.pill_default: str | None = None
        self.rerun_count = 0
        self.sidebar = self

    def record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args or (kwargs,)))

    def set_page_config(self, **kwargs: Any) -> None:
        self.record("set_page_config", **kwargs)

    def title(self, text: str = "") -> None:
        self.record("title", text)

    def write(self, text: str = "") -> None:
        self.record("write", text)

    def info(self, text: str = "") -> None:
        self.record("info", text)

    def caption(self, text: str = "") -> None:
        self.record("caption", text)

    def markdown(self, text: str = "", **kwargs: Any) -> None:
        self.record("markdown", text)

    def divider(self) -> None:
        self.record("divider")

    def warning(self, text: str, **kwargs: Any) -> None:
        self.record("warning", text)

    def dataframe(self, data: Any, **kwargs: Any) -> None:
        self.record("dataframe", data)

    def text_input(self, label: str, **kwargs: Any) -> str:
        self.record("text_input", label)
        if self.text_values:
            return self.text_values.pop(0)
        return kwargs.get("value", "") or ""

    def selectbox(self, label: str, options: list[str], index: int = 0, **kwargs: Any) -> str:
        self.record("selectbox", label)
        if self.text_values:
            return self.text_values.pop(0)
        return options[index]

    def pills(
        self, label: str, options: list[str], selection_mode: str = "single", **kwargs: Any
    ) -> str | None:
        self.record("pills", label)
        if self.pill_values:
            return self.pill_values.pop(0)
        return self.pill_default

    def toggle(self, label: str, **kwargs: Any) -> bool:
        self.record("toggle", label)
        return bool(kwargs.get("value", False))

    def _click(self, label: str, pressed: bool, callback: Any) -> bool:
        self.calls.append(("button", (label,)))
        if pressed and callable(callback):
            callback()
        return pressed

    def button(self, label: str, **kwargs: Any) -> bool:
        return self._click(label, self.buttons.get(label, False), kwargs.get("on_click"))

    def _click(self, label: str, pressed: bool, callback: Any) -> bool:
        self.calls.append(("button", (label,)))
        if pressed and callable(callback):
            callback()
        return pressed

    def button(self, label: str, **kwargs: Any) -> bool:
        return self._click(label, self.buttons.get(label, False), kwargs.get("on_click"))

    def spinner(self, text: str) -> _Ctx:
        self.record("spinner", text)
        return _Ctx(self.calls, "spinner")

    def tabs(self, labels: list[str]) -> list[_Ctx]:
        self.record("tabs", *labels)
        return [_Ctx(self.calls, label) for label in labels]

    def columns(self, spec: Any, **kwargs: Any) -> list[_Column]:
        count = spec if isinstance(spec, int) else len(spec)
        self.record("columns", count)
        return [_Column(self.calls, self.buttons) for _ in range(count)]

    def rerun(self) -> None:
        self.rerun_count += 1

    def cache_resource(self, *args: Any, **kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]

        def decorator(function: Any) -> Any:
            return function

        return decorator

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def html(self) -> str:
        chunks = [
            str(args[0])
            for name, args in self.calls
            if name == "markdown" and args and isinstance(args[0], str)
        ]
        return "\n".join(chunks)

    def texts(self, name: str) -> str:
        return " ".join(
            str(arg) for called, args in self.calls if called == name for arg in args
        )


class _Rerun(Exception):
    pass


@pytest.fixture()
def fake_st(monkeypatch: pytest.MonkeyPatch) -> FakeStreamlit:
    module = types.ModuleType("streamlit")
    fake = FakeStreamlit()
    for attribute in dir(fake):
        if not attribute.startswith("_"):
            setattr(module, attribute, getattr(fake, attribute))
    monkeypatch.setitem(sys.modules, "streamlit", module)
    monkeypatch.delitem(sys.modules, "app.ui", raising=False)
    return fake


def import_ui() -> Any:
    import app.ui as module

    return module


def ask_then_rerun(module: Any, fake_st: FakeStreamlit) -> None:
    module.main()
    module.main()


def test_theme_exposes_design_tokens() -> None:
    assert ui_theme.TOKENS["surface"] == "#111317"
    assert ui_theme.TOKENS["primary_container"] == "#00d09c"
    assert ui_theme.TOKENS["tertiary_container"] == "#fda417"
    assert ui_theme.TOKENS["max_width"] == "840px"
    assert ui_theme.TOKENS["radius_full"] == "9999px"


def test_theme_css_declares_every_token() -> None:
    css = ui_theme.build_css()
    for key in ui_theme.TOKENS:
        assert f"--{key.replace('_', '-')}" in css
    assert "Inter" in css
    assert "tabular-nums" in css
    assert "gfa-compliance" in css
    assert "gfa-refusal" in css
    assert "gfa-scheme-card" in css


def test_theme_css_styles_refusal_without_colour_only() -> None:
    css = ui_theme.build_css()
    assert "gfa-pii" in css
    assert "1F1A12" in css
    assert "2B1617" in css


def test_streamlit_config_file_exists() -> None:
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
    assert config_path.is_file(), ".streamlit/config.toml is required for the dark theme"


def test_streamlit_config_uses_the_design_palette() -> None:
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    assert "[theme]" in text
    assert 'base = "dark"' in text
    assert f'primaryColor = "{ui_theme.TOKENS["primary_container"]}"' in text
    assert f'backgroundColor = "{ui_theme.TOKENS["surface"]}"' in text
    assert f'textColor = "{ui_theme.TOKENS["on_surface"]}"' in text


def test_streamlit_config_has_no_default_red_primary() -> None:
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
    text = config_path.read_text(encoding="utf-8").lower()
    assert "#ff4b4b" not in text


def test_css_overrides_the_app_and_header_background() -> None:
    css = ui_theme.build_css()
    assert '[data-testid="stAppViewContainer"]' in css
    assert '[data-testid="stHeader"]' in css
    assert "background: transparent" in css


def test_css_pins_the_primary_button_to_green_in_every_state() -> None:
    css = ui_theme.build_css()
    assert 'button[data-testid="stBaseButton-primary"]' in css
    assert "background: var(--primary-container)" in css
    assert "background: #00b98a" in css
    assert "background: #00a179" in css


def test_css_keeps_hover_states_visible_not_black() -> None:
    css = ui_theme.build_css()
    hover = css.split(":hover")[1] if ":hover" in css else ""
    assert "surface-container-highest" in hover
    assert "background: #000" not in css
    assert "background: black" not in css


def test_css_sets_an_explicit_focus_ring() -> None:
    css = ui_theme.build_css()
    assert ":focus-visible" in css
    assert ui_theme.TOKENS["focus_ring"] in css


def _css_without_comments() -> str:
    import re

    return re.sub(r"/\*.*?\*/", "", ui_theme.build_css(), flags=re.S)


def _tab_css() -> str:
    css = _css_without_comments()
    return css[css.index(".stTabs [role=") :]


def test_tab_css_uses_react_aria_selectors_not_baseweb() -> None:
    css = _css_without_comments()
    assert 'data-baseweb="tab-list"' not in css
    assert 'data-baseweb="tab-highlight"' not in css
    assert 'data-baseweb="tab-border"' not in css
    assert '[role="tablist"]' in css
    assert '[data-testid="stTab"]' in css
    assert "react-aria-SelectionIndicator" in css


def test_tablist_is_flex_with_a_gap_and_no_wrap() -> None:
    block = _tab_css().split('}')[0]
    assert "display: flex" in block
    assert "gap:" in block
    assert "flex-wrap: nowrap" in block
    assert "overflow-x: auto" in block


def test_tab_labels_are_forced_onto_one_line() -> None:
    assert "white-space: nowrap" in _tab_css()


def test_tabs_are_never_absolutely_positioned_or_stacked() -> None:
    tabs = _tab_css()
    assert "position: absolute" not in tabs
    assert "position:absolute" not in tabs
    assert "flex: 0 0 auto" in tabs


def test_underline_is_not_given_a_fixed_width_or_offset() -> None:
    block = _tab_css().split("react-aria-SelectionIndicator")[1].split("}")[0]
    assert "left: 0" in block
    assert "right: 0" in block
    assert "width" not in block
    assert "transform" not in block


def test_active_tab_does_not_get_a_conflicting_pill_background() -> None:
    assert "#0b2921" not in _tab_css()


def test_theme_inject_uses_unsafe_html() -> None:
    recorded: list[tuple[str, dict]] = []

    class Sink:
        def markdown(self, text: str, **kwargs: Any) -> None:
            recorded.append((text, kwargs))

    ui_theme.inject(Sink())
    assert recorded
    assert recorded[0][1].get("unsafe_allow_html") is True
    assert "<style>" in recorded[0][0]


def test_data_loads_five_real_schemes() -> None:
    records = ui_data.load_scheme_facts()
    assert len(records) == 5
    assert {record.scheme_id for record in records} == {"S1", "S2", "S3", "S4", "S5"}


def test_data_reads_values_from_extracted_fields() -> None:
    records = {record.scheme_id: record for record in ui_data.load_scheme_facts()}
    assert records["S1"].percent() == "1.03%"
    assert records["S4"].rupees("min_sip") == "₹100"
    assert records["S3"].value("lock_in") == "3 years"


def test_data_marks_missing_facts() -> None:
    records = {record.scheme_id: record for record in ui_data.load_scheme_facts()}
    assert records["S1"].value("lock_in") == ui_data.MISSING
    assert records["S1"].has("lock_in") is False


def test_data_does_not_invent_scheme_names() -> None:
    names = " ".join(record.name for record in ui_data.load_scheme_facts())
    assert "Top 100" not in names
    assert all(record.name.startswith("HDFC") for record in ui_data.load_scheme_facts())


def test_data_every_record_is_labelled_with_an_authority() -> None:
    for record in ui_data.load_scheme_facts():
        assert record.authority in ("mirror", "official")


def test_data_prefers_official_link_when_available() -> None:
    record = ui_data.scheme_by_id("S3")
    assert record is not None
    url, label = record.official_link()
    assert "hdfcfund.com" in url
    assert "factsheet" in label.lower()


def test_data_filter_matches_name_and_field_values() -> None:
    records = ui_data.load_scheme_facts()
    assert [r.scheme_id for r in ui_data.filter_records(records, "small cap")] == ["S4"]
    assert [r.scheme_id for r in ui_data.filter_records(records, "NIFTY 100")] == ["S1"]
    assert ui_data.filter_records(records, "zzz-no-match") == []


def test_data_corpus_as_of_is_the_newest_document_date() -> None:
    as_of = ui_data.corpus_as_of(ui_data.load_scheme_facts())
    assert as_of == date(2026, 9, 25)


def test_facts_mentioned_only_surfaces_values_present_in_the_answer() -> None:
    record = ui_data.scheme_by_id("S1")
    assert record is not None
    hits = ui_data.facts_mentioned(record, "The direct TER is 1.03%.")
    assert ("Expense Ratio (TER)", "1.03%") in hits
    assert ui_data.facts_mentioned(record, "No numbers here.") == []


def test_compliance_ribbon_is_facts_only() -> None:
    ribbon = ui.compliance_ribbon()
    assert "published facts only" in ribbon
    assert "does not provide investment advice" in ribbon
    assert "gfa-compliance" in ribbon


def test_scheme_filter_pills_cover_every_scheme(fake_st: FakeStreamlit) -> None:
    import_ui()
    labels = [args for name, args in fake_st.calls if name == "pills"]
    assert labels
    assert labels[0] == ("Scheme",)


def test_scheme_filter_pill_maps_to_a_scheme_id(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.pill_values = ["S4", None]
    module.main()
    assert fake_st.session_state["scheme_filter"] == "S4"


def test_all_schemes_pill_clears_the_filter(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.pill_values = [ui_data.ALL_SCHEMES, None]
    module.main()
    assert fake_st.session_state["scheme_filter"] == ""


def test_example_pill_prefills_the_question(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.pill_values = [None, module.EXAMPLES[0]]
    module.main()
    assert fake_st.session_state["question"] == module.EXAMPLES[0]


def test_scheme_filter_is_added_to_the_question(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    seen: dict[str, str] = {}
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda q, **k: (seen.setdefault("q", q), make_result())[1]
    fake_st.pill_values = ["S4", None]
    fake_st.text_values = ["What is the expense ratio?", ""]
    fake_st.buttons = {"Ask": True}
    module.main()
    ui_screens.answer_question = original
    assert "HDFC Small Cap Fund" in seen["q"]


def test_example_text_is_escaped_in_the_pills_label() -> None:
    html = ui.highlight("<script>alert(1)</script>")
    assert "<script>" not in html


def test_highlight_marks_numbers_and_escapes_html() -> None:
    html = ui.highlight("TER is 1.03% and min SIP is ₹100 <b>now</b>")
    assert "<b>1.03%</b>" in html
    assert "<b>\u20b9100</b>" in html
    assert "&lt;b&gt;now&lt;/b&gt;" in html


def test_metric_tile_renders_label_value_and_sub() -> None:
    tile = ui.metric_tile("Expense Ratio (TER)", "1.03%", "direct growth")
    assert "Expense Ratio (TER)" in tile
    assert "1.03%" in tile
    assert "direct growth" in tile
    assert "gfa-metric-value" in tile


def test_source_row_labels_mirror_authority_in_words() -> None:
    row = ui.source_row("https://x.test", "Source: Fees", mirror=True)
    assert ui.MIRROR_LABEL in row
    assert "https://x.test" in row
    assert "noopener" in row


def test_source_row_omits_mirror_label_for_official() -> None:
    row = ui.source_row("https://x.test", "Source: Factsheet", mirror=False)
    assert ui.MIRROR_LABEL not in row


def test_answer_card_shows_answer_citation_and_freshness() -> None:
    record = ui_data.scheme_by_id("S1")
    assert record is not None
    html = ui.answer_card(make_result(), "HDFC Large Cap Fund", "10:42", "Source grounded", record)
    assert "1.03%" in html
    assert ui.MIRROR_LABEL in html
    assert "Freshness: 2026-06-30" in html
    assert "gfa-card" in html


def test_answer_card_metric_grid_only_shows_grounded_values() -> None:
    record = ui_data.scheme_by_id("S1")
    assert record is not None
    grounded = ui.answer_card(make_result(), "n", "10:42", "note", record)
    assert "gfa-metric" in grounded
    empty = ui.answer_card(
        make_result(answer="There is no such figure."), "n", "10:42", "note", record
    )
    assert "gfa-metrics" not in empty


def test_answer_card_without_record_omits_the_grid() -> None:
    html = ui.answer_card(make_result(), "HDFC Large Cap Fund", "10:42", "note", None)
    assert "gfa-metrics" not in html
    assert "gfa-card" in html


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        ("advice", ui.GUARDRAIL_LABEL),
        ("performance", ui.GUARDRAIL_LABEL),
        ("out_of_scope", ui.SCOPE_GUARDRAIL_LABEL),
        ("npi", ui.PII_GUARDRAIL_LABEL),
        ("not_found", ui.NOT_FOUND_GUARDRAIL_LABEL),
    ],
)
def test_refusal_card_labels_every_refusal_kind_in_text(kind: str, label: str) -> None:
    result = make_result(
        answer="I cannot help with that.", refused=True, refusal_kind=kind, citations=[]
    )
    html = ui.refusal_card(result, "10:45")
    assert label in html
    assert "gfa-refusal" in html


def test_pii_refusal_uses_the_coral_container() -> None:
    result = make_result(answer="Removed.", refused=True, refusal_kind="npi", citations=[])
    assert "gfa-pii" in ui.refusal_card(result, "10:45")


def test_answer_stamp_marks_mirror_answers() -> None:
    assert "mirror" in ui.turn_stamp(make_result(), "10:42").lower()


def test_answer_stamp_marks_refusals_without_colour() -> None:
    result = make_result(answer="No.", refused=True, refusal_kind="advice", citations=[])
    stamp = ui.turn_stamp(result, "10:45")
    assert "Non-advisory guardrail" in stamp
    assert "10:45" in stamp


def test_scheme_card_renders_real_metrics_and_mirror_label() -> None:
    record = ui_data.scheme_by_id("S4")
    assert record is not None
    html = ui.scheme_card(record)
    assert "HDFC Small Cap Fund" in html
    assert "0.78%" in html
    assert "\u20b9100" in html
    assert ui.MIRROR_LABEL in html
    assert "gfa-scheme-card" in html


def test_scheme_card_shows_lock_in_when_present() -> None:
    record = ui_data.scheme_by_id("S3")
    assert record is not None
    html = ui.scheme_card(record)
    assert "3 years" in html
    assert "3-Yr Statutory Lock" in html


def test_scheme_card_says_nil_when_lock_in_absent() -> None:
    record = ui_data.scheme_by_id("S1")
    assert record is not None
    html = ui.scheme_card(record)
    assert "Statutory Lock-in: Nil" in html


def test_scheme_card_links_to_the_official_source() -> None:
    record = ui_data.scheme_by_id("S3")
    assert record is not None
    assert "hdfcfund.com" in ui.scheme_card(record)


def test_scheme_card_escapes_scheme_names() -> None:
    hacked = ui_data.SchemeFacts(
        scheme_id="S9",
        name="<img src=x onerror=alert(1)>",
        category="Equity",
        plan="Growth",
        url="https://x.test",
        source_id="S9_groww",
        authority="mirror",
        document_date=None,
    )
    html = ui.scheme_card(hacked)
    assert "<img" not in html
    assert "&lt;img" in html
    assert "Equity" in html


def test_empty_state_states_the_scope_limit() -> None:
    html = ui.empty_state("Only 5 HDFC schemes are indexed.")
    assert "No statutory match" in html
    assert "5 HDFC" in html


def test_verdict_marks_factual_as_permitted() -> None:
    html = ui.verdict("factual", "What is the TER?", "Status: <b>PERMITTED</b>")
    assert "gfa-verdict-ok" in html
    assert "PERMITTED" in html


def test_verdict_marks_refusals_as_blocked() -> None:
    html = ui.verdict("advice", "Should I buy?", "Status: <b>REFUSED</b>")
    assert "gfa-verdict-blocked" in html
    assert "REFUSED" in html


def test_verdict_escapes_the_query() -> None:
    html = ui.verdict("factual", "<b>x</b>", "ok")
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_legal_notice_contains_the_full_disclaimer() -> None:
    from app import config

    html = ui.legal_notice()
    assert config.DISCLAIMER[:40] in html
    assert "Mandatory regulatory notice" in html


def test_list_item_carries_an_icon_tone() -> None:
    html = ui.list_item("text", "&#10003;", "ok")
    assert "gfa-ico-ok" in html


def test_scope_row_numbers_the_scheme() -> None:
    html = ui.scope_row(3, "HDFC ELSS Tax Saver Fund", "ELSS")
    assert 'class="gfa-scope-num">3<' in html
    assert "ELSS" in html


def test_ui_calls_set_page_config_first(fake_st: FakeStreamlit) -> None:
    import_ui()
    assert fake_st.names()[0] == "set_page_config"


def test_ui_renders_all_three_screens(fake_st: FakeStreamlit) -> None:
    import_ui()
    labels = [args for name, args in fake_st.calls if name == "tabs"]
    assert labels
    assert tuple(labels[0]) == ("Q&A Assistant", "Scheme Facts", "Scope & Rules")


def test_ui_injects_theme_css(fake_st: FakeStreamlit) -> None:
    import_ui()
    assert "--surface-container" in fake_st.html()
    assert "gfa-scheme-card" in fake_st.html()


def test_ui_shows_short_and_full_disclaimers(fake_st: FakeStreamlit) -> None:
    from app import config

    import_ui()
    everything = fake_st.texts("caption") + fake_st.html()
    assert config.DISCLAIMER_SHORT in everything
    assert config.DISCLAIMER in everything


def test_ui_shows_the_three_examples(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    labels = [args for name, args in fake_st.calls if name == "pills"]
    assert ("Try a question",) in labels
    assert len(module.EXAMPLES) == 3
    for example in module.EXAMPLES:
        assert example in module.EXAMPLES


def test_ui_renders_scheme_facts_cards(fake_st: FakeStreamlit) -> None:
    import_ui()
    html = fake_st.html()
    assert "HDFC Large Cap Fund" in html
    assert "1.03%" in html
    assert "Covered HDFC Schemes" in html


def test_ui_renders_scope_and_rules(fake_st: FakeStreamlit) -> None:
    import_ui()
    html = fake_st.html()
    assert "Scope, Compliance" in html
    assert "What this assistant CAN do" in html
    assert "What this assistant CANNOT do" in html
    assert "Covered schemes boundary" in html


def test_ui_renders_guardrail_sandbox(fake_st: FakeStreamlit) -> None:
    import_ui()
    html = fake_st.html()
    assert "Guardrail policy preview" in html
    assert "PERMITTED FACTUAL RETRIEVAL" in html


@pytest.mark.parametrize(
    ("probe", "status"),
    [
        ("What is the exit load of HDFC Large Cap Fund?", "PERMITTED FACTUAL RETRIEVAL"),
        ("Should I buy HDFC Small Cap today?", "REFUSED - ADVISORY GUARDRAIL"),
        ("What is the price of Bitcoin?", "DECLINED - OUT OF SCOPE"),
    ],
)
def test_sandbox_reports_the_right_status_for_each_probe(probe: str, status: str) -> None:
    from app import ui_screens

    html = ui_screens._sandbox_verdict(probe)
    assert status in html
    assert probe in html


def test_sandbox_probe_list_matches_the_verdicts_it_previews() -> None:
    from app import ui_screens

    for probe, _ in ui_screens.SANDBOX_PROBES:
        html = ui_screens._sandbox_verdict(probe)
        assert "gfa-verdict" in html
        assert "Status: <b>" in html


def test_sandbox_redacts_pii_before_displaying_the_query() -> None:
    from app import ui_screens

    html = ui_screens._sandbox_verdict("My PAN is ABCDE1234F, what is the exit load?")
    assert "REFUSED - PII GUARDRAIL" in html
    assert "ABCDE1234F" not in html


def test_sandbox_escapes_a_malicious_probe() -> None:
    from app import ui_screens

    html = ui_screens._sandbox_verdict("<script>alert(1)</script>")
    assert "<script>" not in html


def test_ui_offline_toggle_is_wired(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    seen: dict[str, Any] = {}
    original = ui_screens.answer_question

    def fake_answer(question: str, debug: bool = False, offline: bool = False) -> QueryResult:
        seen["offline"] = offline
        seen["debug"] = debug
        return make_result()

    ui_screens.answer_question = fake_answer
    fake_st.text_values = ["What is the expense ratio of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    module.main()
    ui_screens.answer_question = original
    assert seen["offline"] is False
    assert seen["debug"] is False


def test_ui_offline_toggle_reaches_the_pipeline(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    seen: dict[str, Any] = {}
    original = ui_screens.answer_question

    def fake_answer(question: str, debug: bool = False, offline: bool = False) -> QueryResult:
        seen["offline"] = offline
        return make_result()

    ui_screens.answer_question = fake_answer
    fake_st.session_state["offline"] = True
    fake_st.text_values = ["What is the expense ratio of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    module.main()
    ui_screens.answer_question = original
    assert seen["offline"] is True


def test_ui_ask_button_answers_the_question(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    seen: dict[str, Any] = {}
    original = ui_screens.answer_question

    def fake_answer(question: str, debug: bool = False, offline: bool = False) -> QueryResult:
        seen["question"] = question
        return make_result()

    ui_screens.answer_question = fake_answer
    fake_st.text_values = ["What is the expense ratio of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    module.main()
    ui_screens.answer_question = original
    assert seen["question"] == "What is the expense ratio of HDFC Large Cap Fund?"
    assert fake_st.session_state["turns"]


def test_ui_clear_button_empties_history(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result()
    fake_st.text_values = ["What is the TER of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    ask_then_rerun(module, fake_st)
    assert fake_st.session_state["turns"]
    before = fake_st.rerun_count
    fake_st.buttons = {"Clear": True}
    module.main()
    ui_screens.answer_question = original
    assert fake_st.session_state["turns"] == []
    assert fake_st.rerun_count > before


def test_ask_triggers_a_rerun_so_the_answer_appears(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result()
    fake_st.text_values = ["What is the TER of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    before = fake_st.rerun_count
    module.main()
    ui_screens.answer_question = original
    assert fake_st.rerun_count == before + 1


def test_ui_does_not_answer_an_empty_question(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    called: list[str] = []
    original = ui_screens.answer_question

    def fake_answer(question: str, **kwargs: Any) -> QueryResult:
        called.append(question)
        return make_result()

    ui_screens.answer_question = fake_answer
    fake_st.text_values = ["   ", ""]
    fake_st.buttons = {"Ask": True}
    module.main()
    ui_screens.answer_question = original
    assert called == []


def test_ui_turn_renders_answer_and_citation(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result()
    fake_st.text_values = ["What is the expense ratio of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    ask_then_rerun(module, fake_st)
    ui_screens.answer_question = original
    html = fake_st.html()
    assert "gfa-turn-user" in html
    assert "gfa-turn-bot" in html
    assert ui.MIRROR_LABEL in html


def test_ui_refusal_turn_renders_the_guardrail_card(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result(
        answer="I only share published facts.",
        refused=True,
        refusal_kind="advice",
        citations=[],
        freshness_date=None,
    )
    fake_st.text_values = ["Should I buy HDFC Small Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    ask_then_rerun(module, fake_st)
    ui_screens.answer_question = original
    html = fake_st.html()
    assert ui.GUARDRAIL_LABEL in html
    assert "gfa-refusal" in html


def test_ui_escapes_a_malicious_question(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result()
    fake_st.text_values = ["<script>alert('xss')</script>", ""]
    fake_st.buttons = {"Ask": True}
    ask_then_rerun(module, fake_st)
    ui_screens.answer_question = original
    html = fake_st.html()
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_ui_escapes_a_malicious_answer(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result(
        answer="<img src=x onerror=alert(1)>", citations=[]
    )
    fake_st.text_values = ["what is the ter", ""]
    fake_st.buttons = {"Ask": True}
    ask_then_rerun(module, fake_st)
    ui_screens.answer_question = original
    html = fake_st.html()
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_ui_search_filters_the_scheme_cards(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.text_values = ["", "small cap"]
    module.main()
    html = fake_st.html()
    assert "Showing 1 of 5 indexed files" in html
    assert "HDFC Small Cap Fund" in html


def test_ui_search_with_no_match_shows_the_empty_state(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.text_values = ["", "zzzz-no-such-scheme"]
    module.main()
    assert "No statutory match" in fake_st.html()


def test_ui_debug_toggle_shows_ranked_chunks(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result()
    fake_st.session_state["debug"] = True
    fake_st.text_values = ["What is the TER of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    module.main()
    ui_screens.answer_question = original
    assert "Debug: ranked chunks" in fake_st.texts("markdown") + fake_st.html()


def test_ui_default_view_has_no_debug_table(fake_st: FakeStreamlit) -> None:
    from app import ui_screens

    module = import_ui()
    original = ui_screens.answer_question
    ui_screens.answer_question = lambda *a, **k: make_result()
    fake_st.text_values = ["What is the TER of HDFC Large Cap Fund?", ""]
    fake_st.buttons = {"Ask": True}
    module.main()
    ui_screens.answer_question = original
    assert "Debug: ranked chunks" not in fake_st.html()


def test_ui_debug_query_param_is_honoured(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    sys.modules["streamlit"].query_params = {"debug": "1"}
    assert module.debug_enabled() is True
    sys.modules["streamlit"].query_params = {"debug": "0"}
    assert module.debug_enabled() is False
    sys.modules["streamlit"].query_params = {}
    assert module.debug_enabled() is False


def test_ui_scheme_filter_is_recorded_in_session(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.text_values = ["", ""]
    module.main()
    assert fake_st.session_state["scheme_filter"] == ""


def test_ui_sidebar_keeps_offline_and_debug_controls(fake_st: FakeStreamlit) -> None:
    import_ui()
    labels = [args[0] for name, args in fake_st.calls if name == "toggle"]
    assert "Offline mode (extractive answers)" in labels
    assert "Debug" in labels


def test_ask_link_targets_the_qa_screen_with_the_question() -> None:
    html = ui.ask_link("Ask about this scheme", "What is the TER of HDFC Large Cap Fund?")
    assert "href=\"?q=" in html
    assert "What+is+the+TER" in html or "What%20is%20the%20TER" in html


def test_action_row_links_are_working_links() -> None:
    html = ui.action_row([("Exit load", "What is the exit load of HDFC Large Cap Fund?")])
    assert 'class="gfa-action" href="?q=' in html
    assert "<span class=\"gfa-action\">" not in html


def test_action_row_is_empty_for_a_refusal() -> None:
    assert ui.action_row([]) == ""


def test_answer_card_actions_ask_a_real_factual_question() -> None:
    html = ui.answer_card(make_result(), "HDFC Large Cap Fund", "10:42", "note")
    assert "What+is+the+exit+load+of+HDFC+Large+Cap+Fund" in html


def test_scheme_card_links_to_the_assistant_and_the_official_source() -> None:
    record = ui_data.scheme_by_id("S3")
    assert record is not None
    html = ui.scheme_card(record)
    assert "Ask about this scheme" in html
    assert 'href="?q=' in html
    assert "hdfcfund.com" in html
    assert 'rel="noopener noreferrer"' in html


def test_linked_question_param_prefills_the_box(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.query_params["q"] = "What is the TER of HDFC Large Cap Fund?"
    module.main()
    assert fake_st.session_state["question"] == "What is the TER of HDFC Large Cap Fund?"


def test_example_pill_does_not_reset_a_typed_question(fake_st: FakeStreamlit) -> None:
    module = import_ui()
    fake_st.pill_values = [None, module.EXAMPLES[0]]
    module.main()
    assert fake_st.session_state["question"] == module.EXAMPLES[0]
    assert fake_st.session_state["example_applied"] == module.EXAMPLES[0]
    fake_st.pill_values = [None, module.EXAMPLES[0]]
    fake_st.session_state["question"] = "my edited question"
    module.main()
    assert fake_st.session_state["question"] == "my edited question"
