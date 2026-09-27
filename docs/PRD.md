# PRD — HDFC Mutual Fund Facts-Only RAG Chatbot

| Field | Value |
| --- | --- |
| Document type | Product Requirements Document (engineering-grade) |
| Status | Draft v1.0 for team review |
| Owner | RAG Chatbot team (class demo project) |
| Source brief | `probemStatement.txt` — Milestone brief "Mutual Fund FAQs (Facts-Only Q&A)" |
| Target | Working prototype + submitable deliverables pack |

---

## 1. Summary

Build a **facts-only RAG chatbot** that answers factual questions about a scoped set of
HDFC Asset Management mutual fund schemes, using only official public web pages as its
knowledge base. Every answer is capped at three sentences, contains exactly one source
link, and carries a freshness stamp. Opinionated and performance-comparison questions are
refused with a polite redirect.

The system is a textbook RAG pipeline and must demonstrate every stage end to end:
**Loading → Chunking → Embedding → Vector Store → Retrieval → Generation → Guardrails.**

| Decision | Value | Rationale |
| --- | --- | --- |
| AMC | HDFC Asset Management | Fixed by brief; single AMC keeps scope demo-sized |
| Schemes | 5 (Large Cap, Flexi Cap, ELSS, Small Cap, Balanced Advantage), all Direct–Growth | Brief requires 3–5, one per category |
| Corpus | Official HDFC AMC / AMFI / SEBI documents (factsheets, KIM/SID, fee pages) as the source of truth; the 5 public Groww scheme pages as a labelled fallback | Brief-mandated public sources only |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-dim, cosine) | Brief-mandated; CPU-fast, no API cost |
| Vector DB | ChromaDB (persistent, local) | Brief-mandated |
| Chunking | Decided by experiment, not assumption (see §6.3) | Brief says "let the tooling decide based on the data" |
| Answer generation | **Anthropic Claude API**, default `claude-sonnet-5` | Confirmed with team; cheap tier `claude-haiku-4-5` |
| UI | Streamlit tiny UI + rich CLI fallback | Brief requires a tiny UI; CLI keeps demo working offline |

---

## 2. Problem & Opportunity

**Problem.** Retail investors comparing mutual fund schemes need the same handful of
facts over and over: expense ratio, exit load, minimum SIP/amount, ELSS lock-in,
riskometer level, benchmark, and how to download a capital-gains statement. These facts
live in factsheets, KIM/SID documents, fee pages and scattered across scheme pages. Finding
them is slow, and the numbers are easy to mis-transcribe.

**Who this helps**

| Persona | Need | Current pain |
| --- | --- | --- |
| Retail user comparing HDFC schemes | Side-by-side factual comparison of 5 schemes | Facts scattered across pages and PDFs; no single place to ask |
| Support / content team | Fast, consistent answers to repetitive MF questions | Manual lookup; inconsistent phrasing between agents |

**Why a RAG bot rather than search.** The questions are natural-language and the
answers must be phrased, summarised into ≤3 sentences, and cited. That is generation over
retrieval, not lookup. The bot must never invent a number, so every sentence must be
traceable to a retrieved chunk.

**Opportunity statement.** If we can answer 90% of a fixed 15-question factual evaluation
set with correct citations and zero advice leakage, the prototype demonstrates a
production-shaped RAG system on a genuinely useful, compliance-sensitive use case.

---

## 3. Goals & Non-Goals

### 3.1 Goals

| ID | Goal | Success signal |
| --- | --- | --- |
| G1 | Answer factual scheme questions from the scoped corpus | ≥90% correct answers on golden set |
| G2 | Every answer carries exactly one working source link | 100% of factual answers |
| G3 | Never give investment advice or opinionated guidance | 0 advice answers in eval + red-team set |
| G4 | Never state or compare returns/performance | 0 performance claims in eval |
| G5 | Never accept or store PII | 0 PII values persisted; 100% refusal on PII probes |
| G6 | Demonstrate every RAG stage visibly and reproducibly | Stage-by-stage CLI output + stored artifacts |
| G7 | Demo is reproducible on a laptop and offline after ingestion | Demo runs with network disabled post-ingest |

### 3.2 Non-Goals (explicitly out of scope)

- Buy / sell / hold recommendations, portfolio allocation, risk profiling, goal planning.
- Computing, comparing, ranking or displaying returns, NAV history, or performance ratios.
- Real-time or live data (NAV, AUM, fund performance) — static snapshot only.
- Multi-AMC coverage (no ICICI, Axis, etc.) and no user-uploaded documents.
- Account servicing: login, statements generation, transaction history, PAN-linked tax reports.
- Mobile app, multi-turn memory across sessions beyond the current turn, voice input.
- Production hardening: auth, rate limiting, multi-tenant storage, monitoring dashboards.

---

## 4. Scope of the Corpus

### 4.1 Schemes in scope (AMC: HDFC Asset Management)

| # | Scheme | Category | Plan | Source URL |
| --- | --- | --- | --- | --- |
| S1 | HDFC Large Cap Fund | Large Cap | Direct Growth | `https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth` |
| S2 | HDFC Equity (Flexi Cap) Fund | Flexi Cap | Direct Growth | `https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth` |
| S3 | HDFC ELSS Tax Saver Fund | ELSS / Tax | Direct Plan Growth | `https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth` |
| S4 | HDFC Small Cap Fund | Small Cap | Direct Growth | `https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth` |
| S5 | HDFC Balanced Advantage Fund | Balanced Advantage (Hybrid) | Direct Growth | `https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth` |

### 4.2 Supplementary permitted sources

**Sourcing decision (confirmed).** Facts come from **official HDFC AMC documents**. The
Groww pages in §4.1 are retained as a *secondary mirror and fallback* — they are the
brief-mandated 5 public pages, they are easy to parse, and they keep the demo working if a
PDF fetch breaks, but they are never the authority for a number. Every fact is traceable to
an official document; a fact that exists **only** on a mirror is not asserted.

All sources must be public, no login, no PII, no third-party blogs.

