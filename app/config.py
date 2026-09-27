from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from dotenv import load_dotenv

from app.models import AUTHORITY_MIRROR, AUTHORITY_OFFICIAL, Scheme, utcnow

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env", override=False)

os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / "data" / "models"))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(PROJECT_ROOT / "data" / "models"))

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EMBEDDING_CACHE_DIR = DATA_DIR / "embedding_cache"
MODELS_DIR = DATA_DIR / "models"
CHROMA_DIR = DATA_DIR / "chroma"
EVAL_DIR = DATA_DIR / "eval"
DOCS_DIR = PROJECT_ROOT / "docs"

ALL_DIRS = (
    RAW_DIR,
    PROCESSED_DIR,
    EMBEDDING_CACHE_DIR,
    MODELS_DIR,
    CHROMA_DIR,
    EVAL_DIR,
)

USER_AGENT = "hdfc-mf-facts-bot/0.1 (class project; contact: set-me@example.com)"

SCHEMES: list[Scheme] = [
    Scheme(
        scheme_id="S1",
        name="HDFC Large Cap Fund",
        category="Large Cap",
        plan="Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    ),
    Scheme(
        scheme_id="S2",
        name="HDFC Equity (Flexi Cap) Fund",
        category="Flexi Cap",
        plan="Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    ),
    Scheme(
        scheme_id="S3",
        name="HDFC ELSS Tax Saver Fund",
        category="ELSS / Tax",
        plan="Direct Plan Growth",
        url="https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    ),
    Scheme(
        scheme_id="S4",
        name="HDFC Small Cap Fund",
        category="Small Cap",
        plan="Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    ),
    Scheme(
        scheme_id="S5",
        name="HDFC Balanced Advantage Fund",
        category="Balanced Advantage (Hybrid)",
        plan="Direct Growth",
        url="https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth",
    ),
]

ALLOWED_HOSTS = frozenset(
    {
        "groww.in",
        # The AMC's fund-document site. hdfcamc.com is the corporate AMC site and is not
        # where scheme factsheets live. One entry covers www. and the files. CDN host.
        "hdfcfund.com",
        "amfiindia.com",
        "sebi.gov.in",
        "incometax.gov.in",
    }
)

# Reachability measured 2026-09-27 from the dev machine. Recorded because it decides
# which rung of the extraction ladder Phase 4 must use; it is an observation, not policy.
HOST_REACHABILITY = {
    "groww.in": "ok",
    "amfiindia.com": "ok",
    "hdfcfund.com": "akamai_403",
    "www.hdfcfund.com": "akamai_403",
    "files.hdfcfund.com": "akamai_403",
    "www.sebi.gov.in": "tls_handshake_timeout",
}

# hdfcfund.com answers 403 from this network for every path, robots.txt included, and
# with a browser User-Agent. It is an edge bot-protection block, not a robots denial, so
# it must not be recorded as a publisher permission problem. Ingest therefore falls back
# to manual snapshots placed in this directory.
MANUAL_SNAPSHOT_DIR = RAW_DIR / "official_snapshots"

REQUIRED_FACTS = (
    "expense_ratio",
    "exit_load",
    "min_sip",
    "min_amount",
    "lock_in",
    "riskometer",
    "benchmark",
)

LOCK_IN_SCHEMES = frozenset({"S3"})

OFFICIAL_SOURCE_TYPES = (
    "factsheet",
    "kim",
    "sid",
    "fee_page",
    "risk_note",
    "guide",
    "regulatory_note",
)

# Entry points used by ingest for discovery. The index is not itself a fact source: it is
# crawled to resolve the newest month-stamped PDF. The TER page is the publisher's own
# statutory expense-ratio disclosure and is the cross-check for any scraped number.
OFFICIAL_FACTSHEET_INDEX_URL = "https://www.hdfcfund.com/mutual-funds/factsheets"
OFFICIAL_TER_PAGE_URL = (
    "https://www.hdfcfund.com/statutory-disclosure/"
    "total-expense-ratio-of-mutual-fund-schemes/reports"
)

# Newest consolidated factsheet verified on 2026-09-27. Month-stamped, so this goes stale.
OFFICIAL_FACTSHEET_URL = (
    "https://files.hdfcfund.com/s3fs-public/2026-07/"
    "HDFC%20MF%20Factsheet%20-%20June%202026.pdf"
)
OFFICIAL_FACTSHEET_MONTH = "June 2026"
OFFICIAL_FACTSHEET_AS_OF = "2026-06-30"

# Page ranges read off the factsheet's own table of contents. Only recorded where
# confirmed; a missing hint means "resolve at parse time", never "same page as last time".
OFFICIAL_FACTSHEET_PAGE_HINTS = {"S3": "61-62", "S5": "42-45"}

# What the consolidated factsheet actually contains. min_sip, min_amount and lock_in are
# deliberately excluded: they are not in this document, so expecting them here would invite
# the extractor to bind a neighbouring scheme's number to the wrong scheme.
FACTSHEET_FACTS = ("expense_ratio", "exit_load", "benchmark", "riskometer")

# Per-scheme pages carry min_sip, min_amount and lock_in. Only the S1 slug was verified on
# the AMC site; S2-S5 slugs are deliberately absent rather than guessed.
OFFICIAL_SCHEME_PAGE_URLS = {
    "S1": "https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct",
}

# The factsheet calls S2 "HDFC Flexi Cap Fund" while the scheme name we carry is the older
# "HDFC Equity (Flexi Cap) Fund". Name matching that misses this alias silently drops S2
# from the corpus, so scoping must key on ISIN with these aliases as the display fallback.
SCHEME_NAME_ALIASES = {
    "S2": ("HDFC Flexi Cap Fund", "HDFC Equity (Flexi Cap) Fund"),
}

# The consolidated factsheet carries all five schemes, so scoping a source to one scheme has
# to key on ISIN. These were read from the live Groww payload on 2026-09-27 and are the
# verified identity of each Direct plan; they must be confirmed against the official PDF
# before an official snapshot is trusted, and a mismatch must fail the source rather than
# silently fall through to whichever scheme happens to appear first.
SCHEME_ISINS = {
    "S1": "INF179K01YV8",
    "S2": "INF179K01UT0",
    "S3": "INF179K01YS4",
    "S4": "INF179KA1RW5",
    "S5": "INF179K01WA6",
}

OFFICIAL_SOURCES: list[dict[str, Any]] = [
    {
        "source_id": f"{scheme.scheme_id}_hdfc_factsheet",
        "scheme_id": scheme.scheme_id,
        "url": OFFICIAL_FACTSHEET_URL,
        "title": f"HDFC MF consolidated factsheet {OFFICIAL_FACTSHEET_MONTH} - {scheme.name}",
        "source_type": "factsheet",
        "publisher": "HDFC Mutual Fund",
        "authority": AUTHORITY_OFFICIAL,
        "as_of": OFFICIAL_FACTSHEET_AS_OF,
        "page_hint": OFFICIAL_FACTSHEET_PAGE_HINTS.get(scheme.scheme_id),
        "isin": SCHEME_ISINS.get(scheme.scheme_id),
        "expected_facts": FACTSHEET_FACTS,
    }
    for scheme in SCHEMES
]

OFFICIAL_SOURCE_NOTES = (
    "The AMC publishes one month-stamped consolidated factsheet covering every open-ended "
    "scheme, so all five official entries share a single URL and are separated by "
    "fields.json scoping plus page_hint, never by filename. OFFICIAL_FACTSHEET_URL is "
    "pinned to the newest month verified on 2026-09-27 and will go stale; ingest must "
    "re-resolve the newest month from OFFICIAL_FACTSHEET_INDEX_URL and pin the resolved "
    "URL into the corpus version. Groww is never the authority for a number. "
    "Known gap: min_sip, min_amount and lock_in are not in the consolidated factsheet. "
    "They come from the per-scheme page, whose slugs are only verified for S1; S2-S5 slugs "
    "must be discovered from the index, not guessed. Until then those facts abstain."
)

MIRROR_SOURCES: list[dict[str, Any]] = [
    {
        "source_id": f"{scheme.scheme_id}_groww",
        "scheme_id": scheme.scheme_id,
        "url": scheme.url,
        "title": f"{scheme.name} ({scheme.plan}) - Groww scheme page",
        "source_type": "scheme_page",
        "publisher": "Groww",
        "authority": AUTHORITY_MIRROR,
        "expected_facts": [
            fact
            for fact in REQUIRED_FACTS
            if fact != "lock_in" or scheme.scheme_id in LOCK_IN_SCHEMES
        ],
    }
    for scheme in SCHEMES
]

SOURCES: list[dict[str, Any]] = OFFICIAL_SOURCES + MIRROR_SOURCES

CHUNKER = "C3"
CHUNKER_CANDIDATES = ("C1", "C2", "C3", "C4")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
CHUNK_SIZE_SWEEP = (300, 500, 800)
TOP_K = 5
TOP_K_FETCH = 20
TOP_K_SWEEP = (3, 5, 8)
RRF_K = 60
SIMILARITY_FLOOR = 0.30

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
EMBED_BATCH_SIZE = 32
CHROMA_COLLECTION = "hdfc_schemes"
CHROMA_HNSW_M = 16
CHROMA_HNSW_CONSTRUCTION_EF = 128

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
GROQ_CHEAP_MODEL = os.environ.get("GROQ_CHEAP_MODEL", "openai/gpt-oss-20b")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com")

LLM_MODEL = GROQ_MODEL
LLM_CHEAP_MODEL = GROQ_CHEAP_MODEL
LLM_BASE_URL = GROQ_BASE_URL
LLM_MAX_TOKENS = 300
LLM_TEMPERATURE = float(os.environ["LLM_TEMPERATURE"]) if os.environ.get("LLM_TEMPERATURE") else None
LLM_TIMEOUT_SECONDS = 30.0
LLM_MAX_RETRIES = 1
LLM_RETRY_BACKOFF_SECONDS = 1.0


def llm_api_key() -> str:
    return GROQ_API_KEY


def llm_model(model: str) -> str:
    if model == "cheap":
        return LLM_CHEAP_MODEL
    return LLM_MODEL

DISCLAIMER_SHORT = "Facts-only. No investment advice."

DISCLAIMER = (
    "Facts-only. No investment advice. This assistant shares published information "
    "about HDFC Asset Management schemes from public sources and does not recommend "
    "buying, selling or holding any investment. Mutual fund investments are subject to "
    "market risks; read all scheme related documents carefully. Verify every detail "
    "against the official factsheet and AMC website before acting."
)

SCOPE_STATEMENT = (
    "AMC: HDFC Asset Management \u00b7 Schemes: HDFC Large Cap, HDFC Equity (Flexi Cap), "
    "HDFC ELSS Tax Saver, HDFC Small Cap, HDFC Balanced Advantage (all Direct Growth). "
    "Sources: official HDFC AMC / AMFI / SEBI documents (factsheets, KIM/SID, fee and "
    "riskometer pages), with public Groww scheme pages used only as a labelled fallback."
)

TUNING_NOTES = {
    "CHUNKER": "Provisional. Set to the winner of scripts/chunk_experiment.py (Phase 7).",
    "CHUNK_SIZE": "Provisional. Set from the Phase 7 chunk_size sweep.",
    "SIMILARITY_FLOOR": (
        "Provisional. Tune on data/eval/golden_set.json in Phase 14, never by feel. "
        "A low floor produces confident wrong numbers; prefer silence."
    ),
    "LLM_MODEL": (
        "Read from GROQ_MODEL. No temperature/top_p/top_k is sent unless LLM_TEMPERATURE "
        "is set, so determinism comes from the frozen corpus and a fixed prompt."
    ),
    "GROQ_CHEAP_MODEL": "Cheap/low-latency tier for the Phase 12 fallback chain.",
}


def path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def ensure_dirs() -> None:
    for directory in ALL_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def host_of(url: str) -> str:
    parsed = urlparse(url if "//" in url else f"//{url}")
    return (parsed.hostname or "").lower()


def host_allowed(url_or_host: str) -> bool:
    host = host_of(url_or_host)
    if not host:
        return False
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_HOSTS)


def source_by_id(source_id: str) -> dict[str, Any] | None:
    for source in SOURCES:
        if source["source_id"] == source_id:
            return source
    return None


def scheme_by_id(scheme_id: str) -> Scheme | None:
    for scheme in SCHEMES:
        if scheme.scheme_id == scheme_id:
            return scheme
    return None


_PINNED_CORPUS_VERSION: str | None = None
_RUN_CORPUS_VERSION: str | None = None


def set_corpus_version(version: str) -> None:
    global _PINNED_CORPUS_VERSION
    _PINNED_CORPUS_VERSION = version


def corpus_fingerprint(content_hashes: Iterable[str]) -> str:
    joined = "\n".join(sorted({value for value in content_hashes if value}))
    return f"cv{sha256(joined.encode('utf-8')).hexdigest()[:16]}"


def corpus_version() -> str:
    global _RUN_CORPUS_VERSION
    if _PINNED_CORPUS_VERSION:
        return _PINNED_CORPUS_VERSION
    ensure_dirs()
    if _RUN_CORPUS_VERSION is None:
        _RUN_CORPUS_VERSION = utcnow().strftime("%Y%m%dT%H%M%SZ")
    return _RUN_CORPUS_VERSION
