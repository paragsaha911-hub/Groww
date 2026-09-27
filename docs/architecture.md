# Architecture — HDFC Mutual Fund Facts-Only RAG Chatbot

| Field | Value |
| --- | --- |
| Document type | System Architecture (companion to `docs/PRD.md`) |
| Status | Draft v1.0 |
| Audience | Build team + demo evaluator |
| Upstream | `docs/PRD.md` — defines *what* and *why*; this document defines *how* |
| Stack | Python 3.10+, `all-MiniLM-L6-v2`, ChromaDB, Anthropic `claude-sonnet-5`, Streamlit |

---

## 1. How to read this document

The PRD is a requirements contract. This document is the implementation blueprint. If you
are building, read §4–§8. If you are evaluating the demo, read §3 (context), §9 (trust
boundaries) and §12 (demo walkthrough).

| Section | Contents |
| --- | --- |
| §2 | Architecture drivers — the constraints that forced each decision |
| §3 | System context |
| §4 | The two pipelines (the central design idea) |
| §5 | Ingestion pipeline, stage by stage |
| §6 | Query pipeline, stage by stage |
| §7 | Module map and public interfaces |
| §8 | Data schemas |
| §9 | Trust boundaries and privacy model |
| §10 | Design decisions (ADR summary) |
| §11 | Failure modes and degradation matrix |
| §12 | Observability, demo walkthrough, traceability |

---

## 2. Architecture drivers

Seven constraints from the PRD determine nearly every structural choice. Each is traceable.

| # | Driver | PRD ref | Architectural consequence |
| --- | --- | --- | --- |
| AD1 | Every RAG stage must be visible and reproducible; none may be skipped in the demo | G6 | Batch ingestion and query are **separate, separately runnable** pipelines with persisted artefacts between them — not one function |
| AD2 | Numbers must be exactly right; a plausible wrong number is worse than no answer | G4, R1, R2 | A build-time **field-regex extraction** pass (`fields.json`) acts as a correctness gate independent of the LLM; a similarity floor forces `not_found` rather than guessing |
| AD3 | Official HDFC AMC documents are the source of truth; mirrors are fallback | §4.2, Q2 | Every source carries an `authority` flag; citation resolution and conflict handling depend on it |
| AD4 | No PII accepted, none stored, none sent to the model | G5, R4 | PII screening runs **before** retrieval and before any outbound call; persistence is hash-only on that path |
| AD5 | Never give advice or state performance | G3, G4 | Intent classification is a deterministic-first **gate**, not a prompt instruction; refusal paths return before the LLM is ever called |
| AD6 | The demo must not fail live | R7, NFR-3 | Answer generation sits behind an `Answerer` interface with an offline `ExtractiveAnswerer`; the model and corpus are cached locally |
| AD7 | Chunking strategy is to be chosen by measurement, not assumption | §6.3 | The chunker is swappable behind a `Chunker` protocol, and an experiment harness runs the whole pipeline per candidate |

---

## 3. System context

```
   ┌──────────────────────────────────────────────────────────────────────────┐
   │                          USER  (browser or terminal)                     │
   │        "What is the expense ratio of HDFC Large Cap Fund?"              │
   └───────────────────────────────┬──────────────────────────────────────────┘
                                   │ natural-language question
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │   PRESENTATION                                                            │
   │   app/ui.py  (Streamlit, primary demo surface)                            │
   │   app/cli.py (rich, offline fallback + debug view)                        │
   │   shows: ≤3 sentences · one source link · freshness · disclaimer         │
   └───────────────────────────────┬──────────────────────────────────────────┘
                                   │ QueryResult
   ┌───────────────────────────────▼──────────────────────────────────────────┐
   │   APPLICATION  (app/)                                                    │
   │                                                                          │
   │   guardrails/  ──►  retrieve/  ──►  generate/                             │
   │   PII · intent      top-k + RRF     Claude | extractive                  │
   │   injection guard                                                │        │
   └───────────────────────────────┬───────────────────────────┬──────────────┘
                                   │                           │
                    ┌──────────────▼──────────┐      ┌─────────▼──────────────────┐
                    │  data/chroma            │      │  Anthropic Claude API      │
                    │  ChromaDB (local, HNSW) │      │  claude-sonnet-5           │
                    │  + all-MiniLM-L6-v2     │      │  outbound, prompt only     │
                    └─────────────────────────┘      └────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────────────────┐
   │   EXTERNAL KNOWLEDGE SOURCES  (fetched offline by the ingestion pipeline)│
   │   hdfcfund.com (consolidated factsheet, KIM/SID, fee pages) · amfiindia.com ·        │
   │   sebi.gov.in · incometax.gov.in · groww.in  [mirror, fallback only]    │
   └──────────────────────────────────────────────────────────────────────────┘
```

