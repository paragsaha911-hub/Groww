from __future__ import annotations

import io
import sys
import types
from datetime import date
from typing import Any

import pytest
from rich.console import Console

from app import cli
from app.models import AUTHORITY_MIRROR, AUTHORITY_OFFICIAL, Citation, QueryResult


def make_result(**overrides: Any) -> QueryResult:
    base: dict[str, Any] = {
        "answer": "The direct growth expense ratio is 1.12%.",
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


def render(function: Any, *args: Any) -> str:
    buffer = io.StringIO()
    console = Console(file=buffer, width=100, no_color=True, force_terminal=False)
    function(console, *args)
    return buffer.getvalue()


def flat(text: str) -> str:
    return " ".join(text.split())


def test_cli_exposes_exactly_three_examples() -> None:
    assert len(cli.EXAMPLES) == 3
    assert all(question.strip().endswith("?") for question in cli.EXAMPLES)


def test_cli_welcome_shows_examples_and_short_disclaimer() -> None:
    from app import config

    output = flat(render(cli.render_welcome))
    for example in cli.EXAMPLES:
        assert example in output
    assert flat(config.DISCLAIMER_SHORT) in output


def test_cli_footer_contains_full_disclaimer() -> None:
    from app import config

    output = flat(render(cli.render_footer))
    assert flat(config.DISCLAIMER) in output
    assert flat(config.SCOPE_STATEMENT) in output


def test_cli_answer_shows_answer_citation_and_freshness() -> None:
    output = render(cli.render_answer, make_result())
    assert "expense ratio is 1.12%" in output
    assert "groww.in/mutual-funds/hdfc-large-cap-fund" in output
    assert "2026-06-30" in output


def test_cli_labels_mirror_authority_in_words() -> None:
    output = render(cli.render_answer, make_result())
    assert cli.MIRROR_LABEL in output


def test_cli_does_not_label_official_source_as_mirror() -> None:
    result = make_result(
        citations=[
            Citation(
                source_id="hdfc_factsheet",
                url="https://files.hdfcfund.com/x.pdf",
                section_title="Fees",
                authority=AUTHORITY_OFFICIAL,
                page=3,
            )
        ],
        authority=AUTHORITY_OFFICIAL,
    )
    output = render(cli.render_answer, result)
    assert cli.MIRROR_LABEL not in output
    assert "page 3" in output


def test_cli_refusal_is_marked_without_relying_on_colour() -> None:
    result = make_result(
        answer="I only share published facts.",
        refused=True,
        refusal_kind="advice",
        citations=[],
        freshness_date=None,
    )
    output = render(cli.render_answer, result)
    assert cli.REFUSAL_LABEL in output
    assert "advice" in output


def test_cli_not_found_refusal_has_its_own_label() -> None:
    result = make_result(
        answer="I could not find that in my sources.",
        refused=True,
        refusal_kind="not_found",
        citations=[],
        freshness_date=None,
    )
    output = render(cli.render_answer, result)
    assert cli.REFUSAL_LABEL in output
    assert cli.NOT_ANSWERABLE_LABEL in output


def test_cli_answer_notes_intent_generator_and_latency() -> None:
    output = render(cli.render_answer, make_result())
    assert "intent=factual" in output
    assert "generator=groq" in output
    assert "latency=42ms" in output


def test_cli_json_contains_every_contract_field() -> None:
    import json

    payload = json.loads(cli.to_json(make_result(), debug=False))
    for field in (
        "answer",
        "intent",
        "refused",
        "refusal_kind",
        "sentences",
        "citations",
        "freshness_date",
        "authority",
        "generator",
        "latency_ms",
        "trace_id",
    ):
        assert field in payload
    assert payload["freshness_date"] == "2026-06-30"
    assert payload["citations"][0]["source_id"] == "S1_groww"


def test_cli_json_omits_retrieved_when_not_debug() -> None:
    import json

    assert "retrieved" not in json.loads(cli.to_json(make_result(), debug=False))


def test_cli_debug_table_renders_scores() -> None:
    from app import pipeline

    record = {
        "query_sha256": "abc123" + "0" * 48,
        "retrieved": [
            {
                "rank": 1,
                "chunk_id": "S1_groww_c0001",
                "fused_score": 0.0328,
                "cosine_score": 0.7187,
                "lexical_score": 3.8899,
                "rerank_score": 0.3897,
                "best_score": 1.0004,
                "section": "Fees",
            }
        ],
        "corpus_version": "v-test",
        "embed_model": "sentence-transformers/all-MiniLM-L6-v2",
    }
    target = pipeline.TRACES_PATH.parent / "ui_debug_traces.jsonl"
    import json as jsonlib

    target.write_text(jsonlib.dumps(record) + "\n", encoding="utf-8")
    try:
        original = pipeline.load_trace

        def fake_load(trace_id: str, path: Any = None) -> Any:
            return record

        pipeline.load_trace = fake_load
        cli.load_trace = fake_load
        try:
            output = render(cli.render_debug, make_result())
        finally:
            pipeline.load_trace = original
            cli.load_trace = original
    finally:
        target.unlink(missing_ok=True)

    assert "S1_groww_c0001" in output
    assert "0.7187" in output
    assert "Fees" in output
    assert "v-test" in output


def test_cli_debug_table_survives_a_missing_trace() -> None:
    def fake_load(trace_id: str, path: Any = None) -> Any:
        return None

    original = cli.load_trace
    cli.load_trace = fake_load
    try:
        output = render(cli.render_debug, make_result())
    finally:
        cli.load_trace = original
    assert "abc123" in output


def test_cli_parser_exposes_expected_flags() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["what", "is", "ter", "--debug", "--offline", "--json"])
    assert args.debug is True
    assert args.offline is True
    assert args.json is True
    assert args.question == ["what", "is", "ter"]


