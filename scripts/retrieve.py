from __future__ import annotations

import argparse
import json
import os
import sys

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from app import config
from app.retrieve.retriever import FLOOR_METRIC, HybridRetriever

HEADER = (
    f"{'#':>2}  {'chunk_id':<22} {'fused':>7} {'cosine':>7} "
    f"{'lexical':>8} {'rerank':>8} {'best':>7}  section"
)


def _quiet_transformers() -> None:
    try:
        from transformers.utils import logging as hf_logging
    except ImportError:
        return
    hf_logging.disable_progress_bar()
    hf_logging.set_verbosity_error()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.retrieve",
        description="Retrieve ranked chunks for a question. Retrieval only, no generation.",
    )
    parser.add_argument("question", help="natural-language question")
    parser.add_argument("--debug", action="store_true", help="print the full score table")
    parser.add_argument("--top-k", type=int, default=None, help="override config.TOP_K")
    parser.add_argument("--json", action="store_true", help="emit the retrieval trace as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _quiet_transformers()
    retriever = HybridRetriever()
    result = retriever.retrieve(args.question, top_k=args.top_k)

    if args.json:
        payload = {
            "query": result.query,
            "scheme_filter": result.scheme_filter,
            "floor": result.floor,
            "floor_metric": FLOOR_METRIC,
            "passed_floor": result.passed_floor,
            "candidates": result.candidate_count,
            "best_score": round(result.best_score, 4),
            "lexical_backend": result.lexical_backend,
            "reranker": result.reranker,
            "pii_detected": result.pii_detected,
            "chunks": result.to_trace(),
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.passed_floor else 1

    print(f"query         : {result.query}")
    print(f"scheme filter : {result.scheme_filter or '(none)'}")
    print(f"candidates    : {result.candidate_count}  (fetched {config.TOP_K_FETCH} max)")
    print(f"lexical       : {result.lexical_backend}")
    print(f"reranker      : {result.reranker}")
    print(f"pii detected  : {result.pii_detected}")
    print(
        f"floor         : {result.floor} on {FLOOR_METRIC} "
        f"(best {round(result.best_score, 4)})"
    )

    if not result.passed_floor:
        print("\npassed_floor  : False -> below floor, returning no chunks")
        if result.nearest:
            print("\nnearest links (not answerable from sources):")
            for item in result.nearest[: config.TOP_K]:
                print(f"  {item.chunk.url}  [{item.chunk.section_title}]")
        return 1

    print(f"passed_floor  : True  ({len(result.chunks)} chunks)")
    if args.debug and result.chunks:
        print()
        print(HEADER)
        print("-" * len(HEADER))
        for item in result.chunks:
            print(
                f"{item.rank:>2}  {item.chunk_id:<22} {item.fused_score:>7.4f} "
                f"{item.cosine_score:>7.4f} {item.lexical_score:>8.4f} "
                f"{item.rerank_score:>8.4f} {item.best_score:>7.4f}  "
                f"{item.chunk.section_title}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