| Priority | Source type | Examples | Authority |
| --- | --- | --- | --- |
| P1 | **Official scheme factsheet (PDF)** | HDFC AMC monthly/quarterly factsheets | **Authoritative** for expense ratio/TER, benchmark, riskometer, exit load |
| P2 | **Official KIM / SID (PDF)** | HDFC AMC, AMFI | **Authoritative** for scheme terms, exit-load slabs, lock-in, minimum amounts |
| P3 | **Official fee & charges page** | HDFC AMC | Authoritative for TER, exit-load slabs, other expenses |
| P4 | **Official riskometer & benchmark note** | HDFC AMC, SEBI | Authoritative for risk level and benchmark name |
| P5 | Statement / tax-doc guides | HDFC AMC, income-tax guidance pages, Groww help centre | Authoritative for how-to steps |
| P6 | Regulatory notes | AMFI, SEBI | Authoritative for lock-in rules, ELSS 80C context |
| F | **Fallback mirror (non-authoritative)** | The 5 Groww scheme pages in §4.1 | Used only to fill extraction gaps; every answer citing a fallback must show a secondary-source label |

**Conflict resolution.** If P1–P6 and F disagree on a value, the official document wins
and the answer cites the official URL. Disagreements are logged to
`data/eval/source_conflicts.jsonl` and reported by `scripts/coverage_report.py`, so a stale
mirror is visible instead of silently wrong.

**Document date.** Official PDFs carry an `as of` date. Both the document's own date and our
`retrieved_at` are stored; the answer footer uses `retrieved_at` (as the brief's wording
requires) and the UI may additionally display the document date.

**Hard rule.** Only `groww.in`, `hdfcfund.com`, `amfiindia.com`, `sebi.gov.in` and
`incometax.gov.in` hosts may be ingested. Any other host is rejected by the loader with a
logged reason. No blogs, no YouTube transcripts, no forums.

`hdfcfund.com` covers `www.` and the `files.` CDN host, which is where the consolidated
factsheet PDFs actually live. The corporate site `hdfcamc.com` is **not** a source host:
its apex did not respond during Q8 and it is not where scheme factsheets are published.

**Measured reachability (2026-09-27).** Recorded because it selects the rung of the
extraction ladder, not because it changes policy. `hdfcfund.com` and `files.hdfcfund.com`
return `403` from the dev network for every path including `/robots.txt`, and still `403`
with a browser `User-Agent`; `www.sebi.gov.in` fails the TLS handshake; `groww.in` and
`amfiindia.com` respond normally. This is edge bot protection, **not** a robots denial, and
must never be recorded as a publisher-permission problem. The consequence is §4.4.

### 4.3 Deliverable: source list

The brief asks for a "source list of the 5 URLs you used", so `docs/sources.md` leads with
the 5 in-scope scheme URLs from §4.1, followed by the official documents actually ingested.

`docs/sources.md` (and `data/sources.csv`) records, per source: `source_id`, `scheme_id`,
`title`, `url`, `source_type`, `publisher`, `authority` (`official`/`mirror`),
`extraction_method` (`pdf`/`static`/`mirror`/`manual`), `document_date` (a factsheet's own
`as of` date where present), `retrieved_at`, `http_status`, `content_hash`, `chunk_count`,
`fields_extracted`, `is_complete`. Generated by `scripts/export_sources.py` — never
hand-edited, so it cannot drift from what is actually in the vector store.

### 4.4 Consequence of §4.2: the official path is manual-snapshot from this network

`hdfcfund.com` is edge-blocked from the dev machine, so ladder rungs 1–2 cannot execute
here. The design response is rung 4, promoted to the *primary* path for this project:

1. A reviewer downloads the newest consolidated factsheet PDF from
   `https://www.hdfcfund.com/mutual-funds/factsheets` on an unblocked network and saves it
   to `data/raw/official_snapshots/` unchanged, alongside a `.meta.json` recording the
   source URL, the download `retrieved_at`, and the SHA-256 of the file.
2. Ingest reads the local file, records `extraction_method = "manual"` and
   `authority = "official"`, and keeps the original publisher URL as the citation target.
3. `coverage_report.py` prints the snapshot's `retrieved_at` in the demo output so the
   evaluator can see the corpus age without opening the file.

This preserves the §4.2 invariant that official documents are the authority for numbers —
the automation is sacrificed, not the trust model. The alternative, promoting the Groww
mirror to primary, would silently redefine the project and is rejected. Attempting to defeat
the edge block with a spoofed `User-Agent` is also rejected: it was already tried and failed,
and working around bot protection is out of scope for a class demo.

**Open follow-up:** the factsheet is month-stamped, so a snapshot ages. The demo must pin
the snapshot it ships with and state its `as of` date, rather than implying live data.

---

## 5. Users & Primary Flows

| User | Flow | Success criteria |
| --- | --- | --- |
| Retail user | Opens app → sees welcome line + 3 example questions + "Facts-only. No investment advice." → asks about one scheme → reads ≤3 sentence answer + 1 source link + freshness stamp | Answers question without leaving the app |
| Retail user | Asks "Should I buy HDFC Small Cap?" | Polite refusal, facts-only message, relevant educational link, no opinion |
| Retail user | Asks "Which scheme returned the most last year?" | Redirect to official factsheet; no numbers computed |
| Support agent | Asks "What is the exit load on HDFC ELSS?" → copies answer + link into a ticket | Citation is sufficient for the agent to verify |
| Compliance reviewer | Runs `pytest` + eval script; inspects logs | Can confirm zero advice, zero performance claims, zero PII storage |
| Demo evaluator | Clones repo → `make ingest` → `make demo` | Works from a clean checkout |

### 5.1 Reference questions (must work)

1. "What is the expense ratio of HDFC Large Cap Fund?"
2. "Is there an exit load on HDFC ELSS Tax Saver Fund?"
3. "What is the minimum SIP amount for HDFC Small Cap Fund?"
4. "What is the lock-in period for the HDFC ELSS Tax Saver Fund?"
5. "What is the riskometer level of HDFC Balanced Advantage Fund?"
6. "What is the benchmark of HDFC Equity (Flexi Cap) Fund?"
7. "How do I download my capital gains statement?"

---

## 6. System Design

### 6.1 Pipeline overview

```
   [1] LOADING          [2] CHUNKING         [3] EMBEDDING        [4] VECTOR STORE
  fetch + parse   →    strategy from     →   all-MiniLM-L6-v2  →   ChromaDB persist
  robots + cache       experiment         →   384-d, L2-norm     →   HNSW, cosine
  clean to text        + metadata         →   batch 32           →   metadata filterable
                                │
                                ▼
   [5] RETRIEVAL      [6] GUARDRAILS           [7] GENERATION          [8] PRESENTATION
  embed query     →   PII scan, intent     →   LLM ≤3 sentences  →   answer + 1 link
  top-k + filter      classify, inject       grounded in chunks     + freshness + disclaimer
  score + dedupe      defense                                     refusal template
```

