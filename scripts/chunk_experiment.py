from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import config
from app.ingest import chunk as chunk_mod
from app.ingest import parse as parse_mod
from app.models import Chunk, Document

TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "of", "for", "on", "in", "to",
    "and", "or", "what", "which", "does", "do", "has", "have", "it", "its", "this",
    "that", "these", "those", "be", "been", "by", "from", "at", "as", "my", "me",
    "i", "you", "your", "if", "then", "than", "so", "but", "not", "no", "any",
    "there", "here", "with", "about", "please", "tell", "give", "show", "many",
    "much", "do", "does", "did", "can", "could", "would", "should", "will",
}

PROVISIONAL_NOTE = (
    "PROVISIONAL: retrieval uses a deterministic TF-IDF lexical retriever, not "
    "all-MiniLM-L6-v2 (Phase 8 is not implemented). Absolute scores will not match "
    "the eventual dense retriever. The relative ordering of chunking strategies "
    "under a fixed retriever is still informative, and the comparison is fair "
    "because every strategy uses identical retrieval settings."
)


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in TOKEN.findall(text.lower())
        if token not in STOPWORDS and len(token) > 1
    ]


@dataclass
class LexicalIndex:
    vectors: list[dict[str, float]]
    norms: list[float]
    idf: dict[str, float]

    def score(self, query_tokens: list[str], position: int) -> float:
        vector = self.vectors[position]
        if not vector or not self.norms[position]:
            return 0.0
        total = 0.0
        for token in query_tokens:
            weight = vector.get(token)
            if weight is None:
                continue
            q = self.idf.get(token, 0.0)
            total += weight * q
        return total / (self.norms[position] or 1.0)


def build_index(chunks: list[Chunk]) -> LexicalIndex:
    tokenized = [tokenize(chunk.text) for chunk in chunks]
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))
    total = max(1, len(tokenized))
    idf = {
        token: math.log((total + 1) / (frequency + 1)) + 1.0
        for token, frequency in document_frequency.items()
    }
    vectors: list[dict[str, float]] = []
    norms: list[float] = []
    for tokens in tokenized:
        counts = Counter(tokens)
        length = max(1, len(tokens))
        vector = {
            token: (count / length) * idf.get(token, 0.0) for token, count in counts.items()
        }
        vectors.append(vector)
        norms.append(math.sqrt(sum(weight * weight for weight in vector.values())))
    return LexicalIndex(vectors=vectors, norms=norms, idf=idf)


def retrieve(
    index: LexicalIndex, chunks: list[Chunk], query: str, top_k: int
) -> list[tuple[int, float]]:
    tokens = tokenize(query)
    scored = [(position, index.score(tokens, position)) for position in range(len(chunks))]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [item for item in scored[:top_k] if item[1] > 0.0]


def has_section_heading(chunk_text: str, title: str) -> bool:
    wanted = title.strip().lower()
    for line in chunk_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if stripped.lstrip("#").strip().lower() == wanted:
                return True
    return False


def load_golden_set() -> list[dict[str, Any]]:
    path = config.EVAL_DIR / "golden_set.json"
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(
    documents: list[Document], strategy: str, top_k: int, chunk_size: int | None
) -> dict[str, Any]:
    chunker = chunk_mod.get_chunker(
        strategy, **({"chunk_size": chunk_size} if chunk_size else {})
    )
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunker.split(document))

    index = build_index(chunks)
    golden = load_golden_set()

    hits = 0
    first_hits = 0
    scheme_scored = 0
    reciprocal_ranks: list[float] = []
    section_total = 0
    section_contained = 0
    per_query: list[dict[str, Any]] = []

    for entry in golden:
        ranked = retrieve(index, chunks, entry["query"], top_k)
        top = [chunks[position] for position, _ in ranked]
        expected_scheme = entry.get("expected_scheme")
        expected_section = entry.get("expected_section")

        rank = None
        if expected_scheme:
            scheme_scored += 1
            for position, chunk in enumerate(top, start=1):
                if chunk.scheme_id == expected_scheme:
                    rank = position
                    break
            if rank is not None:
                hits += 1
                reciprocal_ranks.append(1.0 / rank)
            if rank == 1:
                first_hits += 1

        if expected_section:
            section_total += len(top)
            section_contained += sum(
                1 for chunk in top if has_section_heading(chunk.text, expected_section)
            )

        per_query.append(
            {
                "id": entry["id"],
                "query": entry["query"],
                "expected_scheme": expected_scheme,
                "expected_section": expected_section,
                "rank_of_expected_scheme": rank,
                "top_sections": [chunk.section_title for chunk in top],
            }
        )

    total_tokens = sum(chunk.token_count for chunk in chunks)
    return {
        "strategy": strategy,
        "chunk_size": chunk_size or config.CHUNK_SIZE,
        "top_k": top_k,
        "chunk_count": len(chunks),
        "avg_tokens_per_chunk": round(total_tokens / len(chunks), 1) if chunks else 0.0,
        "hit_at_k": round(hits / scheme_scored, 4) if scheme_scored else None,
        "hit_at_1": round(first_hits / scheme_scored, 4) if scheme_scored else None,
        "scheme_scored": scheme_scored,
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else None,
        "section_hit_rate": (
            round(section_contained / section_total, 4) if section_total else None
        ),
        "section_scored": section_total,
        "per_query": per_query,
    }


