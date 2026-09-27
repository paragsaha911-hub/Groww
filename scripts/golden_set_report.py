from __future__ import annotations

import json
from pathlib import Path

from app import config
from app.retrieve.retriever import HybridRetriever


def main() -> int:
    path = config.EVAL_DIR / "golden_set.json"
    if not path.exists():
        print(f"missing {path}")
        return 1
    golden = json.loads(path.read_text(encoding="utf-8"))
    retriever = HybridRetriever()
    misses = 0
    for entry in golden:
        result = retriever.retrieve(entry["query"])
        top = result.chunks[0] if result.chunks else None
        scheme = top.scheme_id if top else "-"
        section = top.section_title if top else "-"
        expected = entry.get("expected_scheme")
        if not result.passed_floor:
            ok = "FLOOR" if expected is None else "MISS"
        else:
            ok = "HIT" if (expected is None or scheme == expected) else "MISS"
        if ok == "MISS":
            misses += 1
        print(
            f"{entry['id']:4} {ok:5} filter={result.scheme_filter or '-':3} "
            f"top={scheme:3} {section} | {entry['query'][:60]}"
        )
    print(f"\n{len(golden) - misses}/{len(golden)} resolved")
    return 0 if misses == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