Each stage is a separately invocable, separately testable module with a persisted artifact.
No stage may be skipped in the demo.

### 6.2 Stage 1 — Loading

| Item | Specification |
| --- | --- |
| Input | Source URLs (§4.1 schemes, §4.2 official documents). Each source is declared in `config.py` with its `scheme_id`, `source_type`, `authority` (`official` / `mirror`), and expected facts. |
| Fetch | `httpx` with explicit User-Agent, 30 s timeout, max 1 req/s per host, 3 retries with exponential backoff, honours `Retry-After` |
| Robots | `urllib.robotparser` check per host; disallowed → skip + log with reason. A `403`/`5xx` or transport failure is **not** a robots verdict: record it as `unreachable`, never as "allowed" and never as "disallowed". |
| Raw cache | `data/raw/{source_id}.{html,pdf}` + `.meta.json`; content-hash keyed so re-runs are no-ops. PDFs are the primary cached artefact, so the demo never re-downloads a large file. |
| HTML parse | `beautifulsoup4` + `lxml`; drop `script`, `style`, `nav`, `footer`, `header`, cookie banners. Preserve heading hierarchy (`h1`–`h4`); serialise tables (fees, exit-load slabs) to pipe-delimited text so numbers survive. |
| PDF parse | `pypdf` page-by-page. Factsheets are tabular and column-heavy, so: extract text, then run a **field-regex pass** (`expense ratio`, `exit load`, `benchmark`, `riskometer`, `minimum SIP`, `lock-in`, `NAV`, `AUM`) per page. The regex pass is what makes numeric facts reliable; raw page text alone is retained as backup context. |
| Structure | Every chunk retains its page/section locator so a citation can point at factsheet page N. |
| Output | `data/processed/{source_id}.md` — normalised text + heading outline JSON + a `fields.json` of regex-extracted key/value facts per scheme. |
| Offline | All later stages read only from `data/`; no network at query time |

**Extraction ladder (order matters).** Official documents first; mirrors only to fill gaps.
`extraction_method` and a completeness flag are recorded per source in metadata.

1. **Official PDF** (consolidated monthly factsheet, then KIM/SID) — primary path,
   `extraction_method = "pdf"`.
2. **Official HTML page** on `hdfcfund.com` / `amfiindia.com` — `extraction_method = "static"`.
3. **Groww mirror** (§4.1) — fallback only, `extraction_method = "mirror"`, `authority = "mirror"`.
4. **Manual snapshot** — last resort, `extraction_method = "manual"`, requires a reviewer note.

**The official source is one document, not five.** HDFC publishes a single month-stamped
consolidated factsheet covering every open-ended scheme (≈139 pages, including
*Scheme performance summary — Direct Plans* and *Benchmark and Scheme riskometers*). All five
official entries therefore share one URL and are separated **only** by `fields.json` scheme
scoping and a page hint. This is the single most important structural fact for R1: the
document repeats `EXPENSE RATIO … Regular: x% Direct: y%` once per scheme, so a positional
or nearest-heading regex will happily bind a neighbouring scheme's number. Scoping must key
on ISIN, with the S2 display-name alias (`HDFC Flexi Cap Fund` vs our older
`HDFC Equity (Flexi Cap) Fund`) handled explicitly.

**Known hazard (high risk).** Both failure modes must be handled, because the corpus spans
two different hosts:

- ~~Groww pages may be **client-side rendered**, so a static fetch yields a shell without the
  numeric tables.~~ **Disproven 2026-09-27.** A static `httpx` GET of
  `hdfc-large-cap-fund-direct-growth` returned `200` with ≈450 KB of HTML that already
  contains a server-rendered `__NEXT_DATA__` block containing `expense_ratio`, `exit_load`,
  `benchmark`, `riskometer`, `min SIP` and `lock-in` for the requested plan. Mirrors
  therefore remain usable. They stay step 3 on principle — a mirror is never the authority
  for a number — but the completeness argument for that ordering is now R1-correctness, not
  R1b-renderability. Extract from the `__NEXT_DATA__` JSON, not from scraped visible text.
- Official factsheet PDFs are **heavily tabular**; naive text extraction scrambles fee and
  exit-load columns and silently produces wrong numbers. This is a *correctness* risk, not
  just a completeness risk, which is why the `fields.json` regex pass in §9.2 gets a
  100% numeric-exactness check and any regex/golden-set disagreement is a release blocker.
  Confirmed by inspection: the same factsheet carries at least three different
  `EXPENSE RATIO … Regular: 1.35% Direct: 0.75%` / `1.75% / 0.92%` / `1.56% / 1.03%` blocks
  for different schemes, and Groww independently showed `1.03` for HDFC Large Cap — the
  cross-source agreement that makes a scoped extraction testable at all.


A corpus row with `is_complete = false` is excluded from the evaluation set — an
incomplete corpus must fail loudly, not silently under-answer.

### 6.3 Stage 2 — Chunking (decided by experiment, per brief)

The brief explicitly asks that the chunking strategy be chosen based on the data, not
assumed. Therefore Stage 2 is a **measured decision**, and its artefact
(`docs/chunking-decision.md`) is a graded deliverable in its own right.

**Candidates evaluated**

| ID | Strategy | Rationale to test |
| --- | --- | --- |
| C1 | Fixed window, 500 tokens / 100 overlap | Baseline; simple, but splits fee tables mid-row |
| C2 | Recursive character split, 500 / 100, separators `\n## → \n\n → . → space` | Respects natural boundaries cheaply |
| C3 | Heading-aware / semantic | Section boundaries on these pages already align with fields (expense ratio, exit load, riskometer) — likely the winner |
| C4 | Overlap-free whole-section chunks | Largest context per chunk; hurts precision if sections are long |

**Decision procedure**

1. Build the golden question set (§9.1) *before* tuning, and freeze it.
2. For each candidate, chunk the corpus, embed, and run the identical retrieval config.
3. Score on: **hit@k** (correct scheme present in top-k), **MRR**, **section precision**
   (fraction of top-k chunks from the correct scheme *and* the correct heading), and
   **answer faithfulness** on a 5-question manual sample.
4. Select the winner, then sweep `chunk_size ∈ {300, 500, 800}` and
   `top_k ∈ {3, 5, 8}` once each on the same frozen set.
5. Write the chosen strategy, the table of scores, and the reasoning into
   `docs/chunking-decision.md`.

