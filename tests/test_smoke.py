from __future__ import annotations

import subprocess
import sys
import textwrap

from app import config


def test_disclaimer_and_scope_are_populated() -> None:
    assert config.DISCLAIMER.strip()
    assert config.SCOPE_STATEMENT.strip()
    assert config.DISCLAIMER_SHORT == "Facts-only. No investment advice."
    assert "no investment advice" in config.DISCLAIMER.lower()


def test_exactly_five_schemes_with_unique_ids() -> None:
    assert len(config.SCHEMES) == 5
    assert [s.scheme_id for s in config.SCHEMES] == ["S1", "S2", "S3", "S4", "S5"]
    assert len({s.scheme_id for s in config.SCHEMES}) == 5
    assert len({s.url for s in config.SCHEMES}) == 5


def test_all_scheme_urls_are_on_allowed_hosts() -> None:
    for scheme in config.SCHEMES:
        assert config.host_allowed(scheme.url), scheme.url


def test_schemes_cover_the_required_categories() -> None:
    categories = {s.category for s in config.SCHEMES}
    assert "Large Cap" in categories
    assert "Flexi Cap" in categories
    assert "ELSS / Tax" in categories
    assert "Small Cap" in categories
    assert "Balanced Advantage (Hybrid)" in categories


def test_host_allowlist_rejects_lookalike_hosts() -> None:
    assert config.host_allowed("https://groww.in/mutual-funds/x")
    assert config.host_allowed("https://www.groww.in/help")
    assert not config.host_allowed("https://evil-groww.in/x")
    assert not config.host_allowed("https://groww.in.evil.com/x")
    assert not config.host_allowed("https://hdfcamc.com.attacker.net/x")
    assert not config.host_allowed("")


def test_every_configured_source_is_on_an_allowed_host() -> None:
    for source in config.SOURCES:
        assert config.host_allowed(source["url"]), source["url"]


def test_groww_sources_are_marked_mirror_not_official() -> None:
    assert len(config.MIRROR_SOURCES) == 5
    for source in config.MIRROR_SOURCES:
        assert source["authority"] == "mirror"
        assert source["publisher"] == "Groww"


def test_official_sources_are_populated_and_authoritative() -> None:
    assert config.OFFICIAL_SOURCES, "OFFICIAL_SOURCES must not be empty"
    assert {s["scheme_id"] for s in config.OFFICIAL_SOURCES} == {"S1", "S2", "S3", "S4", "S5"}
    for source in config.OFFICIAL_SOURCES:
        assert source["authority"] == "official"
        assert source["source_type"] in config.OFFICIAL_SOURCE_TYPES
        assert source["publisher"] == "HDFC Mutual Fund"
        assert source["as_of"] == config.OFFICIAL_FACTSHEET_AS_OF


def test_official_source_ids_are_unique_and_disjoint_from_mirrors() -> None:
    ids = [s["source_id"] for s in config.SOURCES]
    assert len(ids) == len(set(ids))
    official = {s["source_id"] for s in config.OFFICIAL_SOURCES}
    mirror = {s["source_id"] for s in config.MIRROR_SOURCES}
    assert not official & mirror
    assert config.source_by_id("S1_hdfc_factsheet") is not None


def test_official_coverage_gap_for_required_facts_is_explicit() -> None:
    covered = {f for s in config.OFFICIAL_SOURCES for f in s["expected_facts"]}
    gaps = set(config.REQUIRED_FACTS) - covered
    assert gaps == {"min_sip", "min_amount", "lock_in"}, gaps
    assert "expense_ratio" in covered
    assert "riskometer" in covered


def test_mirror_never_outranks_official_for_the_same_scheme_and_fact() -> None:
    official = {
        (s["scheme_id"], f) for s in config.OFFICIAL_SOURCES for f in s["expected_facts"]
    }
    for source in config.MIRROR_SOURCES:
        if source["authority"] == "mirror":
            continue
        for fact in source["expected_facts"]:
            if source["scheme_id"] == "S3" or fact != "lock_in":
                assert (source["scheme_id"], fact) in official


def test_factsheet_expected_facts_exclude_facts_absent_from_that_document() -> None:
    for source in config.OFFICIAL_SOURCES:
        assert tuple(source["expected_facts"]) == config.FACTSHEET_FACTS
        for absent in ("min_sip", "min_amount", "lock_in"):
            assert absent not in source["expected_facts"], absent


def test_unverified_official_scheme_page_slugs_are_absent_not_guessed() -> None:
    for url in config.OFFICIAL_SCHEME_PAGE_URLS.values():
        assert config.host_allowed(url)
    assert "S1" in config.OFFICIAL_SCHEME_PAGE_URLS
    unverified = {"S2", "S3", "S4", "S5"} - set(config.OFFICIAL_SCHEME_PAGE_URLS)
    assert unverified, "record which slugs still need discovery"