Note the asymmetry that defines the system: **external sources are touched only during
offline ingestion, never at query time.** The query path reads `data/` and calls exactly
one external service (the Claude API).

---

## 4. The two pipelines

This is the central architectural idea. The PRD mandates that every RAG stage be
demonstrable, so the system is split into a **batch path** that builds knowledge and an
**online path** that answers questions. They communicate only through `data/`.

```
  OFFLINE / BATCH   ──  make ingest   ──  runs rarely, no user, network allowed
  ─────────────────────────────────────────────────────────────────────────────
   [1] Loading        fetch · robots · cache · HTML+PDF parse · fields.json
   [2] Chunking       strategy C1..C4, selected by experiment
   [3] Embedding      all-MiniLM-L6-v2, 384-d, L2-normalised, cached
   [4] Vector Store   ChromaDB persistent, deterministic chunk_id upsert
        │
        │  artefacts (the only interface between the two paths)
        ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ data/raw/  ·  data/processed/  ·  data/embedding_cache/          │
  │ data/models/  ·  data/chroma/  ·  data/sources.csv              │
  └──────────────────────────────────────────────────────────────────┘
        │
  ONLINE / REQUEST  ──  make demo / streamlit run  ──  per question
  ───────────────────────────────────────────────────────────────────
   [5] Retrieval     embed query · optional pre-filter · RRF hybrid
                     · optional rerank · similarity floor
   [6] Guardrails    PII scan · intent classify · injection delimiters
   [7] Generation    grounded ≤3 sentences · citation · freshness
   [8] Presentation  answer + one link + disclaimer
```

**Why this split matters**

| Benefit | Consequence |
| --- | --- |
| Each stage is independently demonstrable and testable (AD1) | Chunking quality can be re-measured without re-fetching anything |
| Query path is fast and network-free except the LLM call | Meets NFR-5 latency; ingest cost is amortised |
| Ingestion is idempotent and auditable | `content_hash` per source; re-runs are no-ops (NFR-6) |
| Corpus is a reviewable artefact | A human can read `data/processed/*.md` and check facts before indexing (AD2) |
| The demo degrades gracefully | With no network, only stage 7 swaps implementation (AD6) |

**Shared state is only ever `data/`.** No in-memory coupling between pipelines, so
`make ingest` and `make demo` are independent processes that can be run days apart.

---

## 5. Ingestion pipeline (offline)

Entry point: `scripts/ingest.py`. Each stage prints a count and writes a file, so the
console output *is* the stage-by-stage demo evidence for AD1.

### Stage 1 — Loading (`app/ingest/fetch.py`, `app/ingest/parse.py`)

```
  config.SOURCES (declared: url, scheme_id, source_type, authority, expected_facts)
        │
        ▼
  ┌───────────────┐  host not in ALLOWED_HOSTS ──────────────────► reject + log   (FR-22)
  │ host allowlist│
  └───────┬───────┘
          ▼
  ┌───────────────┐  disallowed ────────────────────────────────► skip + log
  │ robots.txt    │
  └───────┬───────┘
          ▼
  ┌───────────────┐  ≤1 req/s · 30 s timeout · 3 retries · honour Retry-After
  │ httpx fetch   │
  └───────┬───────┘
          ▼
  ┌───────────────┐  content_hash already cached ───────────────► reuse (no-op)
  │ data/raw/     │  .html or .pdf + .meta.json
  └───────┬───────┘
          ▼
   ┌──────────────┴──────────────┐
   │                             │
   ▼                             ▼
┌──────────────┐          ┌──────────────┐
│ HTML parse   │          │ PDF parse    │
│ bs4 + lxml   │          │ pypdf        │
│ strip script/│          │ page-by-page │
│ style/nav/   │          │ + FIELD      │
│ footer/      │          │ REGEX PASS   │──► fields.json   ◄── AD2 correctness gate
│ cookie bars  │          │ (expense     │      expense_ratio, exit_load,
│ keep h1–h4   │          │  ratio,      │      benchmark, riskometer,
│ tables →     │          │  exit load,  │      min_sip, lock_in, nav, aum
│ pipe-delimited│         │  benchmark,  │
└──────┬───────┘          │  riskometer, │
       │                  │  min SIP,    │
       │                  │  lock-in)    │
       │                  └──────┬───────┘
       │                         │
       └────────────┬────────────┘
                    ▼
        data/processed/{source_id}.md  +  heading_outline.json  +  fields.json
                    │
                    ▼
        completeness + authority flags  ── is_complete=false ⇒ excluded from eval
```