**Anticipated default (to be validated, not assumed).** Heading-aware splitting
(equivalent to recursive splitting seeded at Markdown heading boundaries), target
400–600 tokens, 80–120 token overlap, with `heading_path` and `section_title` retained as
metadata so the retriever can filter and the citation can name a section.

**Chunk metadata contract** (required for filtering + citation):

`chunk_id`, `source_id`, `scheme_id`, `scheme_name`, `category`, `section_title`,
`heading_path` (`>`-joined), `ordinal`, `token_count`, `char_start`, `char_end`,
`url`, `retrieved_at`, `extraction_method`, `corpus_version`.

### 6.4 Stage 3 — Embedding

| Item | Specification |
| --- | --- |
| Model | `sentence-transformers/all-MiniLM-L6-v2` (locked by `sentence-transformers` version) |
| Dimension | 384, L2-normalised so inner product == cosine |
| Batching | 32 texts, sorted by length to minimise padding waste |
| Query prefix | None for symmetric models; `all-MiniLM-L6-v2` is trained for symmetric similarity. Do **not** add "query:"/"passage:" prefixes — this is a common silent accuracy bug. |
| Caching | Chunk embeddings keyed by `(corpus_version, chunk_hash, model_id)` in `data/embedding_cache/` so re-ingest does not re-encode |
| Model identity | `model_id` and dimension stored alongside the collection; query time asserts the pair matches, else re-index |
| Offline | Model is cached under `data/models/` after first download so the demo needs no network |

### 6.5 Stage 4 — Vector Store

| Item | Specification |
| --- | --- |
| Engine | ChromaDB, `chromadb.PersistentClient(path="data/chroma")` |
| Collection | `hdfc_schemes`; distance `cosine` (safe if normalisation ever changes) |
| IDs | `chunk_id` — deterministic and idempotent, so re-ingest upserts instead of duplicating |
| Payload | All §6.3 metadata fields, so retrieval can do metadata pre-filtering |
| Index | Default HNSW (`hnsw:space=cosine`, `hnsw:M=16`, `hnsw:construction_ef=128`) |
| Rebuild | `scripts/ingest.py --rebuild` drops and recreates the collection, then prints per-stage counts |
| Provenance | `corpus_version` stored in collection metadata; a mismatch triggers a re-index warning |

### 6.6 Stage 5 — Retrieval

1. PII pre-screen and intent classify (§6.7) run **before** retrieval, so a refusal costs
   nothing and never sends user text to the LLM.
2. Embed the (PII-scrubbed) query with the same model.
3. Candidate pool: `top_k_fetch = 20`.
4. Optional pre-filter by `scheme_id` when the query names a scheme
   (deterministic match on normalised scheme aliases; wrong-but-confident scheme pinning
   is worse than no filter, so require a confident alias hit).
5. Optional keyword BM25-style lexical score from chunk headings to break cosine ties —
   useful for exact fields like "80C" or "Tier 1".
6. Fuse hybrid scores (reciprocal-rank fusion, `k=60`).
7. Rerank to `top_k = 5` with a cross-encoder **if** one is present locally; otherwise use
   a cheap heuristic (heading match + scheme match + density). Reranking is optional by
   design so the demo has no extra model download.
8. Apply a similarity floor. If the best score is below it, do **not** hallucinate — return
   the "not found in sources" path with the nearest links.

**Required output shape** for every retrieval: ordered `(chunk_id, score, rank)` with
fused and raw scores retained, so retrieval can be inspected independently of generation.

### 6.7 Stage 6 — Guardrails

#### 6.7.1 PII — refuse and never store

| Detector | Pattern basis | Action on hit |
| --- | --- | --- |
| PAN | `[A-Z]{5}[0-9]{4}[A-Z]` | Refuse, do not persist raw text |
| Aadhaar | 12 digits with optional `XXXX XXXX XXXX` spacing; Verhoeff checksum where possible | Refuse, do not persist raw text |
| Bank account no. | 8–18 digit standalone number | Refuse, do not persist raw text |
| IFSC | `[A-Z]{4}0[A-Z0-9]{6}` | Refuse |
| Card number | 13–19 digits passing a Luhn check | Refuse |
| OTP | 4–6 digits near `otp`/`one time`/`verification code` | Refuse |
| Email | RFC-shaped address | Refuse |
| Phone | `+91`/10-digit mobile shapes | Refuse |

Rules:

- On detection, the **raw query is never written to logs, cache, or trace**. Persist only
  `query_sha256`, the matched detector name, and a redacted preview.
- PII must never reach the LLM provider. Scrub before the retrieval embed and before any
  outbound call.
- False positives (e.g. a question containing the number 80C) are handled by requiring
  contextual keywords for the numeric detectors where ambiguity exists.
- A `tests/test_pii.py` suite asserts that none of a PII fixture set appears in any log
  file after an end-to-end run.

#### 6.7.2 Intent routing

| Intent | Examples | Behaviour |
| --- | --- | --- |
| `factual` | "expense ratio of X", "min SIP for X", "lock-in period" | Retrieve → answer with citation |
| `comparative_factual` | "expense ratio of X vs Y" | Answer per scheme, ≤3 sentences, cite each distinct source. No ranking, no "better". |
| `performance` | "returns of X", "which performed best", "NAV history" | Refuse to state numbers; reply with the official factsheet link and a neutral explanation |
| `advice` | "should I buy/sell X", "is X good for me", "which should I choose" | Refuse with facts-only message + educational link |
| `npi` (PII-bearing) | any PII detector hit | Refuse, no persistence |
| `out_of_scope` | "weather", "write code", unrelated AMC | Decline and state the corpus scope |

Classifier: high-precision keyword/regex rules first (deterministic, auditable, free), then
an LLM classifier for the residual. Order matters — `npi` → `advice` → `performance` →
`out_of_scope` → factual. Rules must catch every known advice phrase in the eval set, so the
system fails safe without depending on the model.

Refusal template (used for `advice`, `performance`, `out_of_scope`):

```
I only share published facts about HDFC schemes, and I don't give investment advice or
compare returns. Here you can read the official details:
<one educational / factsheet link>
```

#### 6.7.3 Prompt-injection defence

Retrieved chunks are untrusted input. Chunks are wrapped in explicit delimiters
(`<<<SOURCE id=...>>> ... <<<END>>>`), the system prompt states that content inside
delimiters is data and never instructions, and the model is told to ignore any directive
found in source text. A test plants an injected instruction in a fixture chunk and asserts
the bot does not comply.

### 6.8 Stage 7 — Generation