def print_table(results: list[dict[str, Any]]) -> None:
    header = (
        f"{'strategy':9} {'size':5} {'k':3} {'chunks':7} {'avg_tok':8} "
        f"{'hit@1':7} {'hit@k':7} {'MRR':7} {'section_hit':13}"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        hit = result["hit_at_k"]
        first = result["hit_at_1"]
        mrr = result["mrr"]
        section = result["section_hit_rate"]
        print(
            f"{result['strategy']:9} {result['chunk_size']:<5} {result['top_k']:<3} "
            f"{result['chunk_count']:<7} {result['avg_tokens_per_chunk']:<8} "
            f"{('-' if first is None else f'{first:.3f}'):7} "
            f"{('-' if hit is None else f'{hit:.3f}'):7} "
            f"{('-' if mrr is None else f'{mrr:.3f}'):7} "
            f"{('-' if section is None else f'{section:.3f}'):13}"
        )


SWEEP_SIZES = tuple(config.CHUNK_SIZE_SWEEP)
SWEEP_KS = tuple(config.TOP_K_SWEEP)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare chunking strategies.")
    parser.add_argument("--strategy", default="all", help="all | C1 | C2 | C3 | C4")
    parser.add_argument("--chunk-size", type=int)
    parser.add_argument("--top-k", type=int, default=config.TOP_K)
    parser.add_argument("--sweep", action="store_true", help="run the full size x k grid")
    parser.add_argument("--corpus", choices=["real", "synthetic"], default="synthetic")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    if args.corpus == "real":
        documents = parse_mod.load_corpus()
        label = "REAL reachable corpus (Groww mirrors)"
    else:
        from scripts.synthetic_corpus import build_synthetic_documents

        documents = build_synthetic_documents()
        label = "SYNTHETIC factsheet-shaped corpus (real values, generated structure)"

    if not documents:
        raise SystemExit("no documents; run `python -m scripts.ingest` first")

    total = sum(len(document.text) for document in documents)
    print(f"corpus: {label}")
    print(
        f"documents={len(documents)} chars={total} "
        f"golden_entries={len(load_golden_set())}"
    )
    print(PROVISIONAL_NOTE)
    print()

    strategies = (
        list(chunk_mod.CHUNKERS)
        if args.strategy == "all"
        else [args.strategy.upper()]
    )

    if args.sweep:
        results = [
            evaluate(documents, strategy, top_k, size)
            for strategy in strategies
            for size in SWEEP_SIZES
            for top_k in SWEEP_KS
        ]
    else:
        results = [
            evaluate(documents, strategy, args.top_k, args.chunk_size)
            for strategy in strategies
        ]
    print_table(results)

    payload = {
        "corpus": args.corpus,
        "provisional": True,
        "note": PROVISIONAL_NOTE,
        "sweep": bool(args.sweep),
        "results": results,
    }
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nwrote {args.json_out}")

    best = max(
        (r for r in results if r["mrr"] is not None),
        key=lambda r: (r["mrr"], r["hit_at_1"] or 0.0),
        default=None,
    )
    scorable = results[0]["scheme_scored"] if results else 0
    print(
        f"\nhit@1/hit@k/MRR are computed over the {scorable} golden entries that name a "
        f"single expected scheme. Entries with expected_scheme=null (cross-scheme "
        f"comparisons and the out-of-scope question) are excluded from those metrics and "
        f"scored on section_hit_rate only, so the denominator is never inflated."
    )
    print(
        "section_hit_rate = share of top-k chunks whose text actually contains the "
        "expected section's heading. This is containment, not label equality: a "
        "multi-section chunk is credited when the answer-bearing section is inside it."
    )
    if best:
        print(
            f"\nbest by MRR: {best['strategy']} size={best['chunk_size']} "
            f"k={best['top_k']} mrr={best['mrr']}"
        )


if __name__ == "__main__":
    main()
