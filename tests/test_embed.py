from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pytest

from app import config
from app.index.embed import (
    DimensionMismatchError,
    MiniLMEmbedder,
    cache_key,
    model_identity,
)


class StubEncoder:
    def __init__(self, dim: int = 8, calls: list[list[str]] | None = None) -> None:
        self.dim = dim
        self.calls = calls if calls is not None else []

    def __call__(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        out = []
        for text in texts:
            vector = np.zeros(self.dim, dtype=np.float32)
            for position, char in enumerate(text[: self.dim]):
                vector[position] = (ord(char) % 17) + 1.0
            out.append(vector)
        return np.vstack(out)


def make(tmp_path: Path, **kwargs) -> tuple[MiniLMEmbedder, StubEncoder]:
    calls: list[list[str]] = []
    encoder = StubEncoder(dim=kwargs.pop("dim", 8), calls=calls)
    embedder = MiniLMEmbedder(
        corpus_version=kwargs.pop("corpus_version", "cvtest"),
        model_id=kwargs.pop("model_id", "stub-model"),
        expected_dim=kwargs.pop("expected_dim", 8),
        batch_size=kwargs.pop("batch_size", 32),
        cache_dir=tmp_path / "cache",
        encoder=encoder,
        **kwargs,
    )
    return embedder, encoder


def test_vectors_are_unit_norm(tmp_path) -> None:
    embedder, _ = make(tmp_path)
    vectors = embedder.encode(["expense ratio is 1.03 percent", "riskometer moderately high"])
    for vector in vectors:
        assert abs(math.sqrt(sum(value * value for value in vector)) - 1.0) < 1e-6


def test_batch_size_is_respected(tmp_path) -> None:
    embedder, encoder = make(tmp_path, batch_size=32)
    texts = [f"chunk number {index} with some length variation here" for index in range(70)]
    embedder.encode(texts)
    assert encoder.calls
    assert all(len(call) <= 32 for call in encoder.calls)
    assert sum(len(call) for call in encoder.calls) == 70


def test_length_sorted_batching_restores_original_order(tmp_path) -> None:
    embedder, _ = make(tmp_path, batch_size=4)
    texts = [
        "short",
        "a considerably longer piece of text than the others in this list",
        "medium length text",
        "tiny",
        "another rather long sentence to make the lengths differ from one another",
    ]
    vectors = embedder.encode(texts)
    assert len(vectors) == len(texts)
    single = [embedder.encode([text])[0] for text in texts]
    for produced, expected in zip(vectors, single):
        assert produced == pytest.approx(expected, abs=1e-6)


def test_no_instruction_prefix_is_prepended(tmp_path) -> None:
    embedder, encoder = make(tmp_path)
    texts = ["what is the expense ratio", "exit load details"]
    embedder.encode(texts)
    embedded = [text for call in encoder.calls for text in call]
    assert sorted(embedded) == sorted(texts)
    for text in embedded:
        assert not text.lower().startswith(("query:", "passage:", "search_document:"))


def test_dimension_mismatch_raises_with_both_values(tmp_path) -> None:
    embedder, _ = make(tmp_path, dim=8, expected_dim=384)
    with pytest.raises(DimensionMismatchError) as excinfo:
        embedder.encode(["anything"])
    message = str(excinfo.value)
    assert "384" in message
    assert "8" in message


def test_cache_hit_avoids_recomputation(tmp_path) -> None:
    embedder, encoder = make(tmp_path)
    first = embedder.encode(["expense ratio 1.03", "exit load nil"])
    assert sum(len(call) for call in encoder.calls) == 2
    encoder.calls.clear()
    second = embedder.encode(["expense ratio 1.03", "exit load nil"])
    assert encoder.calls == []
    for produced, expected in zip(first, second):
        assert produced == pytest.approx(expected, abs=1e-6)


def test_cache_key_depends_on_version_model_and_text(tmp_path) -> None:
    base = cache_key("cv1", "m1", "text")
    assert base != cache_key("cv2", "m1", "text")
    assert base != cache_key("cv1", "m2", "text")
    assert base != cache_key("cv1", "m1", "other")
    assert base == cache_key("cv1", "m1", "text")
    assert len(base) == 64


def test_cache_is_not_shared_across_corpus_versions(tmp_path) -> None:
    calls: list[list[str]] = []
    encoder = StubEncoder(calls=calls)
    first = MiniLMEmbedder(
        corpus_version="cvA",
        model_id="stub-model",
        expected_dim=8,
        cache_dir=tmp_path / "cache",
        encoder=encoder,
    )
    second = MiniLMEmbedder(
        corpus_version="cvB",
        model_id="stub-model",
        expected_dim=8,
        cache_dir=tmp_path / "cache",
        encoder=encoder,
    )
    first.encode(["same text"])
    calls.clear()
    second.encode(["same text"])
    assert sum(len(call) for call in calls) == 1


def test_corrupt_cache_entry_is_recomputed(tmp_path) -> None:
    embedder, encoder = make(tmp_path)
    embedder.encode(["recoverable text"])
    assert sum(len(call) for call in encoder.calls) == 1
    for path in (tmp_path / "cache").glob("*.npy"):
        path.write_bytes(b"not a numpy file")
    encoder.calls.clear()
    embedder.encode(["recoverable text"])
    assert sum(len(call) for call in encoder.calls) == 1


def test_empty_input_returns_empty_list(tmp_path) -> None:
    embedder, encoder = make(tmp_path)
    assert embedder.encode([]) == []
    assert encoder.calls == []


def test_duplicate_texts_share_one_vector(tmp_path) -> None:
    embedder, encoder = make(tmp_path)
    vectors = embedder.encode(["same", "same", "same"])
    assert len(vectors) == 3
    assert vectors[0] == vectors[1] == vectors[2]
    assert sum(len(call) for call in encoder.calls) == 1


def test_non_string_input_is_rejected(tmp_path) -> None:
    embedder, _ = make(tmp_path)
    with pytest.raises(TypeError):
        embedder.encode([123])


def test_model_identity_matches_config() -> None:
    identity = model_identity()
    assert identity == {"model_id": config.EMBED_MODEL, "dim": config.EMBED_DIM}
    assert model_identity("other", 99) == {"model_id": "other", "dim": 99}


def test_real_defaults_come_from_config() -> None:
    embedder = MiniLMEmbedder(corpus_version="cv1")
    assert embedder.model_id == config.EMBED_MODEL
    assert embedder.dim == config.EMBED_DIM
    assert embedder.batch_size == config.EMBED_BATCH_SIZE
    assert embedder.cache_dir == config.EMBEDDING_CACHE_DIR


def test_model_cache_env_is_set_before_import() -> None:
    import os

    from app.index import embed

    assert os.environ["HF_HOME"] == str(config.MODELS_DIR)
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == str(config.MODELS_DIR)
    assert embed.os.environ["HF_HOME"] == str(config.MODELS_DIR)


def test_local_snapshot_detection(tmp_path) -> None:
    from app.index.embed import local_snapshot

    assert local_snapshot("sentence-transformers/all-MiniLM-L6-v2", tmp_path) is None
    hub_dir = tmp_path / "models--stub-org--stub-model"
    hub_dir.mkdir(parents=True)
    assert local_snapshot("stub-org/stub-model", tmp_path) == hub_dir
    plain = tmp_path / "plain-model"
    plain.mkdir()
    assert local_snapshot("org/plain-model", tmp_path) == plain


def test_cached_snapshot_loaded_without_network(tmp_path, monkeypatch) -> None:
    from app.index.embed import load_sentence_transformer

    hub_dir = tmp_path / "models--stub-org--stub-model"
    hub_dir.mkdir(parents=True)
    captured: dict[str, object] = {}

    class FakeModel:
        def __init__(self, model_id, **kwargs) -> None:
            captured.update(kwargs)
            captured["model_id"] = model_id

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.setitem(
        __import__("sys").modules, "sentence_transformers", type("M", (), {"SentenceTransformer": FakeModel})
    )
    load_sentence_transformer("stub-org/stub-model", cache_dir=tmp_path)
    assert captured["local_files_only"] is True
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"

    captured.clear()
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    load_sentence_transformer("absent-org/absent-model", cache_dir=tmp_path)
    assert captured["local_files_only"] is False
    assert "HF_HUB_OFFLINE" not in os.environ


@pytest.mark.slow
def test_real_model_downloads_once_then_runs_offline() -> None:
    embedder = MiniLMEmbedder(corpus_version="cvslow")
    vectors = embedder.encode(["HDFC Large Cap Fund direct growth expense ratio"])
    assert len(vectors) == 1
    assert len(vectors[0]) == config.EMBED_DIM
    assert abs(math.sqrt(sum(value * value for value in vectors[0])) - 1.0) < 1e-6
    again = MiniLMEmbedder(corpus_version="cvslow2").encode(
        ["HDFC Large Cap Fund direct growth expense ratio"]
    )
    assert len(again[0]) == config.EMBED_DIM