| Item | Specification |
| --- | --- |
| Interface | `Answerer` protocol with one method, `generate(system, user) -> str`. Implementations: `ClaudeAnswerer` (Anthropic API, default) and `ExtractiveAnswerer` (offline fallback). Selected by config. |
| SDK | `anthropic` (official Anthropic Python SDK). One SDK only; the `Answerer` interface keeps a future provider swap to a single file. |
| Default model | `claude-sonnet-5` — fast, 1M context, best balance for a ≤3-sentence grounded answer. `claude-haiku-4-5` is the cheap/low-latency tier. Model ID configurable via `ANTHROPIC_MODEL`. |
| `max_tokens` | Set explicitly (e.g. 300). Required by the API, and also our sentence-cap safety net. |
| Sampling params | **Do not send `temperature`, `top_p`, or `top_k`.** `claude-sonnet-5` returns **HTTP 400** for non-default sampling values. Determinism comes from the frozen corpus, fixed `top_k`, and a fixed prompt — not from a temperature knob. |
| Thinking | Adaptive thinking is on by default on `claude-sonnet-5`. For this short extraction task, keep effort low to control demo latency; verify the setting against the Anthropic docs before the live run. |
| Prompt shape | System prompt with role, hard rules (facts-only, ≤3 sentences, one link, no performance math, ignore embedded instructions), refusal policy, and the exact output contract. Then user message = intent + scrubbed query + numbered, delimited chunks + the required citation URL. |
| Grounding | Only retrieved chunks are supplied. Zero retrieved context → "not found in sources" path, never a free-form answer |
| Citation | Model must return the `source_id` it used; the app then renders the canonical URL from metadata, not from model text. This prevents hallucinated or malformed links. |
| Length | Post-check: sentence count ≤3. If exceeded, regenerate once with an explicit trim instruction; if still over, fall back to the extractive renderer |
| Freshness | Answer footer: `Last updated from sources: {max(retrieved_at of cited chunks)}` in `YYYY-MM-DD` |
| Failure handling | On API error, timeout, or rate limit, retry once with backoff, then fall back to `ExtractiveAnswerer` rather than failing the demo. The trace records which generator actually served the answer. |

The LLM never sees the user's raw text when PII was detected — that path returns before
generation.

### 6.9 Stage 8 — Presentation

Required UI content (brief-mandated):

- Welcome line.
- **3 example questions** (clickable).
- The note: **"Facts-only. No investment advice."**
- Answer area: ≤3 sentences, **one** citation link, freshness stamp.
- If the answer is grounded in a non-authoritative mirror, a small
  `Secondary source — verify on hdfcfund.com` label is shown (Q9; default on, because
  compliance favours transparency over a cleaner screen).
- Refusal styling visually distinct from a factual answer.

| Surface | Role |
| --- | --- |
| `app/ui.py` (Streamlit) | Primary demo surface; shareable link if hosted |
| `app/cli.py` (rich) | Offline fallback; also the debug view showing retrieved chunks and scores |

The UI must not display raw chunk scores to end users, but `?debug=1` (or a CLI flag)
exposes them — useful for the demo's architecture walkthrough.

---

## 7. Functional Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-1 | Ingest the 5 in-scope scheme pages plus approved supplementary sources, with robots check, raw caching, and content hashing | Must |
| FR-2 | Clean parsed HTML **and** PDF to text, preserving headings, tables and page locators; run the field-regex pass into `fields.json`; record `extraction_method`, `authority` and a completeness flag | Must |
| FR-2b | When an official document and a mirror disagree on a value, answer from the official document and log the conflict | Must |
| FR-3 | Evaluate ≥3 chunking strategies on a frozen question set and publish the decision + scores | Must |
| FR-4 | Chunk with the selected strategy and attach the full metadata contract | Must |
| FR-5 | Embed all chunks with `all-MiniLM-L6-v2`, L2-normalised, with an embedding cache | Must |
| FR-6 | Persist to ChromaDB with deterministic IDs and filterable metadata | Must |
| FR-7 | Retrieve top-k chunks by similarity, with optional metadata pre-filter and hybrid fusion | Must |
| FR-8 | Generate a ≤3-sentence answer grounded only in retrieved chunks, via the LLM answerer | Must |
| FR-9 | Render exactly one citation link per answer, sourced from metadata | Must |
| FR-10 | Append `Last updated from sources: YYYY-MM-DD` to every answer | Must |
| FR-11 | Refuse advice questions with a fixed polite message + educational link | Must |
| FR-12 | Refuse performance/return questions and link to the official factsheet instead | Must |
| FR-13 | Detect PII in input, refuse, and never persist raw input | Must |
| FR-14 | Defend against prompt injection embedded in retrieved chunks | Must |
| FR-15 | Tiny UI: welcome line, 3 example questions, "Facts-only. No investment advice." note | Must |
| FR-16 | Report corpus coverage: for which of the 5 target facts (expense ratio, exit load, min SIP, lock-in, riskometer) each scheme has a retrieved source | Should |
| FR-17 | Export `docs/sources.md` + `data/sources.csv` from actual index contents | Must |
| FR-18 | Export `docs/sample_qa.md` with 5–10 real query/answer/citation transcripts | Must |
| FR-19 | Log per-query trace: intent, top-k chunk IDs, scores, latency, model IDs, corpus version | Should |
| FR-20 | `?offline=1` / `--offline` mode uses the extractive answerer and local model only | Should |
| FR-21 | Corpus completeness report: per scheme, which required fields are present, with gaps listed | Should |
| FR-22 | Reject and log any source outside the approved host allowlist | Must |

---

## 8. Non-Functional Requirements

| ID | Category | Requirement |
| --- | --- | --- |
| NFR-1 | Reproducibility | `make ingest` on a clean checkout produces a byte-identical chunk set for unchanged sources |
| NFR-2 | Portability | Runs on Windows/macOS/Linux, Python 3.10+; no OS-specific paths in code |
| NFR-3 | Offline demo | Ingestion, embedding and retrieval are **fully offline** after first run (local corpus + local model cache + local Chroma). Generation normally needs network for the Claude API; `--offline` / `?offline=1` swaps in `ExtractiveAnswerer` so the whole demo still completes on a dead network |
| NFR-4 | Secrets | No API key in code or repo. `.env.example` documents `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`. `.env` is gitignored; a pre-commit secret scan is configured (R10) |
| NFR-5 | Latency | p50 ≤4 s, p95 ≤10 s end-to-end (local embedding, small corpus) |
| NFR-6 | Idempotency | Re-running ingest does not duplicate chunks; `--rebuild` gives a clean deterministic state |
| NFR-7 | Observability | Structured per-query trace (§FR-19) sufficient to debug a wrong answer without a debugger |
| NFR-8 | Testability | `pytest` suite with no network and no API key required for unit tests; LLM-dependent tests marked and skippable |
| NFR-9 | Rate limits | ≤1 req/s to any external host; honour `Retry-After` |
| NFR-10 | Accessibility of answers | Answers readable without colour reliance; links distinguishable by text, not colour alone |
| NFR-11 | Data footprint | Raw PDF/HTML snapshots retained locally for audit, and excluded from the repo if licensing requires it (Q3) |
| NFR-12 | Cost | Ingestion and eval runs cost $0; only query-time LLM calls are metered |

