from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app import config
from app.models import as_utc, utcnow

VERDICT_ALLOW = "allow"
VERDICT_DISALLOW = "disallow"
VERDICT_UNCLEAR = "unclear"

REASON_HOST_NOT_ALLOWED = "host_not_allowed"
REASON_ROBOTS_DISALLOWED = "robots_disallowed"
REASON_ROBOTS_UNCLEAR = "robots_unclear"
REASON_UNREACHABLE = "unreachable"
REASON_HTTP_ERROR = "http_error"
REASON_EMPTY_BODY = "empty_body"
REASON_OK = "ok"
REASON_CACHED = "cached"
REASON_MANUAL_SNAPSHOT = "manual_snapshot"

KIND_PDF = "pdf"
KIND_HTML = "html"
KIND_UNKNOWN = "unknown"

_last_request_at: dict[str, float] = {}


@dataclass
class FetchResult:
    source_id: str
    url: str
    ok: bool
    raw_path: str | None = None
    content_hash: str | None = None
    http_status: int | None = None
    reason: str | None = None
    retrieved_at: datetime | None = None
    byte_length: int = 0
    content_type: str | None = None
    kind: str = KIND_UNKNOWN
    extraction_method: str = "static"
    robots_verdict: str = VERDICT_UNCLEAR

    @property
    def is_pdf(self) -> bool:
        return self.kind == KIND_PDF

    @property
    def cached(self) -> bool:
        return self.reason == REASON_CACHED

    def __post_init__(self) -> None:
        if self.retrieved_at is None:
            self.retrieved_at = utcnow()
        self.retrieved_at = as_utc(self.retrieved_at)


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def detect_kind(content: bytes, content_type: str | None) -> str:
    if content[:5] == b"%PDF-":
        return KIND_PDF
    head = content[:2048].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html", b"<?xml")) or b"<html" in head:
        return KIND_HTML
    ctype = (content_type or "").lower()
    if "html" in ctype:
        return KIND_HTML
    if "pdf" in ctype:
        return KIND_PDF
    return KIND_UNKNOWN


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": config.USER_AGENT},
    )


def _throttle(url: str, min_interval: float = 1.0) -> None:
    host = config.host_of(url)
    now = time.monotonic()
    previous = _last_request_at.get(host)
    if previous is not None:
        wait = min_interval - (now - previous)
        if wait > 0:
            time.sleep(wait)
    _last_request_at[host] = time.monotonic()


def robots_verdict(
    url: str, client: httpx.Client | None = None
) -> tuple[str, str, str | None]:
    host = config.host_of(url)
    if not host:
        return VERDICT_UNCLEAR, REASON_ROBOTS_UNCLEAR, None
    scheme = urlparse(url).scheme or "https"
    robots_url = f"{scheme}://{host}/robots.txt"
    owned = client is None
    active = client or _client(timeout=15.0)
    try:
        response = active.get(robots_url)
    except Exception:
        return VERDICT_UNCLEAR, REASON_ROBOTS_UNCLEAR, None
    finally:
        if owned:
            active.close()

    if response.status_code == 404:
        return VERDICT_ALLOW, "robots_absent_404", response.status_code
    if response.status_code in (401, 403):
        return VERDICT_UNCLEAR, f"robots_blocked_{response.status_code}", response.status_code
    if response.status_code >= 400:
        return VERDICT_UNCLEAR, f"robots_http_{response.status_code}", response.status_code

    parser = RobotFileParser()
    try:
        parser.parse(response.text.splitlines())
    except Exception:
        return VERDICT_UNCLEAR, "robots_unparseable", response.status_code

    if parser.can_fetch(config.USER_AGENT, url):
        return VERDICT_ALLOW, "robots_allows", response.status_code
    return VERDICT_DISALLOW, REASON_ROBOTS_DISALLOWED, response.status_code


def raw_path_for(source_id: str, extension: str) -> Path:
    return config.RAW_DIR / f"{source_id}.{extension}"


def meta_path_for(source_id: str) -> Path:
    return config.RAW_DIR / f"{source_id}.meta.json"


