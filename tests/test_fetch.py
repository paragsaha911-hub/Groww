from __future__ import annotations

import json

import pytest

from app import config
from app.ingest import fetch
from app.ingest.fetch import FetchResult, detect_kind, robots_verdict, sha256_hex

GROWW_SOURCE = {
    "source_id": "S1_groww",
    "scheme_id": "S1",
    "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "authority": "mirror",
}


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(config, "MANUAL_SNAPSHOT_DIR", tmp_path / "raw" / "official_snapshots")
    for directory in (config.RAW_DIR, config.MANUAL_SNAPSHOT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fetch, "_last_request_at", {})
    yield


def _meta_path() -> "object":
    return config.RAW_DIR / "S1_groww.meta.json"


def test_non_allowlisted_host_is_refused_without_exception() -> None:
    result = fetch.fetch_source(
        {"source_id": "bad", "url": "https://evil-groww.in/x", "authority": "mirror"}
    )
    assert result.ok is False
    assert result.reason == fetch.REASON_HOST_NOT_ALLOWED
    assert result.raw_path is None


def test_lookalike_hosts_are_rejected() -> None:
    for url in (
        "https://groww.in.evil.com/mutual-funds/x",
        "https://evil-groww.in/mutual-funds/x",
        "https://notgroww.in/mutual-funds/x",
    ):
        result = fetch.fetch_source({"source_id": "bad", "url": url})
        assert result.reason == fetch.REASON_HOST_NOT_ALLOWED, url


def test_detect_kind_prefers_magic_bytes_over_content_type() -> None:
    assert detect_kind(b"%PDF-1.7\n...", "text/html") == fetch.KIND_PDF
    assert detect_kind(b"<!DOCTYPE html><html>", "application/pdf") == fetch.KIND_HTML
    assert detect_kind(b"<html><body>hi</body></html>", None) == fetch.KIND_HTML
    assert detect_kind(b"\x89PNG\r\n", "image/png") == fetch.KIND_UNKNOWN


def test_fetch_result_defaults_to_utc_aware_timestamp() -> None:
    result = FetchResult(source_id="s", url="https://groww.in/x", ok=False)
    assert result.retrieved_at is not None
    assert result.retrieved_at.tzinfo is not None
    assert result.retrieved_at.utcoffset().total_seconds() == 0
    assert result.is_pdf is False
    assert result.cached is False


def test_sha256_is_stable() -> None:
    assert sha256_hex(b"abc") == sha256_hex(b"abc")
    assert sha256_hex(b"abc") != sha256_hex(b"abd")


def test_robots_404_means_allowed(monkeypatch) -> None:
    class Response:
        status_code = 404
        text = ""

    class Client:
        def get(self, url, *args, **kwargs):
            return Response()

    verdict, reason, _ = robots_verdict("https://groww.in/mutual-funds/x", client=Client())
    assert verdict == fetch.VERDICT_ALLOW
    assert reason == "robots_absent_404"


def test_robots_403_is_unclear_not_allowed_and_not_disallowed(monkeypatch) -> None:
    class Response:
        status_code = 403
        text = "Access Denied"

    class Client:
        def get(self, url, *args, **kwargs):
            return Response()

    verdict, reason, status = robots_verdict("https://www.hdfcfund.com/x", client=Client())
    assert verdict == fetch.VERDICT_UNCLEAR
    assert reason == "robots_blocked_403"
    assert status == 403


def test_robots_transport_error_is_unclear(monkeypatch) -> None:
    class Client:
        def get(self, url, *args, **kwargs):
            raise RuntimeError("connect timeout")

    verdict, reason, _ = robots_verdict("https://groww.in/mutual-funds/x", client=Client())
    assert verdict == fetch.VERDICT_UNCLEAR
    assert reason == fetch.REASON_ROBOTS_UNCLEAR


def test_robots_disallow_blocks_the_source(monkeypatch) -> None:
    class Response:
        status_code = 200
        text = "User-agent: *\nDisallow: /private/\n"

    class Client:
        def get(self, url, *args, **kwargs):
            return Response()

    verdict, _, _ = robots_verdict("https://groww.in/private/x", client=Client())
    assert verdict == fetch.VERDICT_DISALLOW