def test_cli_parser_has_no_trace_suppression_flag() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["hi", "--no-trace"])


class FakeSidebar:
    def __init__(self, calls: list[tuple[str, tuple[Any, ...]]]) -> None:
        self.calls = calls

    def toggle(self, label: str, **kwargs: Any) -> bool:
        self.calls.append(("toggle", (label,)))
        return bool(kwargs.get("value", False))

    def markdown(self, text: str, **kwargs: Any) -> None:
        self.calls.append(("markdown", (text,)))

    def button(self, label: str, **kwargs: Any) -> bool:
        self.calls.append(("button", (label,)))
        return False


class FakeStreamlit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.session_state: dict[str, Any] = {}
        self.query_params: dict[str, str] = {}
        self.sidebar = FakeSidebar(self.calls)
        self.text_input_value = ""

    def record(self, name: str, *args: Any, **kwargs: Any) -> None:
        payload = args or (kwargs,)
        self.calls.append((name, payload))

    def set_page_config(self, **kwargs: Any) -> None:
        self.record("set_page_config", **kwargs)

    def title(self, text: str) -> None:
        self.record("title", text)

    def write(self, text: str = "") -> None:
        self.record("write", text)

    def info(self, text: str) -> None:
        self.record("info", text)

    def caption(self, text: str = "") -> None:
        self.record("caption", text)

    def markdown(self, text: str, **kwargs: Any) -> None:
        self.record("markdown", text)

    def divider(self) -> None:
        self.record("divider")

    def warning(self, text: str, **kwargs: Any) -> None:
        self.record("warning", text)

    def error(self, text: str, **kwargs: Any) -> None:
        self.record("error", text)

    def text_input(self, label: str, **kwargs: Any) -> str:
        self.record("text_input", label)
        return self.text_input_value

    def spinner(self, text: str) -> Any:
        self.record("spinner", text)
        return _NullContext()

    def dataframe(self, data: Any, **kwargs: Any) -> None:
        self.record("dataframe", data)

    def button(self, label: str, **kwargs: Any) -> bool:
        self.record("button", label)
        return False

    def toggle(self, label: str, **kwargs: Any) -> bool:
        self.record("toggle", label)
        return False

    def cache_resource(self, *args: Any, **kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]

        def decorator(function: Any) -> Any:
            return function

        return decorator

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def text_of(self, name: str) -> str:
        return " ".join(str(arg) for _, args in self.calls if _ == name for arg in args)


class _NullContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: Any) -> bool:
        return False


@pytest.fixture()
def fake_st(monkeypatch: pytest.MonkeyPatch) -> Any:
    module = types.ModuleType("streamlit")
    fake = FakeStreamlit()
    for attribute in dir(fake):
        if not attribute.startswith("_"):
            setattr(module, attribute, getattr(fake, attribute))
    monkeypatch.setitem(sys.modules, "streamlit", module)
    monkeypatch.delitem(sys.modules, "app.ui", raising=False)
    return fake


def import_ui() -> Any:
    import app.ui as ui

    return ui


def test_ui_calls_set_page_config_first(fake_st: Any) -> None:
    import_ui()
    assert fake_st.names()[0] == "set_page_config"


def test_ui_declares_three_examples(fake_st: Any) -> None:
    ui = import_ui()
    assert len(ui.EXAMPLES) == 3


def test_ui_renders_short_and_full_disclaimers(fake_st: Any) -> None:
    from app import config

    import_ui()
    text = fake_st.text_of("info") + fake_st.text_of("caption")
    assert config.DISCLAIMER_SHORT in text
    assert config.DISCLAIMER in text


def test_ui_shows_welcome_and_examples(fake_st: Any) -> None:
    ui = import_ui()
    everything = " ".join(str(arg) for _, args in fake_st.calls for arg in args)
    assert ui.WELCOME in everything
    for example in ui.EXAMPLES:
        assert example in everything


def test_ui_answer_renders_text_citation_and_freshness(fake_st: Any) -> None:
    ui = import_ui()
    ui.render_answer(make_result())
    assert "expense ratio is 1.12%" in fake_st.text_of("write")
    assert "groww.in/mutual-funds/hdfc-large-cap-fund" in " ".join(
        str(arg) for name, args in fake_st.calls if name == "markdown" for arg in args
    )
    assert "2026-06-30" in fake_st.text_of("caption")