def snapshot_candidates(source_id: str) -> list[Path]:
    if not config.MANUAL_SNAPSHOT_DIR.is_dir():
        return []
    return [
        path
        for path in sorted(config.MANUAL_SNAPSHOT_DIR.glob(f"{source_id}.*"))
        if path.suffix.lower() not in {".json"}
    ]


def _load_meta(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_snapshot(source: dict[str, Any]) -> FetchResult | None:
    source_id = source["source_id"]
    candidates = snapshot_candidates(source_id)
    if not candidates:
        return None
    path = candidates[0]
    content = path.read_bytes()
    if not content:
        return FetchResult(
            source_id=source_id,
            url=source["url"],
            ok=False,
            reason=REASON_EMPTY_BODY,
            extraction_method="manual",
        )
    meta = _load_meta(path.with_suffix(".meta.json")) or {}
    retrieved_raw = meta.get("retrieved_at")
    retrieved_at: datetime | None = None
    if isinstance(retrieved_raw, str):
        try:
            retrieved_at = as_utc(datetime.fromisoformat(retrieved_raw))
        except ValueError:
            retrieved_at = None
    content_type = meta.get("content_type")
    destination = raw_path_for(source_id, "pdf" if path.suffix.lower() == ".pdf" else "html")
    config.ensure_dirs()
    destination.write_bytes(content)
    meta_payload = {
        "source_id": source_id,
        "url": meta.get("url", source["url"]),
        "http_status": meta.get("http_status"),
        "content_hash": sha256_hex(content),
        "retrieved_at": (retrieved_at or utcnow()).isoformat(),
        "content_type": content_type,
        "byte_length": len(content),
        "extraction_method": "manual",
        "snapshot_path": str(path),
    }
    meta_path_for(source_id).write_text(
        json.dumps(meta_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return FetchResult(
        source_id=source_id,
        url=source["url"],
        ok=True,
        raw_path=str(destination),
        content_hash=meta_payload["content_hash"],
        http_status=None,
        reason=REASON_MANUAL_SNAPSHOT,
        retrieved_at=retrieved_at or utcnow(),
        byte_length=len(content),
        content_type=content_type,
        kind=detect_kind(content, content_type),
        extraction_method="manual",
    )


def _cached_result(source: dict[str, Any], force: bool) -> FetchResult | None:
    source_id = source["source_id"]
    meta = _load_meta(meta_path_for(source_id))
    if meta is None:
        return None
    raw = meta.get("raw_path") or config.RAW_DIR / f"{source_id}.{meta.get('kind', 'html')}"
    raw_path = Path(raw)
    if not raw_path.is_file():
        return None
    if not force and meta.get("content_hash"):
        content = raw_path.read_bytes()
        if sha256_hex(content) == meta["content_hash"]:
            retrieved_raw = meta.get("retrieved_at")
            retrieved_at = None
            if isinstance(retrieved_raw, str):
                try:
                    retrieved_at = as_utc(datetime.fromisoformat(retrieved_raw))
                except ValueError:
                    retrieved_at = None
            return FetchResult(
                source_id=source_id,
                url=source["url"],
                ok=True,
                raw_path=str(raw_path),
                content_hash=meta["content_hash"],
                http_status=meta.get("http_status"),
                reason=REASON_CACHED,
                retrieved_at=retrieved_at or utcnow(),
                byte_length=int(meta.get("byte_length") or 0),
                content_type=meta.get("content_type"),
                kind=meta.get("kind", KIND_UNKNOWN),
                extraction_method=meta.get("extraction_method", "static"),
            )
    return None


def _fetch_with_retries(
    client: httpx.Client, url: str, attempts: int = 3
) -> tuple[httpx.Response | None, str | None]:
    delay = 1.0
    last_reason = REASON_UNREACHABLE
    for attempt in range(attempts):
        _throttle(url)
        try:
            response = client.get(url)
        except Exception:
            last_reason = REASON_UNREACHABLE
        else:
            if response.status_code in (429, 503):
                last_reason = REASON_HTTP_ERROR
                retry_after = response.headers.get("Retry-After")
                wait = delay
                if retry_after:
                    try:
                        wait = max(delay, float(retry_after))
                    except ValueError:
                        wait = delay
                if attempt < attempts - 1:
                    time.sleep(wait)
                    delay *= 2
                    continue
                return response, last_reason
            return response, None
        if attempt < attempts - 1:
            time.sleep(delay)
            delay *= 2
    return None, last_reason


def fetch_source(source: dict[str, Any], force: bool = False) -> FetchResult:
    source_id = source["source_id"]
    url = source["url"]

    if not config.host_allowed(url):
        return FetchResult(
            source_id=source_id,
            url=url,
            ok=False,
            reason=REASON_HOST_NOT_ALLOWED,
        )

    snapshot = _read_snapshot(source)
    if snapshot is not None:
        return snapshot

    cached = _cached_result(source, force)
    if cached is not None:
        return cached

    authority = source.get("authority", "official")
    with _client() as client:
        verdict, robots_reason, robots_status = robots_verdict(url, client=client)
        if verdict == VERDICT_DISALLOW:
            return FetchResult(
                source_id=source_id,
                url=url,
                ok=False,
                reason=REASON_ROBOTS_DISALLOWED,
                http_status=robots_status,
                robots_verdict=verdict,
            )
        if verdict == VERDICT_UNCLEAR:
            return FetchResult(
                source_id=source_id,
                url=url,
                ok=False,
                reason=REASON_ROBOTS_UNCLEAR,
                http_status=robots_status,
                robots_verdict=verdict,
            )

        response, failure = _fetch_with_retries(client, url)
        if response is None:
            return FetchResult(
                source_id=source_id,
                url=url,
                ok=False,
                reason=failure or REASON_UNREACHABLE,
                robots_verdict=verdict,
            )

    status = response.status_code
    if status in (401, 403, 429) or status >= 500:
        return FetchResult(
            source_id=source_id,
            url=url,
            ok=False,
            reason=REASON_UNREACHABLE,
            http_status=status,
            robots_verdict=verdict,
        )
    if status >= 400:
        return FetchResult(
            source_id=source_id,
            url=url,
            ok=False,
            reason=REASON_HTTP_ERROR,
            http_status=status,
            robots_verdict=verdict,
        )

    content = response.content
    if not content:
        return FetchResult(
            source_id=source_id,
            url=url,
            ok=False,
            reason=REASON_EMPTY_BODY,
            http_status=status,
            robots_verdict=verdict,
        )

    content_type = response.headers.get("content-type")
    kind = detect_kind(content, content_type)
    extension = "pdf" if kind == KIND_PDF else "html"
    destination = raw_path_for(source_id, extension)
    config.ensure_dirs()
    destination.write_bytes(content)

    retrieved_at = utcnow()
    extraction_method = "mirror" if authority == "mirror" else ("pdf" if kind == KIND_PDF else "static")
    meta_payload = {
        "source_id": source_id,
        "url": url,
        "raw_path": str(destination),
        "http_status": status,
        "content_hash": sha256_hex(content),
        "retrieved_at": retrieved_at.isoformat(),
        "content_type": content_type,
        "byte_length": len(content),
        "kind": kind,
        "extraction_method": extraction_method,
        "robots_verdict": verdict,
        "robots_reason": robots_reason,
    }
    meta_path_for(source_id).write_text(
        json.dumps(meta_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return FetchResult(
        source_id=source_id,
        url=url,
        ok=True,
        raw_path=str(destination),
        content_hash=meta_payload["content_hash"],
        http_status=status,
        reason=REASON_OK,
        retrieved_at=retrieved_at,
        byte_length=len(content),
        content_type=content_type,
        kind=kind,
        extraction_method=extraction_method,
        robots_verdict=verdict,
    )


def fetch_all(
    sources: list[dict[str, Any]] | None = None, force: bool = False
) -> list[FetchResult]:
    return [fetch_source(source, force=force) for source in (sources or config.SOURCES)]