def test_manual_snapshot_is_used_with_zero_network(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise AssertionError("network call despite snapshot")

    monkeypatch.setattr(fetch, "_client", explode)
    monkeypatch.setattr(fetch, "robots_verdict", explode)

    snapshot = config.MANUAL_SNAPSHOT_DIR / "S1_groww.pdf"
    snapshot.write_bytes(b"%PDF-1.4 fake factsheet bytes")
    (config.MANUAL_SNAPSHOT_DIR / "S1_groww.meta.json").write_text(
        json.dumps(
            {
                "url": "https://files.hdfcfund.com/s3fs-public/x.pdf",
                "retrieved_at": "2026-09-01T10:00:00+00:00",
                "content_type": "application/pdf",
            }
        ),
        encoding="utf-8",
    )

    result = fetch.fetch_source(GROWW_SOURCE)
    assert result.ok is True
    assert result.reason == fetch.REASON_MANUAL_SNAPSHOT
    assert result.extraction_method == "manual"
    assert result.is_pdf is True
    assert result.retrieved_at.isoformat() == "2026-09-01T10:00:00+00:00"
    assert result.content_hash == sha256_hex(b"%PDF-1.4 fake factsheet bytes")
    assert (config.RAW_DIR / "S1_groww.pdf").is_file()


def test_second_fetch_is_a_network_noop(monkeypatch) -> None:
    calls: list[str] = []

    class Response:
        status_code = 200
        content = b"<!DOCTYPE html><html><body>hello</body></html>"
        text = "User-agent: *\nDisallow:\n"
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, url, *args, **kwargs):
            calls.append(url)
            return Response()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(fetch, "_client", lambda *a, **k: Client())

    first = fetch.fetch_source(GROWW_SOURCE)
    assert first.ok is True
    assert first.reason == fetch.REASON_OK
    assert first.extraction_method == "mirror"
    assert first.retrieved_at is not None and first.retrieved_at.tzinfo is not None

    calls.clear()
    second = fetch.fetch_source(GROWW_SOURCE)
    assert second.ok is True
    assert second.reason == fetch.REASON_CACHED
    assert second.cached is True
    assert calls == []


def test_403_is_unreachable_not_a_robots_denial(monkeypatch) -> None:
    class Response:
        status_code = 403
        content = b"Access Denied"
        text = "User-agent: *\nDisallow:\n"
        headers = {"content-type": "text/html"}

        def __init__(self, status_code: int, content: bytes = b"", headers=None):
            self.status_code = status_code
            self.content = content
            self.headers = headers or {}

    class Client:
        def __init__(self, robots_status: int = 200):
            self.robots_status = robots_status

        def get(self, url, *args, **kwargs):
            if url.endswith("/robots.txt"):
                return Response(self.robots_status, b"User-agent: *\nDisallow:\n")
            return Response(403, b"Access Denied", {"content-type": "text/html"})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(fetch, "_client", lambda *a, **k: Client(200))
    monkeypatch.setattr(fetch, "_fetch_with_retries", lambda client, url, attempts=3: (Response(403, b"", {"content-type": "text/html"}), None))

    result = fetch.fetch_source(GROWW_SOURCE)
    assert result.ok is False
    assert result.reason == fetch.REASON_UNREACHABLE
    assert result.http_status == 403
    assert result.robots_verdict == fetch.VERDICT_ALLOW
    assert result.raw_path is None


def test_robots_unclear_refuses_without_fetching(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise AssertionError("fetched despite unclear robots")

    monkeypatch.setattr(fetch, "_fetch_with_retries", explode)
    monkeypatch.setattr(
        fetch, "robots_verdict", lambda url, client=None: (fetch.VERDICT_UNCLEAR, "robots_unparseable", 200)
    )

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(fetch, "_client", lambda *a, **k: Client())
    result = fetch.fetch_source(GROWW_SOURCE)
    assert result.ok is False
    assert result.reason == fetch.REASON_ROBOTS_UNCLEAR


def test_robots_disallowed_refuses_with_reason(monkeypatch) -> None:
    monkeypatch.setattr(
        fetch, "robots_verdict", lambda url, client=None: (fetch.VERDICT_DISALLOW, "robots_disallowed", 200)
    )

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(fetch, "_client", lambda *a, **k: Client())
    result = fetch.fetch_source(GROWW_SOURCE)
    assert result.ok is False
    assert result.reason == fetch.REASON_ROBOTS_DISALLOWED
    assert result.robots_verdict == fetch.VERDICT_DISALLOW


def test_meta_json_records_provenance_fields(monkeypatch) -> None:
    class Response:
        status_code = 200
        content = b"%PDF-1.7 official bytes"
        text = "User-agent: *\nDisallow:\n"
        headers = {"content-type": "application/pdf"}

    class Client:
        def get(self, url, *args, **kwargs):
            return Response()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(fetch, "_client", lambda *a, **k: Client())
    source = {**GROWW_SOURCE, "authority": "official"}
    result = fetch.fetch_source(source)
    assert result.ok is True
    assert result.is_pdf is True
    assert result.extraction_method == "pdf"

    payload = json.loads(_meta_path().read_text(encoding="utf-8"))
    for key in (
        "url",
        "http_status",
        "content_hash",
        "retrieved_at",
        "content_type",
        "byte_length",
        "kind",
        "extraction_method",
    ):
        assert key in payload, key
    assert payload["content_hash"] == result.content_hash
    assert payload["byte_length"] == len(b"%PDF-1.7 official bytes")