---

## 9. Evaluation & Acceptance

### 9.1 Golden set (created before chunking tuning, then frozen)

15 factual questions spanning all 5 schemes and the required fact types. Each row carries
`query`, `expected_scheme`, `expected_section`, `expected_source_url`, and whether the
answer must be numeric.

| Fact type | Example query | Must be exact |
| --- | --- | --- |
| Expense ratio | "Expense ratio of HDFC Large Cap Fund?" | Yes — a number |
| Exit load | "Exit load on HDFC ELSS Tax Saver?" | Yes — slabs |
| Minimum SIP | "Minimum SIP for HDFC Small Cap Fund?" | Yes — an amount |
| Lock-in | "Lock-in period for HDFC ELSS Tax Saver?" | Yes — period |
| Riskometer | "Riskometer level of HDFC Balanced Advantage?" | Yes — a level |
| Benchmark | "Benchmark of HDFC Equity (Flexi Cap) Fund?" | Yes — an index name |
| Statement guide | "How to download capital gains statement?" | No — steps |
| Cross-scheme | "Expense ratio of HDFC Large Cap vs HDFC Small Cap?" | Yes — two numbers |

### 9.2 Metrics

| Metric | Definition | Target |
| --- | --- | --- |
| Hit@k | Correct scheme in retrieved top-k | ≥95% at k=5 |
| MRR | Mean reciprocal rank of first correct chunk | ≥0.8 |
| Answer correctness | Answer matches golden fact, verified by reviewer (and LLM judge as a cross-check) | ≥90% |
| Numeric exactness | Numbers in the answer match the source exactly | 100% — any mismatch is a blocker |
| Field-extraction agreement | `fields.json` regex values agree with human-verified golden values, per scheme per fact | 100% — a disagreement blocks release |
| Official-vs-mirror conflicts | Logged to `source_conflicts.jsonl` and reported, with official winning | 100% logged |
| Citation validity | Exactly one citation; URL present in `sources.md`; section matches | 100% |
| Freshness stamp | Present and ≥ source `retrieved_at` | 100% |
| Length compliance | ≤3 sentences | 100% |
| Advice leakage | Advice-shaped answers on the advice probe set (≥20 probes) | 0 |
| Performance leakage | Any return/NAV number stated | 0 |
| PII leakage | PII values found in any log/artifact after PII probes | 0 |
| Refusal accuracy | Correct intent on the mixed probe set | ≥95% |
| Ingestion health | Chunks per source within expected band; 0 sources with `is_complete=false` | 100% |

### 9.3 Acceptance gate

The build is demo-ready when **all Must rows in §7 are implemented**, **every "0" target
in §9.2 holds**, and the four submitable artefacts in §11 exist. A single numeric mismatch
or a single PII leak blocks release of the demo.

---

## 10. Proposed Architecture & Repository Layout

The existing skeleton (`app/`, `data/`, `docs/`, `scripts/`, `tests/`) is kept.

```
myProject/
├─ PRD.md                      # this document
├─ probemStatement.txt         # original brief
├─ README.md                   # setup, scope, known limits   (deliverable)
├─ Makefile                    # ingest | chunk-exp | query | demo | ui | eval | coverage | sources | sample-qa | test
├─ requirements.txt
├─ requirements-dev.txt
├─ .env.example                # ANTHROPIC_API_KEY, ANTHROPIC_MODEL
├─ .gitignore                  # .env, data/chroma, data/models
├─ app/
│  ├─ config.py                # paths, model IDs, allowlist, tunables
│  ├─ models.py                # Document, Chunk, Citation, QueryResult
│  ├─ cli.py                   # rich CLI
│  ├─ ui.py                    # Streamlit tiny UI
│  ├─ ingest/
│  │  ├─ fetch.py              # httpx + robots + raw cache
│  │  ├─ parse.py              # HTML + PDF -> text/headings/tables/fields.json
│  │  └─ chunk.py              # strategies C1..C4
│  ├─ index/
│  │  ├─ embed.py              # all-MiniLM-L6-v2 + cache
│  │  └─ store.py              # ChromaDB wrapper
│  ├─ retrieve/
│  │  ├─ retriever.py          # top-k, pre-filter, RRF hybrid
│  │  └─ rerank.py             # optional cross-encoder
│  ├─ generate/
│  │  ├─ prompts.py            # system prompt + templates
│  │  ├─ claude.py             # ClaudeAnswerer (Anthropic SDK)
│  │  └─ extractive.py         # ExtractiveAnswerer (offline)
│  └─ guardrails/
│     ├─ pii.py                # detectors + scrubber
│     ├─ intent.py             # intent router
│     └─ injection.py          # source-delimiter guard
├─ scripts/
│  ├─ ingest.py                # run stages 1-4 end to end
│  ├─ chunk_experiment.py      # stage 2 decision experiment
│  ├─ query.py                 # one-off query from terminal
│  ├─ export_sources.py        # -> docs/sources.md, data/sources.csv
│  ├─ export_sample_qa.py      # -> docs/sample_qa.md
│  ├─ coverage_report.py       # corpus gap report (FR-16/21)
│  └─ eval.py                  # metrics in 9.2
├─ data/
│  ├─ raw/                     # cached HTML/PDF snapshots
│  ├─ processed/               # cleaned text + heading outline
│  ├─ embedding_cache/
│  ├─ models/                  # local sentence-transformers cache
│  ├─ chroma/                  # persistent vector store
│  ├─ sources.csv
│  └─ eval/golden_set.json, traces.jsonl
├─ docs/
│  ├─ PRD.md
│  ├─ architecture.md          # how it is built (diagram + data flow)
│  ├─ implementation.md        # phase-by-phase build playbook
│  ├─ chunking-decision.md     # stage 2 evidence
│  ├─ evaluation.md            # metric report  (D8)
│  ├─ sources.md               # deliverable    (D2)
│  ├─ sample_qa.md             # deliverable    (D4)
│  ├─ limitations.md
│  └─ demo-script.md           # 3-minute walkthrough
└─ tests/
   ├─ test_smoke.py            # config sanity (Phase 0)
   ├─ test_models.py           # schema contract (Phase 1)
   ├─ test_pii.py
   ├─ test_intent.py
   ├─ test_fetch.py            # allowlist, robots, cache (Phase 4)
   ├─ test_parsing.py
   ├─ test_chunker.py
   ├─ test_embed.py            # offline stub + @pytest.mark.slow real-model
   ├─ test_store.py            # idempotent upsert, identity assert
   ├─ test_retriever.py
   ├─ test_injection.py
   ├─ test_claude.py           # LLM-marked, skippable without a key
   ├─ test_extractive.py
   ├─ test_pipeline.py         # guardrail ordering, no-side-effect refusals
   └─ test_exporters.py
```

