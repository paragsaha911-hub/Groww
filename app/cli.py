from __future__ import annotations

import argparse
import json
import os
import sys

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import config
from app.models import AUTHORITY_MIRROR, QueryResult
from app.pipeline import answer_question, load_trace

WELCOME = "HDFC AMC scheme facts assistant. Facts only, no investment advice."
EXAMPLES = (
    "What is the expense ratio of HDFC Large Cap Fund?",
    "Is there an exit load on HDFC ELSS Tax Saver Fund?",
    "What is the riskometer level of HDFC Balanced Advantage Fund?",
)
REFUSAL_LABEL = "REFUSED"
NOT_ANSWERABLE_LABEL = "Not answerable from the current sources"
MIRROR_LABEL = "Mirror source"
DEBUG_HEADERS = ("#", "chunk_id", "fused", "cosine", "lexical", "rerank", "best", "section")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.cli",
        description="Ask a factual question about HDFC AMC schemes.",
    )
    parser.add_argument("question", nargs="*", help="the question to answer")
    parser.add_argument("--debug", action="store_true", help="show ranked chunks and scores")
    parser.add_argument("--offline", action="store_true", help="skip the LLM, answer extractively")
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    return parser


def _quiet_transformers() -> None:
    try:
        from transformers.utils import logging as hf_logging
    except ImportError:
        return
    hf_logging.disable_progress_bar()
    hf_logging.set_verbosity_error()


def render_welcome(console: Console) -> None:
    console.print(Text(WELCOME, style="bold"))
    console.print(Text(config.DISCLAIMER_SHORT, style="italic dim"))
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("example question")
    for example in EXAMPLES:
        table.add_row(example)
    console.print(table)


def render_answer(console: Console, result: QueryResult) -> None:
    if result.refused:
        heading = (
            f"{REFUSAL_LABEL} - {NOT_ANSWERABLE_LABEL}"
            if result.refusal_kind == "not_found"
            else f"{REFUSAL_LABEL} - {result.refusal_kind}"
        )
        console.print(Panel(Text(heading, style="bold"), border_style="yellow", expand=False))
        console.print(Text(result.answer))
        return
    console.print(Text(result.answer))
    if result.citations:
        lines = []
        for citation in result.citations:
            label = f"{citation.label()} - {citation.authority}"
            if citation.authority == AUTHORITY_MIRROR:
                label = f"{MIRROR_LABEL}: {label}"
            lines.append(label)
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("source")
        for line in lines:
            table.add_row(line)
        console.print(table)
    else:
        console.print(Text("No citation resolved.", style="dim"))
    if result.freshness_date:
        console.print(Text(f"Freshness: {result.freshness_date.isoformat()}", style="dim"))
    console.print(
        Text(
            f"intent={result.intent} generator={result.generator} "
            f"authority={result.authority} latency={result.latency_ms}ms",
            style="dim",
        )
    )


def render_debug(console: Console, result: QueryResult) -> None:
    record = load_trace(result.trace_id) or {}
    table = Table(show_header=True, header_style="bold")
    for header in DEBUG_HEADERS:
        table.add_column(header)
    retrieved = record.get("retrieved") or []
    for item in retrieved:
        table.add_row(
            str(item.get("rank", "")),
            str(item.get("chunk_id", "")),
            f"{float(item.get('fused_score', 0.0)):.4f}",
            f"{float(item.get('cosine_score', 0.0)):.4f}",
            f"{float(item.get('lexical_score', 0.0)):.4f}",
            f"{float(item.get('rerank_score', 0.0)):.4f}",
            f"{float(item.get('best_score', 0.0)):.4f}",
            str(item.get("section", "")),
        )
    console.print(table)
    console.print(
        Text(
            f"trace_id={result.trace_id} corpus={record.get('corpus_version', '?')} "
            f"embed={record.get('embed_model', '?')}",
            style="dim",
        )
    )


def render_footer(console: Console) -> None:
    console.print(Text(config.SCOPE_STATEMENT, style="dim"))
    console.print(Text(config.DISCLAIMER, style="dim"))


def to_json(result: QueryResult, debug: bool) -> str:
    payload = {
        "answer": result.answer,
        "intent": result.intent,
        "refused": result.refused,
        "refusal_kind": result.refusal_kind,
        "sentences": result.sentences,
        "citations": [
            {
                "source_id": citation.source_id,
                "url": citation.url,
                "section": citation.section_title,
                "authority": citation.authority,
                "page": citation.page,
            }
            for citation in result.citations
        ],
        "freshness_date": (
            result.freshness_date.isoformat() if result.freshness_date else None
        ),
        "authority": result.authority,
        "generator": result.generator,
        "latency_ms": result.latency_ms,
        "trace_id": result.trace_id,
    }
    if debug:
        payload["retrieved"] = (load_trace(result.trace_id) or {}).get("retrieved", [])
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    _quiet_transformers()

    question = " ".join(args.question).strip()
    if not question:
        render_welcome(console)
        render_footer(console)
        return 0

    result = answer_question(
        question,
        debug=args.debug,
        offline=args.offline,
    )

    if args.json:
        print(to_json(result, args.debug))
        return 0 if not result.refused else 1

    render_answer(console, result)
    if args.debug:
        render_debug(console, result)
    render_footer(console)
    return 0 if not result.refused else 1


if __name__ == "__main__":
    sys.exit(main())