def test_ui_refusal_uses_warning_and_a_text_label(fake_st: Any) -> None:
    ui = import_ui()
    ui.render_answer(
        make_result(
            answer="I only share published facts.",
            refused=True,
            refusal_kind="advice",
            citations=[],
            freshness_date=None,
        )
    )
    warning = fake_st.text_of("warning")
    assert ui.REFUSAL_LABEL in warning
    assert "advice" in warning
    assert "I only share published facts." in fake_st.text_of("write")


def test_ui_not_found_refusal_has_its_own_label(fake_st: Any) -> None:
    ui = import_ui()
    ui.render_answer(
        make_result(
            answer="I could not find that.",
            refused=True,
            refusal_kind="not_found",
            citations=[],
            freshness_date=None,
        )
    )
    assert ui.NOT_ANSWERABLE_LABEL in fake_st.text_of("warning")


def test_ui_mirror_warning_is_text_not_colour_only(fake_st: Any) -> None:
    ui = import_ui()
    ui.render_answer(make_result())
    captions = fake_st.text_of("caption")
    assert ui.MIRROR_LABEL in captions


def test_ui_debug_renders_ranked_chunks(fake_st: Any) -> None:
    ui = import_ui()
    record = {
        "retrieved": [
            {
                "rank": 1,
                "chunk_id": "S1_groww_c0001",
                "fused_score": 0.03,
                "cosine_score": 0.71,
                "lexical_score": 3.8,
                "rerank_score": 0.38,
                "best_score": 1.0,
                "section": "Fees",
            }
        ],
        "corpus_version": "v-test",
        "embed_model": "m",
    }
    original = ui.load_trace
    ui.load_trace = lambda trace_id, path=None: record
    try:
        ui.render_debug(make_result())
    finally:
        ui.load_trace = original
    payload = [args[0] for name, args in fake_st.calls if name == "dataframe"]
    assert payload
    assert payload[0][0]["chunk_id"] == "S1_groww_c0001"
    assert payload[0][0]["section"] == "Fees"


def test_ui_uses_cached_pipeline_resource(fake_st: Any) -> None:
    import_ui()
    cached = import_ui().get_pipeline()
    assert callable(cached)


def test_ui_debug_query_param_is_honoured(fake_st: Any) -> None:
    ui = import_ui()
    module = sys.modules["streamlit"]
    module.query_params = {"debug": "1"}
    assert ui.debug_enabled() is True
    module.query_params = {"debug": "0"}
    assert ui.debug_enabled() is False
    module.query_params = {}
    assert ui.debug_enabled() is False


def test_ui_debug_session_toggle_is_honoured(fake_st: Any) -> None:
    ui = import_ui()
    fake_st.session_state["debug"] = True
    assert ui.debug_enabled() is True


def test_ui_main_renders_footer_without_a_question(fake_st: Any) -> None:
    ui = import_ui()
    fake_st.text_input_value = ""
    ui.main()
    from app import config

    assert config.DISCLAIMER in fake_st.text_of("caption")
    assert "spinner" not in fake_st.names()


def test_ui_main_calls_answer_question_with_flags(fake_st: Any) -> None:
    ui = import_ui()
    fake_st.text_input_value = "What is the expense ratio of HDFC Large Cap Fund?"
    seen: dict[str, Any] = {}

    def fake_answer(question: str, debug: bool = False, offline: bool = False) -> QueryResult:
        seen["question"] = question
        seen["debug"] = debug
        seen["offline"] = offline
        return make_result()

    ui.answer_question = fake_answer
    ui.get_pipeline = lambda: fake_answer
    ui.main()
    assert seen["question"] == "What is the expense ratio of HDFC Large Cap Fund?"
    assert seen["debug"] is False
    assert seen["offline"] is False
    assert "spinner" in fake_st.names()


def test_ui_main_offline_toggle_is_passed_through(fake_st: Any) -> None:
    ui = import_ui()
    fake_st.text_input_value = "What is the expense ratio of HDFC Large Cap Fund?"
    seen: dict[str, Any] = {}

    def fake_answer(question: str, debug: bool = False, offline: bool = False) -> QueryResult:
        seen["offline"] = offline
        return make_result()

    ui.answer_question = fake_answer
    ui.get_pipeline = lambda: fake_answer

    def offline_toggle(label: str, **kwargs: Any) -> bool:
        return True

    ui.st.sidebar.toggle = offline_toggle
    ui.main()
    assert seen["offline"] is True


def test_both_surfaces_expose_three_matching_examples() -> None:
    assert len(cli.EXAMPLES) == 3


def test_cli_and_ui_share_the_same_disclaimer_source() -> None:
    from app import config

    assert config.DISCLAIMER_SHORT
    assert config.DISCLAIMER