**Extraction ladder** (order is architectural, not incidental):

1. Official PDF (factsheet → KIM/SID) — `extraction_method="pdf"`, `authority="official"`
2. Official HTML on `hdfcfund.com` / `amfiindia.com` — `"static"`, `"official"`
3. Groww mirror — `"mirror"`, `authority="mirror"`
4. Manual snapshot — `"manual"`, requires reviewer note

Official before mirror because the PDF path is the authority (AD3), and because a
client-side-rendered mirror yields no numbers anyway (R1b). The mirror exists to keep the
demo alive, not to be trusted.

### Stage 2 — Chunking (`app/ingest/chunk.py`)

```
  data/processed/*.md
        │
        ├── strategy C1  fixed window 500/100 ──────────┐
        ├── strategy C2  recursive char 500/100 ────────┤   all four run through
        ├── strategy C3  heading-aware (anticipated) ──┤   the SAME retrieval config
        └── strategy C4  overlap-free whole-section ───┘   against a FROZEN golden set
                                    │
                                    ▼
                    hit@k · MRR · section precision · faithfulness
                                    │
                                    ▼
                  docs/chunking-decision.md  (deliverable D6)
                                    │
                                    ▼
        selected strategy ──► chunks + metadata contract (§8)
```

Swappable behind the `Chunker` protocol (AD7). Each chunk carries `heading_path` and
`section_title` so retrieval can filter on them and the citation can name a section.

### Stage 3 — Embedding (`app/index/embed.py`)

```
  chunks ──► length-sorted batches of 32
              │
              ▼
      sentence-transformers/all-MiniLM-L6-v2
              │  384-d, L2-normalised  (inner product == cosine)
              │  NO "query:"/"passage:" prefix — symmetric model
              ▼
      data/embedding_cache/  keyed (corpus_version, chunk_hash, model_id)
              │  cache hit ⇒ skip re-encoding
              ▼
      model_id + dimension recorded  ──► asserted at query time (R8)
```

### Stage 4 — Vector Store (`app/index/store.py`)

```
  chunks + vectors ──► chromadb.PersistentClient("data/chroma")
                          │
                          ▼
                    collection "hdfc_schemes"
                      id       = chunk_id          (deterministic ⇒ upsert, not duplicate)
                      distance = cosine
                      metadata = full §6.3 contract (filterable)
                      HNSW     = M 16, construction_ef 128
                          │
                          ▼
                    collection metadata: corpus_version, model_id, dim
                          │ mismatch at query time ⇒ re-index warning
                          ▼
                    data/chroma/
```

---

## 6. Query pipeline (online)

Entry point: `scripts/query.py`, `app/cli.py`, or `app/ui.py`. All three call the same
`answer_question()` entry point, so the UI is a thin shell over identical logic.