### 10.1 Dependency changes

Current `requirements.txt` covers ingestion and indexing but not generation or the UI.

| Add | Purpose | Required? |
| --- | --- | --- |
| `anthropic` | Claude API client (default provider) | Yes |
| `pypdf` | Parse official HDFC AMC factsheet / KIM / SID PDFs (now the primary source path) | Yes |
| `tiktoken` | Prompt token accounting / truncation guard | Recommended |
| `streamlit` | Tiny hosted demo UI | Yes |
| `rank-bm25` | Lexical scoring for hybrid fusion | Optional |
| `sentence-transformers` | Already present | — |
| `pytest` | Already in `requirements-dev.txt` | — |

Only one LLM SDK is added (`anthropic`). The `Answerer` interface means a future move to
`openai`/`google-genai` is a one-file change, not a refactor.

---

## 11. Deliverables

| # | Deliverable | Location | Owner stage |
| --- | --- | --- | --- |
| D1 | Working prototype (app) or ≤3-min demo video | hosted Streamlit URL, else `docs/demo-script.md` + recording | M7 |
| D2 | Source list of the URLs used | `docs/sources.md`, `data/sources.csv` | M2 |
| D3 | README: setup steps, scope (AMC + schemes), known limits | `README.md` | M7 |
| D4 | Sample Q&A: 5–10 queries with answers + links | `docs/sample_qa.md` | M6 |
| D5 | Disclaimer snippet as used in the UI | `README.md` + `app/config.py` constant | M5 |
| D6 | Chunking decision record | `docs/chunking-decision.md` | M3 |
| D7 | Architecture diagram + RAG stage walkthrough | `docs/architecture.md` | M7 |
| D8 | Evaluation report | `docs/evaluation.md` | M6 |

**Disclaimer snippet (exact text, used verbatim in the UI):**

> Facts-only. No investment advice. This assistant shares published information about
> HDFC Asset Management schemes from public sources and does not recommend buying,
> selling or holding any investment. Mutual fund investments are subject to market
> risks; read all scheme related documents carefully. Verify every detail against the
> official factsheet and AMC website before acting.

**Scope statement (verbatim, for the welcome line and README):**

> AMC: HDFC Asset Management · Schemes: HDFC Large Cap, HDFC Equity (Flexi Cap), HDFC
> ELSS Tax Saver, HDFC Small Cap, HDFC Balanced Advantage (all Direct Growth).
> Sources: official HDFC AMC / AMFI / SEBI documents (factsheets, KIM/SID, fee and
> riskometer pages), with public Groww scheme pages used only as a labelled fallback.

---

## 12. Milestones

| # | Milestone | Output | Depends on |
| --- | --- | --- | --- |
| M0 | Scaffold: `config`, `models`, paths, `.env.example`, `Makefile`, requirements updated | Runnable skeleton, `pytest` green | — |
| M1 | Stage 1 Loading: fetch official PDFs + HTML, robots, cache, PDF/HTML parse, `fields.json` field extraction, completeness + authority flags | `data/processed/*` populated | M0 |
| M2 | Golden set frozen + `docs/sources.md` v1 | D2, eval fixture | M1 |
| M3 | Stage 2 Chunking: implement C1–C4, run experiment, publish decision | D6 | M2 |
| M4 | Stages 3–4: embed, ChromaDB persist, rebuild script | Working index | M3 |
| M5 | Stage 6 guardrails: PII, intent, injection, disclaimer constant | Refusal paths + `test_pii.py` | M4 |
| M6 | Stages 5,7: retriever, LLM answerer, extractive fallback, citation, freshness; export sample Q&A | D4, eval report | M5 |
| M7 | Stage 8 UI, coverage report, README, architecture doc, demo script, final eval gate | D1, D3, D7, D8 | M6 |

Critical path: **M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7**. M2 (freezing the golden set)
must precede M3 (tuning) or the evaluation is meaningless.

---

## 13. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| R1 | Official factsheet PDFs are tabular; naive extraction scrambles fee/exit-load columns and yields **wrong** numbers | High | High | Field-regex pass into `fields.json` (§6.2), numeric exactness target 100%, any regex/golden-set disagreement is a release blocker, official doc beats mirror on conflict |
| R1b | ~~Groww mirror pages are client-side rendered; static fetch yields no facts~~ **Disproven 2026-09-27** — pages are server-rendered with facts in `__NEXT_DATA__` (§6.2) | ~~High~~ Low | Medium | Mirrors stay step 3 because a mirror is never the authority for a number, not because they are empty; extract from `__NEXT_DATA__`; completeness flag + `coverage_report.py` still surfaces gaps |
| R1c | ~~`hdfcamc.com` robots.txt disallows automated PDF fetch~~ **Superseded 2026-09-27** — wrong host, and the real host returns `403` from the edge rather than a robots denial | ~~Medium~~ **High (certain)** | High | Realised: rung 4 promoted to primary per §4.4, official authority preserved via manual snapshot with a recorded `retrieved_at` and SHA-256 |
| R1d | All five official entries share one 139-page consolidated factsheet, so a positional regex binds a neighbouring scheme's `Regular:`/`Direct:` pair to the wrong scheme | High | High | Scope by ISIN not position or heading proximity; `SCHEME_NAME_ALIASES` for the S2 rename; per-scheme numeric exactness asserted against a hand-checked golden set |
| R2 | LLM invents or alters a number | Medium | High | Grounded-only prompting, no sampling params (§6.8), fixed corpus + fixed `top_k` for determinism, 100% exact-numeric eval target, extractive fallback, 3-sentence cap |
| R3 | Advice leaks through an innocuous phrasing | Medium | High | Deterministic rules before the LLM classifier, 20+ adversarial advice probes in eval, hard system-prompt rules |
| R4 | PII reaches a log file or the LLM provider | Low | High | Detect → refuse → persist only a hash; `test_pii.py` scans artifacts end-to-end |
| R5 | Prompt injection via a fetched page | Low | Medium | Delimiter isolation, data-not-instructions system prompt, injection test fixture |
| R6 | Pages change during the project and numbers drift | Medium | Medium | `content_hash` + `retrieved_at` per source, freshness stamp in every answer, "verify with factsheet" line |
| R7 | Demo fails live (no network, no API key, no model download) | Medium | High | `--offline` mode, local model + corpus cache, pre-recorded run as backup, `.env.example` documented |
| R8 | Embedding model or index silently mismatched, giving nonsense retrieval | Low | High | Store `model_id` + dimension in collection metadata and assert on query |
| R9 | Chunks too small, losing the table context a fee question needs | Medium | Medium | Explicit chunk experiment (§6.3); include a table-aware chunk variant |
| R10 | API key committed to the repo | Low | High | `.env` gitignored, `.env.example` only, pre-commit secret scan, NFR-4 |
| R11 | Scope creep into returns/NAV to make the demo look smarter | Medium | Medium | Non-goals in §3.2, performance intent refusal, compliance reviewer in the loop |
| R12 | Hosting unavailable (no Streamlit account) | Medium | Low | CLI demo is a first-class surface; deliver ≤3-min video as allowed by the brief |

