from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[1]
PORT = 8777

GEOMETRY = """
() => {
  const tabs = [...document.querySelectorAll('[data-testid="stTab"]')];
  const rows = tabs.map(t => {
    const r = t.getBoundingClientRect();
    const p = t.querySelector('[data-testid="stMarkdownContainer"] p');
    const pr = p ? p.getBoundingClientRect() : null;
    const ind = t.querySelector('.react-aria-SelectionIndicator');
    const ir = ind ? ind.getBoundingClientRect() : null;
    return {
      text: t.innerText.trim(),
      selected: t.getAttribute('aria-selected') === 'true',
      x: r.x, w: r.width, right: r.right,
      labelX: pr ? pr.x : null, labelW: pr ? pr.width : null,
      labelWrap: p ? p.getClientRects().length : 0,
      indicators: t.querySelectorAll('.react-aria-SelectionIndicator').length,
      indX: ir ? ir.x : null, indW: ir ? ir.width : null,
    };
  });
  const overlaps = [];
  for (let i = 0; i < rows.length; i++) {
    for (let j = i + 1; j < rows.length; j++) {
      const a = rows[i], b = rows[j];
      if (a.labelX < b.labelX + b.labelW && b.labelX < a.labelX + a.labelW) {
        overlaps.push([a.text, b.text]);
      }
    }
  }
  return {rows, overlaps, tabCount: tabs.length,
          tablistCount: document.querySelectorAll('[data-testid="stTabs"] [role="tablist"]').length};
}
"""


def _wait_for_port(port: int, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("localhost", port), 1).close()
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("streamlit did not start")


@pytest.fixture(scope="module")
def browser():
    try:
        with playwright_api.sync_playwright() as p:
            try:
                instance = p.chromium.launch()
            except Exception as exc:  # pragma: no cover - environment dependent
                pytest.skip(f"chromium unavailable: {exc}")
            yield instance
            instance.close()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"playwright unavailable: {exc}")


@pytest.fixture(scope="module")
def page(browser):
    server = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app/ui.py",
            f"--server.port={PORT}", "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(PORT)
        tab = browser.new_page(viewport={"width": 1280, "height": 900})
        tab.goto(f"http://localhost:{PORT}", wait_until="networkidle", timeout=120000)
        tab.wait_for_timeout(4000)
        yield tab
        tab.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:  # pragma: no cover
            server.kill()


def test_tab_bar_renders_exactly_three_tabs_once(page) -> None:
    result = page.evaluate(GEOMETRY)
    assert result["tablistCount"] == 1
    assert result["tabCount"] == 3
    assert [row["text"] for row in result["rows"]] == [
        "Q&A Assistant", "Scheme Facts", "Scope & Rules",
    ]


def test_tab_labels_do_not_overlap(page) -> None:
    result = page.evaluate(GEOMETRY)
    assert result["overlaps"] == []


def test_tab_labels_are_on_a_single_line(page) -> None:
    result = page.evaluate(GEOMETRY)
    for row in result["rows"]:
        assert row["labelWrap"] == 1, f"{row['text']} wrapped onto multiple lines"


def test_only_one_tab_is_active_and_it_has_one_indicator(page) -> None:
    result = page.evaluate(GEOMETRY)
    active = [row for row in result["rows"] if row["selected"]]
    assert len(active) == 1
    assert active[0]["indicators"] == 1
    assert sum(row["indicators"] for row in result["rows"]) == 1


def test_active_underline_matches_the_active_label_box(page) -> None:
    result = page.evaluate(GEOMETRY)
    active = next(row for row in result["rows"] if row["selected"])
    assert active["indX"] == pytest.approx(active["labelX"], abs=1.0)
    assert active["indW"] == pytest.approx(active["labelW"], abs=1.0)


def test_underline_follows_the_active_tab_when_switching(page) -> None:
    for index in (1, 2, 0):
        page.click(f'[data-testid="stTab"] >> nth={index}')
        page.wait_for_timeout(1800)
        result = page.evaluate(GEOMETRY)
        active = [row for row in result["rows"] if row["selected"]]
        assert len(active) == 1
        assert sum(row["indicators"] for row in result["rows"]) == 1
        assert active[0]["indX"] == pytest.approx(active[0]["labelX"], abs=1.0)
        assert active[0]["indW"] == pytest.approx(active[0]["labelW"], abs=1.0)
        assert result["overlaps"] == []


@pytest.mark.parametrize("width", [1600, 1280, 1024, 768, 480, 375])
def test_no_overlap_at_any_viewport_width(page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.wait_for_timeout(700)
    result = page.evaluate(GEOMETRY)
    assert result["overlaps"] == []
    for row in result["rows"]:
        assert row["labelWrap"] == 1
        assert row["labelW"] <= row["w"] + 1


def test_tablist_uses_flex_with_a_gap(page) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(500)
    style = page.evaluate(
        """() => {
          const l = document.querySelector('[data-testid="stTabs"] [role="tablist"]');
          const s = getComputedStyle(l);
          return {display: s.display, gap: s.gap, wrap: s.flexWrap};
        }"""
    )
    assert style["display"] == "flex"
    assert style["gap"] not in ("0px", "normal")
    assert style["wrap"] == "nowrap"
