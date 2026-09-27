import json
from pathlib import Path
from app.retrieve.retriever import HybridRetriever
golden = json.loads(Path('data/eval/golden_set.json').read_text(encoding='utf-8'))
r = HybridRetriever()
for g in golden:
    res = r.retrieve(g['query'])
    top = res.chunks[0] if res.chunks else None
    scheme = top.chunk.scheme_id if top else '-'
    section = top.chunk.section_title if top else '-'
    ok = 'HIT' if (g.get('expected_scheme') is None or scheme == g['expected_scheme']) and res.passed_floor else 'MISS'
    if not res.passed_floor:
        ok = 'FLOOR' if g.get('expected_scheme') is None else 'MISS'
    print(f\"{g['id']:4} {ok:5} filter={res.scheme_filter or '-':3} top={scheme:3} {section} | {g['query'][:60]}\")