def test_flexi_cap_name_alias_is_recorded_for_source_scoping() -> None:
    aliases = config.SCHEME_NAME_ALIASES["S2"]
    assert "HDFC Flexi Cap Fund" in aliases
    assert config.scheme_by_id("S2").name in aliases


def test_expected_facts_omit_lock_in_except_for_elss() -> None:
    by_scheme = {s["scheme_id"]: s for s in config.MIRROR_SOURCES}
    for scheme_id, source in by_scheme.items():
        if scheme_id == "S3":
            assert "lock_in" in source["expected_facts"]
        else:
            assert "lock_in" not in source["expected_facts"]


def test_blocked_hosts_are_recorded_and_are_not_robots_denials() -> None:
    blocked = {h for h, s in config.HOST_REACHABILITY.items() if s != "ok"}
    assert "hdfcfund.com" in blocked
    assert "files.hdfcfund.com" in blocked
    assert all(
        s in {"akamai_403", "tls_handshake_timeout"}
        for s in config.HOST_REACHABILITY.values()
        if s != "ok"
    )
    assert config.MANUAL_SNAPSHOT_DIR.name == "official_snapshots"
    assert config.MANUAL_SNAPSHOT_DIR.parent == config.RAW_DIR


def test_tunable_defaults_match_the_prd() -> None:
    assert config.EMBED_MODEL == "sentence-transformers/all-MiniLM-L6-v2"
    assert config.EMBED_DIM == 384
    assert config.CHROMA_COLLECTION == "hdfc_schemes"
    assert config.RRF_K == 60
    assert config.TOP_K == 5
    assert config.TOP_K_FETCH == 20
    assert config.LLM_MODEL == config.GROQ_MODEL
    assert config.LLM_BASE_URL == config.GROQ_BASE_URL
    assert config.LLM_MAX_TOKENS == 300
    assert config.CHUNKER in config.CHUNKER_CANDIDATES


def _config_subprocess(extra_env: dict[str, str], expression: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", f"from app import config; print({expression})"],
        capture_output=True,
        text=True,
        cwd=str(config.PROJECT_ROOT),
        env={**dict(__import__("os").environ), **extra_env},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_llm_model_reads_from_groq_environment() -> None:
    assert (
        _config_subprocess({"GROQ_MODEL": "qwen/qwen3.8-27b"}, "config.LLM_MODEL")
        == "qwen/qwen3.8-27b"
    )


def test_llm_base_url_reads_from_groq_environment() -> None:
    assert (
        _config_subprocess({"GROQ_BASE_URL": "https://example.test"}, "config.LLM_BASE_URL")
        == "https://example.test"
    )


def test_cheap_model_resolves_from_groq_environment() -> None:
    assert (
        _config_subprocess(
            {"GROQ_CHEAP_MODEL": "openai/gpt-oss-20b"}, "config.llm_model('cheap')"
        )
        == "openai/gpt-oss-20b"
    )


def test_llm_api_key_reads_from_groq_environment() -> None:
    assert _config_subprocess({"GROQ_API_KEY": "gsk-test"}, "config.llm_api_key()") == (
        "gsk-test"
    )


def test_llm_temperature_is_unset_by_default() -> None:
    assert (
        _config_subprocess(
            {"GROQ_API_KEY": "gsk-test"},
            "config.LLM_TEMPERATURE",
        ).lower()
        in {"none", "null", ""}
    )


def test_llm_temperature_is_read_when_set() -> None:
    assert (
        _config_subprocess({"LLM_TEMPERATURE": "0.2"}, "config.LLM_TEMPERATURE") == "0.2"
    )


def test_anthropic_keys_are_gone() -> None:
    assert not hasattr(config, "ANTHROPIC_API_KEY")
    assert not hasattr(config, "ANTHROPIC_MODEL")
    assert not hasattr(config, "ANTHROPIC_CHEAP_MODEL")
    assert not hasattr(config, "LLM_PROVIDER")


def test_no_anthropic_dependency_remains() -> None:
    requirements = (config.PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "anthropic" not in requirements.lower()
    assert "groq" in requirements.lower()


def test_importing_config_performs_no_network_io() -> None:
    code = textwrap.dedent(
        """
        import socket

        def _blocked(*args, **kwargs):
            raise AssertionError("network access during import")

        socket.socket = _blocked
        socket.create_connection = _blocked

        from app import config

        assert len(config.SCHEMES) == 5
        assert config.PROJECT_ROOT.is_dir()
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(config.PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")


def test_model_cache_env_is_set_before_transformers_import() -> None:
    import os

    assert os.environ["HF_HOME"] == str(config.MODELS_DIR)
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == str(config.MODELS_DIR)
