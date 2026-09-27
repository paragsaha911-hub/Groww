from __future__ import annotations

import io
import json

import pytest

from app import config
from app.ingest import parse
from app.ingest.fetch import FetchResult
from app.models import approx_token_count

SOURCE = {
    "source_id": "S1_test",
    "scheme_id": "S1",
    "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "authority": "mirror",
    "title": "HDFC Large Cap Fund",
    "expected_facts": ["expense_ratio", "exit_load", "min_sip", "benchmark", "riskometer"],
}

MIRROR_PAYLOAD = {
    "isin": "INF179K01YV8",
    "scheme_name": "HDFC Large Cap Fund Direct Growth",
    "fund_name": "HDFC Large Cap Fund",
    "plan_type": "Direct",
    "scheme_type": "Growth",
    "expense_ratio": "1.03",
    "exit_load": "Exit load of 1% if redeemed within 1 year",
    "benchmark": "NIFTY 100 TRI",
    "benchmark_name": "NIFTY 100 Total Return Index",
    "min_sip_investment": 100,
    "min_investment_amount": 100,
    "nfo_risk": "Moderately High Riskometer",
    "lock_in": {"years": None, "months": None, "days": None},
    "description": "An open ended equity scheme investing in large cap stocks.",
    "fund_house": "HDFC Mutual Fund",
    "fund_manager": "Prashant Jain",
    "launch_date": "01-Jan-2013",
    "registrar_agent": "RTA",
    "sub_category": "Large Cap",
    "aum": 39933.3663,
    "nav": 1189.079,
    "nav_date": "25-Sep-2026",
    "holdings": [{"name": "Reliance Industries", "weight": 9.1}],
}

FACTSHEET_PAGE = """
HDFC Large Cap Fund
ISIN: INF179K01YV8
EXPENSE RATIO (As On June 30, 2026) Base expense Ratio
Regular: 1.56% Direct: 1.03%
EXIT LOAD
In respect of each purchase / switch-in of Units, an Exit Load of 1.00% is payable if
Units are redeemed / switched-out within 1 year from the date of allotment.
Benchmark: NIFTY 100 TRI
Benchmark and Scheme riskometers: Very High Riskometer
"""


def _mirror_html(payload: dict) -> str:
    blob = json.dumps({"props": {"pageProps": {"mfServerSideData": payload}}})
    return (
        "<!DOCTYPE html><html><head><title>x</title>"
        f'<script id="__NEXT_DATA__" type="application/json" nonce="abc">{blob}</script>'
        "</head><body><h1>HDFC Large Cap Fund</h1><p>rendered text</p></body></html>"
    )


def _html_fetch(html: str, tmp_path, name: str = "page.html") -> FetchResult:
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return FetchResult(
        source_id=SOURCE["source_id"],
        url=SOURCE["url"],
        ok=True,
        raw_path=str(path),
        kind="html",
        extraction_method="mirror",
    )


def test_noise_tags_are_removed() -> None:
    html = """
    <html><body>
      <script>var tracker = 1;</script>
      <style>body{color:red}</style>
      <nav>Home About</nav>
      <footer>Copyright</footer>
      <div class="cookie-consent">Accept cookies</div>
      <div id="signup-modal">Subscribe now</div>
      <h2>Expense ratio</h2><p>Expense ratio 1.35%</p>
    </body></html>
    """
    text, _ = parse.parse_html_sections(html)
    for junk in ("tracker", "color:red", "Home About", "Copyright", "Accept cookies", "Subscribe now"):
        assert junk not in text, junk
    assert "Expense ratio 1.35%" in text


def test_nested_headings_produce_correct_heading_path() -> None:
    html = """
    <html><body>
      <h1>Factsheets</h1>
      <h2>Equity</h2>
      <h3>HDFC Large Cap Fund</h3>
      <p>ISIN INF179K01YV8</p>
      <h3>HDFC Small Cap Fund</h3>
      <p>ISIN INF179KA1RW5</p>
    </body></html>
    """
    _, sections = parse.parse_html_sections(html)
    titles = [section.title for section in sections]
    assert titles == ["Factsheets", "Equity", "HDFC Large Cap Fund", "HDFC Small Cap Fund"]
    by_title = {section.title: section for section in sections}
    assert by_title["HDFC Large Cap Fund"].heading_path == "Factsheets>Equity>HDFC Large Cap Fund"
    assert by_title["HDFC Small Cap Fund"].heading_path == "Factsheets>Equity>HDFC Small Cap Fund"
    assert by_title["HDFC Large Cap Fund"].level == 3


def test_char_offsets_point_at_the_right_text() -> None:
    html = "<html><body><h1>A</h1><p>alpha</p><h1>B</h1><p>beta</p></body></html>"
    text, sections = parse.parse_html_sections(html)
    for section in sections:
        assert text[section.char_start : section.char_end].strip() == section.text.strip()
    assert text.index("alpha") < text.index("beta")