---

## 14. Open Questions

| # | Question | Why it matters | Status / Owner |
| --- | --- | --- | --- |
| Q1 | Which LLM provider at demo time? | Determines the SDK and model | **Resolved — Anthropic Claude, `claude-sonnet-5`**, `claude-haiku-4-5` as cheap tier |
| Q2 | Groww mirror, or official HDFC AMC PDFs as the fact source? | PDFs are authoritative but need a parser and carry a column-scrambling correctness risk | **Resolved — official HDFC AMC documents are the source of truth**; Groww retained as labelled fallback |
| Q3 | Is committing cached PDF/HTML snapshots acceptable licensing-wise? | Now more important: PDFs are the primary cached artefact. Affects `.gitignore` and NFR-11 | Open — Team |
| Q4 | Hosted Streamlit link, or local app + video? | Brief allows either; decides D1 format | Open — Team |
| Q5 | Should the bot answer comparative questions across schemes, or refuse anything comparative? | Affects `comparative_factual` scope and eval set | Open — Team |
| Q6 | Is `sentence-transformers` fine on CPU, or is a hosted embedding API acceptable? | all-MiniLM-L6-v2 on CPU is ~80 ms/query — fine, but confirm | Open — Team |
| Q7 | Should freshness be source `retrieved_at` or the factsheet's own `as of` date? | "Last updated from sources" wording implies the former; both are stored, so this only picks the footer value | Open — Team |
| Q8 | ~~Does `hdfcamc.com` robots.txt permit automated PDF fetch at our request rate?~~ **Answered 2026-09-27: no automated fetch is possible, but not for the reason asked.** `hdfcamc.com` is the wrong host — it is the corporate AMC site and its apex did not respond. The real host, `hdfcfund.com`, serves `/robots.txt` as `403` from the edge (Akamai `errors.edgesuite.net`), and `403`s every path including with a browser `User-Agent`; `files.hdfcfund.com` behaves identically. So there is no robots permission to evaluate: the publisher's bot protection denies us before robots semantics apply. | Manual-snapshot path is now **required**, not a contingency — §4.4 promotes rung 4 to primary and keeps official authority intact. Resolved |
| Q9 | Do we show the mirror's "secondary source" label in the demo UI, or keep the UI simple? | Compliance transparency vs. UI simplicity | Open — Team |

---

## 15. Appendices

### 15.1 Canonical intents and refusal copy

| Intent | Answer template |
| --- | --- |
| `factual` | `{fact in ≤3 sentences}` + `Source: {url}` + `Last updated from sources: {date}` |
| `comparative_factual` | `{per-scheme facts, no ranking}` + one source per scheme + freshness stamp |
| `performance` | `I don't state or compare returns. The official factsheet has the scheme's published performance: {factsheet url}` |
| `advice` | `I only share published facts and don't give investment advice. To evaluate this yourself, read: {educational link}` |
| `npi` | `I can't accept personal identifiers like PAN, Aadhaar, account numbers, OTPs, email or phone. Please re-ask without them.` |
| `out_of_scope` | `I only cover HDFC AMC's Large Cap, Flexi Cap, ELSS, Small Cap and Balanced Advantage funds. Sources: {sources link}` |
| `not_found` | `I couldn't find that in my sources. Closest matches: {top-2 section names}. Try asking about expense ratio, exit load, minimum SIP, lock-in, riskometer or benchmark.` |

### 15.2 Trace record schema (one line per query, `data/eval/traces.jsonl`)

```json
{
  "ts": "ISO-8601",
  "query_sha256": "hex",
  "query_redacted": "expense ratio of hdfc large cap fund",
  "pii_detected": [],
  "intent": "factual",
  "retrieved": [{"rank": 1, "chunk_id": "s1_c004", "score": 0.71, "scheme_id": "S1", "section": "Fees"}],
  "answer": "...",
  "citations": [{"source_id": "s1", "url": "https://groww.in/...", "section": "Fees"}],
  "sentence_count": 2,
  "generator": "claude:claude-sonnet-5",
  "embed_model": "all-MiniLM-L6-v2",
  "authority": "official",
  "corpus_version": "2026-09-27T10:12:04Z",
  "latency_ms": 2380,
  "refused": false
}
```

### 15.3 Terminology

| Term | Meaning in this document |
| --- | --- |
| AMC | Asset Management Company (here: HDFC AMC) |
| Factsheet | Official periodic scheme document with fees, benchmark, riskometer, performance |
| Riskometer | SEBI-mandated risk level label shown on a scheme page |
| TER | Total Expense Ratio; the ongoing cost figure investors compare |
| Direct Growth | Plan variant with no distributor commission; higher-return potential, no commission paid |
| ELSS lock-in | Statutory 3-year holding period for ELSS investments (Section 80C) |
| RRF | Reciprocal Rank Fusion; the score-combining method used in retrieval |
| Grounded | Every sentence traceable to a retrieved chunk |
