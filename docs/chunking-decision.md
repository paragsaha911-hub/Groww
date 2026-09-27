# Chunking Decision — Phase 7

Status: **provisional**. Decided on structural grounds because the available corpus cannot
discriminate between strategies. Re-run required once the official factsheet snapshot exists.

Reproduce with:

```
python -m scripts.ingest
python -m scripts.chunk_experiment --strategy all --corpus real
python -m scripts.chunk_experiment --sweep --corpus synthetic
```

Raw output: `data/eval/chunk_experiment_real.json`,
`data/eval/chunk_experiment_sweep.json`.

## Decision

`CHUNKER = "C3"` (heading-aware), `CHUNK_SIZE = 500`, `CHUNK_OVERLAP = 100`.

| Strategy | Behaviour | Verdict |
| --- | --- | --- |
| C1 fixed window | Character windows, overlap 100 | Rejected — no notion of headings |
| C2 recursive | Splits on `\n## `, `\n\n`, `. `, space | Rejected — separates facts from labels |
| C3 heading-aware | Groups whole sections up to the budget, never across a top-level scheme heading | **Selected** |
| C4 one section per chunk | Every section is its own chunk | Rejected — over-fragments |

## The experiment did not decide this

Both corpora were run. Neither separates C1, C2 and C3, for reasons that are structural
rather than fixable by tuning.

**Real reachable corpus (5 Groww mirrors, 5,128 chars, ~1,283 tokens, 41 sections).** At
`chunk_size=500` C1, C2 and C3 each emit exactly one chunk per document, so retrieval collapses
into whole-document retrieval and `hit@1 = 1.000` for C1 and C2 (C3 scores 0.923). With only
five documents in the corpus, `hit@5` is 1.000 by arithmetic for *any* chunker, which is why
`hit@1` is reported alongside it. The only real signal here is C4's over-fragmentation: 41
chunks averaging 22.9 tokens, with `hit@1` falling to 0.846 and `section_hit_rate` to 0.214.

**Synthetic factsheet-shaped corpus (5 docs, 20,167 chars, 5,044 tokens, 51 sections).** Built
from the verified real values and a realistic section structure, precisely so chunk counts
would vary. They do vary (10–25 chunks per strategy) but the scheme-level metrics still
saturate: every golden query names its scheme explicitly ("HDFC Large Cap Fund"), so scheme
disambiguation is trivial. Across all 36 sweep rows the best MRR is 1.000 for C1, C2 **and** C3,
and 0.894 for C4. Only `section_hit_rate` moves, and it moves for a reason that says nothing
about strategy quality — a larger chunk mechanically contains more section headings.

Reporting `best by MRR: C1` as though it were a finding would be misleading. The sweep produced
ties at the ceiling, and a ceiling is not evidence. The one consistent signal across both corpora
is that C4 is worse, and it is worse for a structural reason rather than a scoring one.

Retrieval used a deterministic TF-IDF lexical retriever rather than
`all-MiniLM-L6-v2`, because Phase 8 is not implemented. A lexical retriever rewards exact term
overlap, which structurally favours heading-preserving chunking less than a dense retriever
would; it cannot stand in for the real thing. Absolute numbers will move once embeddings
exist.

## Why C3 anyway

The deciding argument is a hard requirement, not a score. The official consolidated factsheet
is a **single PDF covering all five schemes**, so the pipeline must be able to split one
document into per-scheme chunks **without ever merging two schemes into one chunk**. Only C3
can express that constraint, and it is enforced and tested
(`test_c3_never_merges_across_a_top_level_scheme_heading`).

The rest follows from the citation contract:

- **C1** slices at arbitrary character offsets, cutting through section headings and through
  table rows. Boundary-level table protection only helps when a boundary happens to land
  inside a detected table; it cannot protect a heading. A citation would then point at a
  chunk whose `section_title` is unrelated to its content.
- **C2** splits on punctuation and whitespace. In a factsheet that routinely separates a
  label from its value — `Expense ratio` heading in one chunk, `1.03%` in the next. That is a
  direct hazard for fact extraction, not a cosmetic issue.
- **C4** keeps headings and tables perfectly intact, which is why it posts the best
  `section_hit_rate` in the mid-size rows of the synthetic sweep. But at one section per chunk
  it produced 41 chunks averaging 22.9 tokens on real data, and it is the only strategy that
  lost `hit@1` on both corpora (0.846 real, 0.692 synthetic). Fragmenting every heading into
  its own chunk discards the surrounding context a generator needs to answer "what is the exit
  load" without also seeing which scheme and plan it applies to.
- **C3** keeps each fact attached to its heading, preserves tables, respects the
  cross-scheme boundary, and degrades gracefully: a section larger than the budget is
  windowed with overlap rather than dropped.

## Caveats

- **Provisional until re-run on the official snapshot.** The consolidated PDF is the only
  document that actually exercises the cross-scheme boundary. The experiment has never seen
  it. If C3's cross-scheme handling is wrong, the sweep on the real PDF will show it.
- **C3 assumes heading structure.** On a document with no level-1 heading, C3 treats the whole
  document as a single root and never splits by scheme. That is correct for a per-scheme
  mirror page and wrong for a multi-scheme PDF with no scheme headings. The PDF parser must
  emit a level-1 heading per scheme, or C3 cannot enforce the boundary.
- **Overlap is applied only within oversized sections.** Section-aligned chunks do not
  overlap each other, so `CHUNK_OVERLAP = 100` has no effect on normal chunks. This is
  deliberate: overlapping section-aligned chunks would duplicate content in the vector store
  and break the one-chunk-per-region model the citation offsets rely on.
- **Token counts are approximate** (`chars / 4`), so `token_count` is a diagnostic, not a
  billing figure. A real tokenizer may be needed before the budget is trusted for cost.

## What would change this decision

1. Official factsheet snapshot ingested, sweep re-run, C3's cross-scheme boundary verified
   against a real multi-scheme PDF.
2. Phase 8 dense embeddings available, replacing the lexical proxy — the ordering may change,
   particularly for C2, which a dense retriever may punish less than TF-IDF does.
3. Real user query logs, which would show whether queries name the scheme explicitly. If they
   do not, scheme-level retrieval becomes genuinely hard and the section-alignment advantage
   of C3 matters much more than this experiment suggests.