```
  user query
      │
      ▼
  ╔═════════════════ STAGE 6a — PII SCREEN (runs FIRST) ═════════════════╗
  ║ pii.scan(query)                                                        ║
  ║   PAN · Aadhaar · account no · IFSC · card (Luhn) · OTP · email · phone ║
  ║   hit ──► refuse; persist ONLY {query_sha256, detector, redacted}      ║
  ║           raw text never logged, never sent to the model    (AD4)     ║
  ╚═══════╤═══════════════════════════════════════╤═══════════════════════╝
          │ clean                                  │ PII
          ▼                                       └──► return refusal, END
  ╔═════════════════ STAGE 6b — INTENT GATE ═══════════════════════════╗
  ║ deterministic regex/keyword rules FIRST, LLM classifier for residual ║
  ║ order: npi → advice → performance → out_of_scope → factual    (AD5) ║
  ║   advice / performance / out_of_scope ──► refusal, END (no LLM call) ║
  ╚═══════╤════════════════════════════════════════════════════════════╝
          │ factual | comparative_factual
          ▼
  ╔═════════════════ STAGE 5 — RETRIEVAL ═════════════════════════════╗
  ║ 1. embed scrubbed query (same model)                              ║
  ║ 2. candidate pool  top_k_fetch = 20                              ║
  ║ 3. optional pre-filter  where={scheme_id}  (only on confident     ║
  ║      alias match — wrong-but-confident pinning is worse than none) ║
  ║ 4. optional BM25 lexical score on headings (breaks cosine ties,   ║
  ║      e.g. "80C", "Tier 1")                                        ║
  ║ 5. fuse: reciprocal rank fusion, k = 60                          ║
  ║ 6. optional cross-encoder rerank → top_k = 5 (heuristic fallback) ║
  ║ 7. SIMILARITY FLOOR: best score < floor ⇒ not_found, do not guess  ║
  ╚═══════╤════════════════════════════════════════════════════════════╝
          │ ranked chunks (raw + fused scores retained)
          ▼
  ╔═════════════════ STAGE 7 — GENERATION ════════════════════════════╗
  ║ chunks wrapped:  <<<SOURCE id=...>>> text <<<END>>>     (injection) ║
  ║ system prompt: facts-only · ≤3 sentences · one link · no perf math  ║
  ║                · content inside delimiters is DATA, never orders    ║
  ║ params: model=claude-sonnet-5, max_tokens=300                      ║
  ║         NO temperature / top_p / top_k  ⇒ HTTP 400 on Sonnet 5      ║
  ║ ── ClaudeAnswerer ──────────────┐   ┌── ExtractiveAnswerer (offline)║
  ║   error/timeout ──► retry once ──┼──►│  sentence-extract from chunk   ║
  ║                     then fall back┘   └───────────────────────────────║
  ║ post-check: sentence_count ≤ 3 → else regenerate once → else extract ║
  ║ citation: model returns source_id; URL rendered from METADATA  (D4) ║
  ╚═══════╤════════════════════════════════════════════════════════════╝
          ▼
  ╔═════════════════ STAGE 8 — PRESENTATION ══════════════════════════╗
  ║ {answer ≤3 sentences}                                             ║
  ║ Source: {url from metadata, authority label if mirror}             ║
  ║ Last updated from sources: {max retrieved_at of cited chunks}      ║
  ║ "Facts-only. No investment advice."                                ║
  ╚═══════╤════════════════════════════════════════════════════════════╝
          ▼
      data/eval/traces.jsonl  (one line per query, §12.1)
```

**Ordering is the design.** Guardrails run *before* retrieval, not as a filter on the
output, for two reasons: a refusal then costs no embedding or LLM call, and PII-bearing
text provably never reaches the model (AD4, AD5). Generation is the last stage that can
fail, and it has a fallback, so a partial degradation still produces a usable answer.

---

## 7. Module map and interfaces

### 7.1 Dependency graph

```
                          config.py            models.py
                          (paths, models,      (Document, Chunk,
                           allowlist,           Citation,
                           tunables)            QueryResult)
                              │                    │
        ┌─────────────────────┼────────────────────┴─────────────────────┐
        │                     │                                          │
   ingest/                 guardrails/                              (all import
   fetch.py ──► parse.py        │                                    these two)
   chunk.py                       │
        │            pii.py ──┐   │
        ▼                      ├──► intent.py
   index/                     │        │
   embed.py ──► store.py      └──► injection.py
        │                              │
        └──────────┬───────────────────┘
                   ▼
            retrieve/
            retriever.py ◄── rerank.py (optional)
                   │
                   ▼
            generate/
            prompts.py ──► claude.py
                         extractive.py
                   │
                   ▼
            cli.py / ui.py
```

`ingest/` never imports `retrieve/` or `generate/`. `generate/` never imports `ingest/`.
The only shared vocabulary is `models.py`. This is what makes the two pipelines in §4
genuinely independent.

### 7.2 Public interfaces

These are the seams. Everything else is an implementation detail we are free to change.

```python
class Chunker(Protocol):
    def split(self, doc: Document) -> list[Chunk]: ...


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
    def query(
        self, vector: list[float], top_k: int, where: dict | None
    ) -> list[ScoredChunk]: ...


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int) -> RetrievalResult: ...


class Answerer(Protocol):
    def generate(self, system: str, user: str) -> str: ...
```

Implementations:

| Protocol | Implementations | Selected by |
| --- | --- | --- |
| `Chunker` | `FixedWindow` (C1), `RecursiveChar` (C2), `HeadingAware` (C3), `SectionChunk` (C4) | `CHUNKER` config, set from the experiment |
| `Embedder` | `MiniLMEmbedder` | `EMBED_MODEL` config |
| `VectorStore` | `ChromaStore` | fixed for this project |
| `Retriever` | `HybridRetriever` (RRF + optional rerank) | fixed |
| `Answerer` | `ClaudeAnswerer` (default), `ExtractiveAnswerer` (`--offline` / fallback) | `ANTHROPIC_API_KEY` present and `offline` flag |