def test_pipe_table_preserves_every_number() -> None:
    html = """
    <html><body><h1>Fees</h1>
    <table>
      <tr><th>Plan</th><th>Regular</th><th>Direct</th></tr>
      <tr><td>Expense ratio</td><td>1.56%</td><td>1.03%</td></tr>
      <tr><td>Exit load</td><td>1.00%</td><td>1.00%</td></tr>
    </table>
    </body></html>
    """
    text, _ = parse.parse_html_sections(html)
    for number in ("1.56%", "1.03%", "1.00%", "Expense ratio", "Exit load"):
        assert number in text, number
    assert "1.56% | 1.03%" in text
    assert "<table" not in text and "<td>" not in text


def test_mirror_fields_are_read_from_next_data_not_rendered_text() -> None:
    html = _mirror_html(MIRROR_PAYLOAD)
    text, sections, fields = parse.mirror_sections(MIRROR_PAYLOAD)
    assert fields["expense_ratio"] == "1.03"
    assert fields["exit_load"] == "Exit load of 1% if redeemed within 1 year"
    assert fields["min_sip"] == "100"
    assert fields["min_amount"] == "100"
    assert fields["benchmark"] == "NIFTY 100 TRI"
    assert fields["riskometer"] == "Moderately High"
    assert "lock_in" not in fields
    assert "Expense ratio: 1.03%" in text
    assert [section.title for section in sections][:3] == [
        "Scheme identity",
        "Objective",
        "Expense ratio",
    ]


def test_mirror_riskometer_variants_normalise_identically() -> None:
    with_suffix = parse.normalise_riskometer("Moderately High Riskometer")
    without = parse.normalise_riskometer("Moderately High")
    assert with_suffix == without == "Moderately High"


def test_lock_in_formatting() -> None:
    assert parse.format_lock_in({"years": 3, "months": 0, "days": 0}) == "3 years"
    assert parse.format_lock_in({"years": 1, "months": 6, "days": 0}) == "1 year 6 months"
    assert parse.format_lock_in({"years": None, "months": None, "days": None}) is None
    assert parse.format_lock_in(None) is None


def test_elss_lock_in_flows_through_to_fields() -> None:
    payload = {**MIRROR_PAYLOAD, "lock_in": {"years": 3, "months": 0, "days": 0}}
    _, _, fields = parse.mirror_sections(payload)
    assert fields["lock_in"] == "3 years"


def test_regular_direct_ter_never_returns_the_regular_value() -> None:
    block = "EXPENSE RATIO (As On June 30, 2026) Regular: 1.56% Direct: 1.03%"
    assert parse.prefer_direct_ter(block) == "1.03%"


def test_fields_are_scoped_by_isin_not_by_page_position() -> None:
    pages = [
        "HDFC Large Cap Fund\nISIN: INF179K01YV8\n"
        "EXPENSE RATIO (As On June 30, 2026) Regular: 1.56% Direct: 1.03%\n"
        "Benchmark: NIFTY 100 TRI\n",
        "HDFC Balanced Advantage Fund\nISIN: INF179K01WA6\n"
        "EXPENSE RATIO (As On June 30, 2026) Regular: 1.75% Direct: 0.92%\n"
        "Benchmark: NIFTY 50 TRI\n",
    ]
    blocks = parse.scope_blocks(pages)
    by_isin = {isin: block for isin, block in blocks if isin}
    assert set(by_isin) == {"INF179K01YV8", "INF179K01WA6"}
    assert parse.prefer_direct_ter(by_isin["INF179K01YV8"]) == "1.03%"
    assert parse.prefer_direct_ter(by_isin["INF179K01WA6"]) == "0.92%"


def test_neighbouring_scheme_number_is_not_borrowed() -> None:
    pages = [
        "ISIN: INF179K01YV8\nEXPENSE RATIO Regular: 1.56% Direct: 1.03%\n",
        "ISIN: INF179K01WA6\nEXPENSE RATIO Regular: 1.75% Direct: 0.92%\n",
    ]
    blocks = parse.scope_blocks(pages)
    assert parse.extract_fields_from_blocks(blocks, "INF179K01YV8")["expense_ratio"] == "1.03%"
    assert parse.extract_fields_from_blocks(blocks, "INF179K01WA6")["expense_ratio"] == "0.92%"


def test_every_scheme_in_one_pdf_gets_its_own_numbers() -> None:
    pages = [
        "\n".join(
            f"ISIN: {isin}\nEXPENSE RATIO Regular: {regular}% Direct: {direct}%\n"
            for isin, regular, direct in (
                ("INF179K01YV8", "1.56", "1.03"),
                ("INF179K01UT0", "1.29", "0.77"),
                ("INF179K01YS4", "2.02", "1.21"),
                ("INF179KA1RW5", "1.30", "0.78"),
                ("INF179K01WA6", "1.29", "0.78"),
            )
        )
    ]
    blocks = parse.scope_blocks(pages)
    for scheme_id, expected in config.SCHEME_ISINS.items():
        fields = parse.extract_fields_from_blocks(blocks, expected)
        assert fields["expense_ratio"], scheme_id