### 7.3 Entry points

| Command | Path | Purpose |
| --- | --- | --- |
| `make ingest` | `scripts/ingest.py` | Stages 1–4; `--rebuild` for a clean index |
| `make chunk-exp` | `scripts/chunk_experiment.py` | Stage 2 decision experiment → `docs/chunking-decision.md` |
| `make query` | `scripts/query.py` | One question from the terminal |
| `make demo` | `app/cli.py` | Interactive demo surface |
| `make ui` | `app/ui.py` | Streamlit surface |
| `make eval` | `scripts/eval.py` | All §9.2 PRD metrics + gate |
| `make coverage` | `scripts/coverage_report.py` | Per-scheme field gaps (FR-16, FR-21) |
| `make sources` | `scripts/export_sources.py` | `docs/sources.md`, `data/sources.csv` (D2) |
| `make sample-qa` | `scripts/export_sample_qa.py` | `docs/sample_qa.md` (D4) |
| `make test` | `pytest` | Unit suite, no network, no API key |

---

## 8. Data schemas

### 8.1 `Document` — one per source, produced by Stage 1

| Field | Type | Notes |
| --- | --- | --- |
| `source_id` | str | Stable, human-readable, e.g. `s1_factsheet_2026-08` |
| `scheme_id` | str | `S1`–`S5` |
| `url` | str | Original URL |
| `title` | str | Document title |
| `source_type` | str | `factsheet` \| `kim` \| `sid` \| `fee_page` \| `risk_note` \| `guide` \| `scheme_page` |
| `authority` | str | `official` \| `mirror` (AD3) |
| `extraction_method` | str | `pdf` \| `static` \| `mirror` \| `manual` |
| `document_date` | date \| None | The document's own `as of` date, when stated |
| `retrieved_at` | datetime | When we fetched it — drives the freshness stamp |
| `content_hash` | str | SHA-256 of the raw bytes; the idempotency key |
| `fields` | dict | Regex-extracted key/value facts (AD2) |
| `is_complete` | bool | `false` ⇒ excluded from the evaluation set |

### 8.2 `Chunk` — the unit of retrieval, produced by Stage 2

| Field | Type | Used by |
| --- | --- | --- |
| `chunk_id` | str | Chroma primary key; deterministic ⇒ idempotent upsert |
| `source_id` | str | Citation resolution |
| `scheme_id` | str | Pre-filter + `expected_scheme` scoring |
| `scheme_name` | str | Display |
| `category` | str | Large Cap / Flexi Cap / ELSS / Small Cap / Balanced Advantage |
| `section_title` | str | Citation label, lexical tie-break |
| `heading_path` | str | `>`-joined heading trail; lexical tie-break |
| `page` | int \| None | Factsheet page locator, so a citation can point at page N |
| `ordinal` | int | Document order |
| `token_count` | int | Chunking diagnostics |
| `char_start` / `char_end` | int | Traceability back to source text |
| `url` | str | Citation URL, **from metadata not model output** |
| `retrieved_at` | datetime | Freshness stamp |
| `document_date` | date \| None | As-of date of the underlying factsheet; lets a citation state the period the number belongs to, and lets retrieval filter by as-of date |
| `authority` | str | Drives the secondary-source label |
| `corpus_version` | str | Provenance; mismatch triggers re-index |

### 8.3 `RetrievalResult` — Stage 5 output

`query`, `intent`, `candidates: list[ScoredChunk]` where each `ScoredChunk` carries
`rank`, `chunk_id`, `fused_score`, `cosine_score`, `lexical_score`, `rerank_score`;
plus `best_score`, `floor`, `passed_floor: bool`.

### 8.4 `QueryResult` — what the UI renders

`answer`, `sentences: list[str]`, `citations: list[Citation]`, `freshness_date`,
`refused: bool`, `refusal_kind`, `authority`, `generator`, `latency_ms`, `trace_id`.

`Citation` = `{source_id, url, section_title, page, authority}`.

### 8.5 Trace — one JSONL line per query

Defined in PRD §15.2. The fields that matter architecturally: `retrieved` (with scores,
so retrieval can be judged without generation), `generator` (proves which answerer served
the answer), `authority` (proves a mirror did not silently become the source), and
`query_sha256` + `pii_detected` (proves no raw PII was persisted).

---

## 9. Trust boundaries and privacy model

Three zones. Most architecture-doc value is in stating which side of each line data sits
on, and what is forbidden from crossing.

```
╔═ ZONE A — UNTRUSTED INPUT ═══════════════════════════════════════════════════╗
║                                                                              ║
║   (a) user query text              adversarial, arbitrary, may carry PII      ║
║   (b) fetched HTML / PDF content   third-party, may change without notice,    ║
║                                    may contain text crafted to steer the LLM   ║
║                                                                              ║
║   Never executed. Never treated as instructions. Never echoed to a user       ║
║   verbatim. Parsed only; scripts/styles stripped before any text is stored.    ║
╚═══════════════════════════════════════╤══════════════════════════════════════╝
                                        │
              ┌─────────────────────────┴─────────────────────────┐
              │ (a) pii.scan + scrub                               │ (b) parse + field-regex
              │     intent.classify (deterministic first)         │     strip scripts
              ▼                                                   ▼
╔═ ZONE B — SANITISED ═════════════════════════════════════════════════════════╗
║                                                                              ║
║   scrubbed query   ·   retrieved chunks (DATA, never instructions)             ║
║                                                                              ║
║   The ONLY two things permitted to reach the model.                           ║
╚═══════════════════════════════════════╤══════════════════════════════════════╝
                                        │
                                        ▼
╔═ ZONE C — OUTBOUND API CALL ══════════════════════════════════════════════════╗
║                                                                              ║
║   Anthropic Claude API receives: system prompt + scrubbed query + chunks       ║
║                                                                              ║
║   MUST NOT receive: PII-bearing raw query · API keys · user identity          ║
║   MUST NOT return:  a URL (the app resolves URLs from metadata instead)       ║
╚═══════════════════════════════════════╤══════════════════════════════════════╝
                                        │
╔═ ZONE D — SECRET (never leaves the process) ═════════════════════════════════╗
║   ANTHROPIC_API_KEY — environment only · never logged · never in traces      ║
║   never written to data/, docs/, or any trace record                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### 9.1 Invariants

| # | Invariant | Enforced by | Test |
| --- | --- | --- | --- |
| I1 | Raw PII never reaches disk | `pii.scan` returns before any write; only a hash is persisted | `test_pii.py` |
| I2 | Raw PII never reaches the model | screen precedes retrieval and generation | `test_pii.py` |
| I3 | Fetched content is never executed | HTML sanitised; PDF is inert; no `eval`, no rendering of fetched HTML | `test_parsing.py` |
| I4 | Fetched content is never obeyed as instructions | delimiter isolation + data-not-instructions system prompt | `test_injection.py` |
| I5 | A citation URL always exists in the ingested source list | URL resolved from `Chunk.url`, never from model text | `test_exporters.py` |
| I6 | The API key never appears in an artefact | env-only; pre-commit secret scan | `test_pii.py` + pre-commit |
| I7 | An incomplete source cannot silently shrink the corpus | `is_complete` gate excludes it from eval and is reported | `coverage_report.py` |
| I8 | Retrieval can be judged without generation | raw + fused scores retained in the trace | `eval.py` |

I5 deserves emphasis: it is the reason the model returns a `source_id` rather than a
link. A language model asked for a URL will eventually produce a plausible-looking one
that 404s or, worse, points somewhere real but wrong. Resolving the URL from chunk
metadata makes a fabricated citation structurally impossible.

---

## 10. Design decisions

| ID | Decision | Rationale | Consequence accepted | Rejected alternative |
| --- | --- | --- | --- | --- |
| D1 | Split batch ingestion from online query, communicating only via `data/` | AD1: every stage must be demonstrable | Two processes instead of one; ingestion must be run before querying | Single end-to-end function; faster to write, impossible to demo or test per stage |
| D2 | Deterministic `chunk_id` + upsert | NFR-6 idempotency | IDs must encode source + ordinal and stay stable across strategy changes | Random UUIDs; re-ingest duplicates the corpus silently |
| D3 | Rich metadata on every chunk, enabling pre-filter and hybrid fusion | Scheme-filtered questions dominate the golden set | Metadata schema must be maintained; a stale field degrades filtering | Pure vector search; a "HDFC ELSS" query can retrieve Large Cap chunks |
| D4 | Model returns `source_id`; app renders the URL from metadata | I5; kills fabricated citations | Slightly more plumbing; a chunk with no URL cannot be cited | Asking the model for the link; simple, and wrong under hallucination |
| D5 | Guardrails gate *before* retrieval | AD4/AD5: refuse cheaply and provably | Intent rules must be maintained as new phrasings appear | Post-hoc output filtering; PII would already have left the process |
| D6 | Hybrid retrieval with RRF (`k=60`) + optional cross-encoder | Exact tokens like "80C" and "Tier 1" are weak under cosine alone | More moving parts; reranker is optional to keep the demo dependency-free | Cosine-only; simpler, measurably worse on exact-token questions |
| D7 | `Answerer` protocol with an extractive fallback | AD6; the demo must not fail live | Two implementations to maintain | Claude-only; a network blip ends the demo |
| D8 | Similarity floor ⇒ `not_found` rather than a best-effort answer | AD2: silence beats a wrong number | Some answerable questions get refused; tune the floor on the golden set | Always answer from top-k; confident and occasionally wrong |
| D9 | Build-time `fields.json` regex pass as a correctness gate | AD2; independent of the LLM | Regex maintenance per factsheet layout; a new layout needs new patterns | Trust the LLM to read the PDF; no independent check on the numbers |
| D10 | `corpus_version` + `model_id` + dimension recorded and asserted | R8; silent index/model mismatch destroys retrieval quality quietly | One extra assert and a re-index path | Trusting the index; produces nonsense rankings with no error |
| D11 | Send no sampling parameters to Claude | `claude-sonnet-5` returns HTTP 400 for non-default `temperature`/`top_p`/`top_k` | No temperature knob for determinism; rely on frozen corpus + fixed `top_k` | `temperature=0`; the obvious choice, and a 400 on every call |
| D12 | `authority` flag on every source and citation | AD3; mirrors must never be silently authoritative | Extra field and a UI label | One undifferentiated source list |

---

## 11. Failure modes and degradation matrix

Design intent: **degrade, never lie, never crash.**

| Failure | Detected by | Behaviour | User sees |
| --- | --- | --- | --- |
| Official PDF 403 / robots-disallowed | `fetch.py` | Skip to next ladder rung, log reason | Answer from the next source, or `not_found` |
| Official PDF unreachable entirely | ladder exhausted | `is_complete=false` on that source | Coverage report lists the gap (never a silent gap) |
| Mirror page is JS-only | completeness check | `is_complete=false`; excluded from eval | Gap surfaced in coverage report |
| PDF table columns scrambled | `fields.json` vs golden set | **Build-time block** (R1) | n/a — never ships |
| Official and mirror disagree | `coverage_report.py` | Official wins; conflict logged | Answer cites the official URL |
| `data/chroma` missing or empty | `ChromaStore` | Clear error telling the user to run `make ingest` | n/a |
| Embedding model or dim mismatch | collection metadata assert | Warn loudly, offer re-index | n/a |
| Query contains PAN/Aadhaar/OTP/email | `pii.scan` | Refuse; persist hash only | "I can't accept personal identifiers…" |
| Advice question | intent rules | Refuse before any LLM call | Facts-only message + educational link |
| Performance/returns question | intent rules | Refuse to state numbers | Factsheet link |
| Injected instruction inside a chunk | (prevented) | Delimiters + data-not-instructions prompt | Normal factual answer; test asserts no compliance |
| Best retrieval score below floor | `retriever` | `not_found` path | "I couldn't find that in my sources" + nearest sections |
| Claude API error, timeout, rate limit | `claude.py` | Retry once with backoff → `ExtractiveAnswerer` | Answer still served (slightly rougher wording) |
| Claude returns >3 sentences | post-check | Regenerate once → else extractive | Answer still within contract |
| No network at all | `offline` flag or exception | `ExtractiveAnswerer`; local model + corpus | Answer from the retrieved chunk |
| Missing `ANTHROPIC_API_KEY` | config load | Auto-select `ExtractiveAnswerer`, print a notice | Demo still runs |

---

## 12. Observability, demo, traceability

### 12.1 What each trace field lets you debug

| Symptom | Look at |
| --- | --- |
| Answer is wrong, retrieval was fine | `answer` + `citations` vs source text; prompt or grounding bug |
| Answer is wrong, retrieval was wrong | `retrieved[].cosine_score` / `fused_score` / `section` — chunking or embedding bug |
| Right scheme, wrong field | `retrieved[].section` — chunk boundary problem, revisit Stage 2 |
| Wording varies run to run | `generator` + `corpus_version` — corpus changed between runs |
| Answer cites Groww unexpectedly | `authority` on the citation — an official source was missing (R1c/Q8) |
| A refusal happened unexpectedly | `intent` — intent rules over-triggered |
| Something leaked into a log | `pii_detected` + `query_sha256` — detector gap |

`?debug=1` (Streamlit) or `--debug` (CLI) prints the ranked chunks with scores, so the
retrieval half of the system is inspectable during the demo without a debugger.

### 12.2 Three-minute demo walkthrough

1. `make ingest --rebuild` — show stage counts 1→4 (AD1 evidence).
2. Ask: *"What is the expense ratio of HDFC Large Cap Fund?"* → answer, one source link,
   freshness stamp.
3. Ask: *"What is the lock-in period for HDFC ELSS?"* → statutory answer, official cite.
4. Ask: *"Should I buy HDFC Small Cap?"* → refusal + educational link (AD5).
5. Ask with a fake PAN → PII refusal, no log entry (AD4).
6. `?debug=1` → show ranked chunks and scores (retrieval is inspectable).
7. `make eval` → the metric table, including the zeros that must stay zero.

Backup: a pre-recorded run, since the brief allows a ≤3-min video (R7, R12).

### 12.3 Traceability — PRD requirement to module

| PRD ref | Module(s) | Test |
| --- | --- | --- |
| FR-1, FR-2, FR-22 | `ingest/fetch.py`, `ingest/parse.py` | `test_fetch.py`, `test_parsing.py` |
| FR-2b (conflict) | `scripts/coverage_report.py` | `test_exporters.py` |
| FR-3, FR-4 | `ingest/chunk.py`, `scripts/chunk_experiment.py` | `test_chunker.py` |
| FR-5, FR-6 | `index/embed.py`, `index/store.py` | `test_embed.py`, `test_store.py` |
| FR-7 | `retrieve/retriever.py`, `retrieve/rerank.py` | `test_retriever.py` |
| FR-8, FR-9, FR-10 | `generate/claude.py`, `generate/prompts.py` | `test_claude.py` (LLM-marked), `test_extractive.py` |
| FR-11, FR-12 | `guardrails/intent.py` | `test_intent.py` |
| FR-13 | `guardrails/pii.py` | `test_pii.py` |
| FR-14 | `guardrails/injection.py` | `test_injection.py` |
| FR-15 | `app/ui.py`, `app/cli.py` | manual |
| FR-16, FR-21 | `scripts/coverage_report.py` | `test_exporters.py` |
| FR-17, FR-18 | `scripts/export_sources.py`, `scripts/export_sample_qa.py` | `test_exporters.py` |
| FR-19 | `app/pipeline.py` trace writer | `test_pipeline.py` |
| FR-20 | `generate/extractive.py` | `test_extractive.py` |

Build order for all of the above is in `docs/implementation.md`.

### 12.4 Known limits of this architecture

Stated plainly, because a demo that overstates its design is worse than a modest one.

| Limit | Detail | Would need |
| --- | --- | --- |
| Corpus scale | Designed for ~5 schemes / hundreds of chunks. Chroma HNSW is far more than this corpus needs | Nothing — deliberately over-provisioned for the brief |
| Embedding ceiling | 384-d MiniLM degrades on very large corpora (~10⁵+ chunks) | A larger embedder, re-index, re-tune Stage 2 |
| Prompt growth | All top-5 chunks go into one prompt; cost and latency grow linearly with chunk count | Reranking to top-2–3, or a cheaper tier (`claude-haiku-4-5`) |
| Concurrency | Single process, no request queue; fine for a demo, not for many users | Worker pool + caching layer |
| Freshness | No scheduler. The corpus is a snapshot that goes stale silently | Cron re-ingest + a staleness alert on `retrieved_at` |
| Coverage | One AMC, English only, Direct–Growth plans only | Per-PRD non-goals |
| Table extraction | `fields.json` regexes are tuned to the current factsheet layout | A layout change needs new patterns; the golden-set gate catches it |
| Reranker | Off by default (no extra model download) | Add a local cross-encoder if eval shows recall loss |

---

## 13. Extension points

| Extension | Touch points | Rough effort |
| --- | --- | --- |
| Add a second AMC | `config.SOURCES`, `config.ALLOWED_HOSTS`, add schemes to golden set | Low — the pipeline is AMC-agnostic |
| Add a new source type (e.g. AMFI NAV CSV) | New parser in `ingest/parse.py` + `extraction_method` enum value | Medium |
| Swap the LLM provider | One file: implement `Answerer` over the new SDK | Low |
| Turn on the cross-encoder reranker | `config.RETRIEVER.use_rerank`; `retrieve/rerank.py` already exists | Low |
| Stream citations inline | `QueryResult.citations` already carries section and page | Low |
| Multi-turn context | New module between stages 6 and 7; must re-run PII screening on history | Medium — PII in history is the trap |
| Live NAV lookup | **Out of scope** — violates the no-performance-claims constraint (G4) | Do not build |