def test_unknown_isin_yields_no_fields_rather_than_the_first_scheme() -> None:
    pages = [
        "ISIN: INF179K01YV8\nEXPENSE RATIO Regular: 1.56% Direct: 1.03%\n",
        "ISIN: INF179K01WA6\nEXPENSE RATIO Regular: 1.75% Direct: 0.92%\n",
    ]
    blocks = parse.scope_blocks(pages)
    assert parse.extract_fields_from_blocks(blocks, "INF179K01ZZZZ") == {}
    assert parse.extract_fields_from_blocks(blocks, None)["expense_ratio"] == "1.03%"


def test_isin_matching_is_case_and_whitespace_insensitive() -> None:
    pages = ["ISIN: inf179k01yv8\nEXPENSE RATIO Regular: 1.56% Direct: 1.03%\n"]
    blocks = parse.scope_blocks(pages)
    assert parse.extract_fields_from_blocks(blocks, " INF179K01YV8 ")["expense_ratio"] == "1.03%"


def test_official_sources_declare_an_isin() -> None:
    for source in config.OFFICIAL_SOURCES:
        assert source.get("isin") == config.SCHEME_ISINS[source["scheme_id"]]
    assert set(config.SCHEME_ISINS) == {s.scheme_id for s in config.SCHEMES}


def test_document_date_detected_from_as_on() -> None:
    assert parse.parse_document_date("EXPENSE RATIO (As On June 30, 2026) 1.03%") == "2026-06-30"
    assert parse.parse_document_date("As of 2026-06-30 something") == "2026-06-30"
    assert parse.parse_document_date("no date here") is None


def test_missing_expected_facts_flag_is_incomplete(tmp_path) -> None:
    payload = {**MIRROR_PAYLOAD}
    del payload["benchmark"]
    result = parse.parse_document(_html_fetch(_mirror_html(payload), tmp_path), SOURCE)
    assert result.is_complete is False
    assert parse.missing_expected_facts(result.fields, SOURCE) == ["benchmark"]


def test_truncated_page_is_incomplete(tmp_path) -> None:
    html = "<html><body><h1>HDFC Large Cap Fund</h1><p>loading</p></body></html>"
    result = parse.parse_document(_html_fetch(html, tmp_path, "thin.html"), SOURCE)
    assert result.is_complete is False
    assert approx_token_count(result.text) < parse.MIN_TEXT_TOKENS


def test_full_mirror_page_is_complete(tmp_path) -> None:
    result = parse.parse_document(_html_fetch(_mirror_html(MIRROR_PAYLOAD), tmp_path), SOURCE)
    assert result.is_complete is True
    assert result.extraction_method == "mirror"
    assert result.document_date == "2026-09-25"


def test_missing_raw_path_is_incomplete_not_an_exception() -> None:
    fetch_result = FetchResult(source_id="s", url="https://groww.in/x", ok=False, raw_path=None)
    result = parse.parse_document(fetch_result, SOURCE)
    assert result.is_complete is False
    assert result.text == ""


def test_generic_html_falls_back_to_regex_fields(tmp_path) -> None:
    html = f"<html><body><h1>HDFC Large Cap Fund</h1><pre>{FACTSHEET_PAGE}</pre></body></html>"
    result = parse.parse_document(_html_fetch(html, tmp_path, "generic.html"), SOURCE)
    assert result.fields["expense_ratio"] == "1.03%"
    assert "1.03%" in result.fields["expense_ratio"]
    assert "NIFTY 100 TRI" in result.fields["benchmark"]


def test_write_outputs_emits_three_reviewable_files(tmp_path, monkeypatch) -> None:
    processed = tmp_path / "processed"
    monkeypatch.setattr(config, "PROCESSED_DIR", processed)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    result = parse.parse_document(_html_fetch(_mirror_html(MIRROR_PAYLOAD), tmp_path), SOURCE)
    paths = parse.write_outputs(result, SOURCE)
    assert paths["md"].is_file() and paths["sections"].is_file() and paths["fields"].is_file()

    md = paths["md"].read_text(encoding="utf-8")
    assert "expense_ratio" not in md
    assert "Expense ratio: 1.03%" in md
    assert "is_complete: True" in md
    assert "source_id: S1_test" in md

    sections = json.loads(paths["sections"].read_text(encoding="utf-8"))
    assert all({"title", "level", "text", "heading_path", "char_start", "char_end"} <= set(s) for s in sections)

    fields = json.loads(paths["fields"].read_text(encoding="utf-8"))
    assert fields["fields"]["expense_ratio"] == "1.03"
    assert fields["missing_facts"] == []
    assert fields["is_complete"] is True
