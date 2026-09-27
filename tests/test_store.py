from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from app import config
from app.index.embed import MiniLMEmbedder
from app.index.store import (
    CHUNK_METADATA_FIELDS,
    ChromaStore,
    ModelIdentityMismatchError,
    chunk_metadata,
    coerce_metadata_value,
)
from app.models import AUTHORITY_MIRROR, AUTHORITY_OFFICIAL, Chunk, Document, ScoredChunk

DIM = 8


def make_chunk(source_id: str, scheme_id: str, ordinal: int, text: str, **kwargs) -> Chunk:
    return Chunk(
        chunk_id=f"{source_id}_c{ordinal:04d}",
        source_id=source_id,
        scheme_id=scheme_id,
        scheme_name=kwargs.get("scheme_name", f"Fund {scheme_id}"),
        category=kwargs.get("category", "Large Cap"),
        section_title=kwargs.get("section_title", "Expense ratio"),
        heading_path=kwargs.get("heading_path", f"Fund {scheme_id}>Expense ratio"),
        text=text,
        ordinal=ordinal,
        char_start=kwargs.get("char_start", 0),
        char_end=kwargs.get("char_end", len(text)),
        url=kwargs.get("url", "https://groww.in/funds/x"),
        retrieved_at=kwargs.get(
            "retrieved_at", datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
        ),
        authority=kwargs.get("authority", AUTHORITY_MIRROR),
        corpus_version=kwargs.get("corpus_version", "cvtest"),
        page=kwargs.get("page"),
        token_count=kwargs.get("token_count", 10),
        document_date=kwargs.get("document_date", date(2026, 6, 30)),
    )


def vector(seed: int) -> list[float]:
    array = np.zeros(DIM, dtype=np.float32)
    array[seed % DIM] = 1.0
    return [float(value) for value in array]


def make_store(tmp_path: Path, corpus_version: str = "cvtest") -> ChromaStore:
    return ChromaStore(
        corpus_version=corpus_version,
        path=tmp_path / "chroma",
        collection_name="test_collection",
    )


def set_metadata(store: ChromaStore, **updates: Any) -> None:
    merged = {**store.stored_metadata(), **updates}
    merged.pop("hnsw:space", None)
    store.collection.modify(metadata=merged)


def test_upsert_is_idempotent(tmp_path) -> None:
    store = make_store(tmp_path)
    chunks = [
        make_chunk("S1_groww", "S1", 1, "expense ratio 1.03"),
        make_chunk("S1_groww", "S1", 2, "exit load one percent"),
    ]
    vectors = [vector(0), vector(1)]
    assert store.upsert(chunks, vectors) == 2
    assert store.count() == 2
    store.upsert(chunks, vectors)
    store.upsert(chunks, vectors)
    assert store.count() == 2


def test_upsert_updates_in_place_without_duplicating(tmp_path) -> None:
    store = make_store(tmp_path)
    chunk = make_chunk("S1_groww", "S1", 1, "expense ratio 1.03")
    store.upsert([chunk], [vector(0)])
    updated = make_chunk("S1_groww", "S1", 1, "expense ratio 1.21 corrected")
    store.upsert([updated], [vector(1)])
    assert store.count() == 1
    assert store.query(vector(1), top_k=1)[0].chunk.text == "expense ratio 1.21 corrected"


def test_upsert_rejects_count_mismatch(tmp_path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.upsert([make_chunk("S1_groww", "S1", 1, "a")], [])


def test_upsert_with_no_chunks_is_a_noop(tmp_path) -> None:
    store = make_store(tmp_path)
    assert store.upsert([], []) == 0
    assert store.count() == 0


def test_none_page_and_datetime_metadata_are_coerced(tmp_path) -> None:
    store = make_store(tmp_path)
    chunk = make_chunk("S1_groww", "S1", 1, "no page", page=None, document_date=None)
    store.upsert([chunk], [vector(0)])
    metadata = chunk_metadata(chunk)
    assert isinstance(metadata["retrieved_at"], str)
    assert metadata["document_date"] == ""
    assert isinstance(metadata["page"], int)
    result = store.query(vector(0), top_k=1)
    assert result[0].chunk.page is None
    assert result[0].chunk.document_date is None


def test_all_architecture_metadata_fields_are_stored(tmp_path) -> None:
    store = make_store(tmp_path)
    chunk = make_chunk(
        "S3_groww", "S3", 4, "lock in three years", page=61, authority=AUTHORITY_OFFICIAL
    )
    store.upsert([chunk], [vector(0)])
    stored = store.collection.get(include=["metadatas"])["metadatas"][0]
    for field in CHUNK_METADATA_FIELDS:
        assert field in stored, field
    assert stored["page"] == 61
    assert stored["authority"] == AUTHORITY_OFFICIAL
    assert stored["document_date"] == "2026-06-30"
    assert stored["retrieved_at"].startswith("2026-09-27")


def test_coerce_metadata_value_types() -> None:
    assert coerce_metadata_value(None) == ""
    assert coerce_metadata_value(True) is True
    assert coerce_metadata_value(3) == 3
    assert coerce_metadata_value(1.5) == 1.5
    assert coerce_metadata_value(date(2026, 6, 30)) == "2026-06-30"
    assert coerce_metadata_value(datetime(2026, 6, 30, tzinfo=timezone.utc)).startswith(
        "2026-06-30"
    )
    assert coerce_metadata_value([1, 2]) == "[1, 2]"


def test_where_filter_returns_only_that_scheme(tmp_path) -> None:
    store = make_store(tmp_path)
    chunks = [
        make_chunk("S1_groww", "S1", 1, "s1 one", scheme_name="HDFC Large Cap Fund"),
        make_chunk("S1_groww", "S1", 2, "s1 two", scheme_name="HDFC Large Cap Fund"),
        make_chunk("S2_groww", "S2", 1, "s2 one", scheme_name="HDFC Flexi Cap Fund"),
    ]
    store.upsert(chunks, [vector(0), vector(1), vector(2)])
    results = store.query(vector(2), top_k=5, where={"scheme_id": "S2"})
    assert results
    assert {r.chunk.scheme_id for r in results} == {"S2"}
    assert store.query(vector(0), top_k=5, where={"scheme_id": "S1"})
    assert {r.chunk.scheme_id for r in store.query(vector(0), 5, {"scheme_id": "S1"})} == {
        "S1"
    }


def test_query_returns_ranked_scored_chunks(tmp_path) -> None:
    store = make_store(tmp_path)
    store.upsert(
        [make_chunk("S1_groww", "S1", i, f"text {i}") for i in (1, 2, 3)],
        [vector(0), vector(3), vector(5)],
    )
    results = store.query(vector(0), top_k=3)
    assert [r.rank for r in results] == [1, 2, 3]
    assert all(isinstance(r, ScoredChunk) for r in results)
    assert results[0].cosine_score == pytest.approx(1.0, abs=1e-5)
    assert results[0].chunk_id == "S1_groww_c0001"
    scores = [r.fused_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_query_respects_top_k(tmp_path) -> None:
    store = make_store(tmp_path)
    store.upsert(
        [make_chunk("S1_groww", "S1", i, f"text {i}") for i in range(1, 6)],
        [vector(i) for i in range(5)],
    )
    assert len(store.query(vector(0), top_k=2)) == 2
    assert store.query(vector(0), top_k=0) == []


def test_assert_model_identity_passes_for_fresh_store(tmp_path) -> None:
    store = make_store(tmp_path)
    store.assert_model_identity()


def test_assert_model_identity_raises_after_tampering(tmp_path) -> None:
    store = make_store(tmp_path)
    set_metadata(store, embed_model="some/other-model")
    with pytest.raises(ModelIdentityMismatchError) as excinfo:
        store.assert_model_identity()
    assert "re-index required" in str(excinfo.value)
    assert "some/other-model" in str(excinfo.value)


def test_assert_model_identity_raises_on_dimension_change(tmp_path) -> None:
    store = make_store(tmp_path)
    set_metadata(store, embed_dim=999)
    with pytest.raises(ModelIdentityMismatchError) as excinfo:
        store.assert_model_identity()
    assert "999" in str(excinfo.value)


def test_query_calls_assert_model_identity(tmp_path) -> None:
    store = make_store(tmp_path)
    store.upsert([make_chunk("S1_groww", "S1", 1, "text")], [vector(0)])
    set_metadata(store, embed_model="tampered/model")
    with pytest.raises(ModelIdentityMismatchError):
        store.query(vector(0), top_k=1)


def test_collection_metadata_records_provenance(tmp_path) -> None:
    store = make_store(tmp_path, corpus_version="cvabc123")
    metadata = store.stored_metadata()
    assert metadata["hnsw:space"] == "cosine"
    assert metadata["hnsw:M"] == config.CHROMA_HNSW_M
    assert metadata["hnsw:construction_ef"] == config.CHROMA_HNSW_CONSTRUCTION_EF
    assert metadata["corpus_version"] == "cvabc123"
    assert metadata["embed_model"] == config.EMBED_MODEL
    assert metadata["embed_dim"] == config.EMBED_DIM


def test_corpus_version_mismatch_is_detected(tmp_path) -> None:
    store = make_store(tmp_path, corpus_version="cvold")
    fresh = make_store(tmp_path, corpus_version="cvnew")
    fresh.assert_model_identity()
    with pytest.raises(ModelIdentityMismatchError):
        fresh.assert_corpus_version()


def test_drop_removes_orphans(tmp_path) -> None:
    store = make_store(tmp_path)
    store.upsert(
        [make_chunk("S1_groww", "S1", i, f"text {i}") for i in (1, 2, 3)],
        [vector(0), vector(1), vector(2)],
    )
    assert store.count() == 3
    store.drop()
    assert store.count() == 0
    store.upsert([make_chunk("S2_groww", "S2", 1, "fresh")], [vector(3)])
    assert store.count() == 1
    assert {r.chunk.scheme_id for r in store.query(vector(3), top_k=1)} == {"S2"}


def test_rebuild_yields_count_equal_to_chunks_created(tmp_path) -> None:
    store = make_store(tmp_path)
    encoder = MiniLMEmbedder(
        corpus_version="cvtest",
        model_id="stub-model",
        expected_dim=DIM,
        cache_dir=tmp_path / "cache",
        encoder=lambda texts: np.vstack(
            [np.eye(DIM, dtype=np.float32)[index % DIM] for index, _ in enumerate(texts)]
        ),
    )
    chunks = [
        make_chunk("S1_groww", "S1", index, f"chunk {index}") for index in range(1, 6)
    ] + [make_chunk("S2_groww", "S2", index, f"chunk {index}") for index in range(1, 4)]
    store.upsert(chunks, encoder.encode([chunk.text for chunk in chunks]))
    assert store.count() == len(chunks)
    store.upsert(chunks, encoder.encode([chunk.text for chunk in chunks]))
    assert store.count() == len(chunks)
    store.drop()
    store.upsert(chunks, encoder.encode([chunk.text for chunk in chunks]))
    assert store.count() == len(chunks)


class StubCollection:
    def __init__(self, name: str, metadata: dict[str, Any] | None) -> None:
        self.name = name
        self.metadata = dict(metadata or {})

    def count(self) -> int:
        return 0


class StubClient:
    def __init__(self) -> None:
        self.requested: list[tuple[str, dict[str, Any]]] = []

    def get_or_create_collection(self, name: str, metadata: dict[str, Any] | None) -> Any:
        self.requested.append((name, dict(metadata or {})))
        return StubCollection(name, metadata)


def test_store_uses_config_paths_by_default() -> None:
    client = StubClient()
    store = ChromaStore(corpus_version="cvcfg", client=client)
    assert store.collection_name == config.CHROMA_COLLECTION
    assert store.path == config.CHROMA_DIR
    name, metadata = client.requested[0]
    assert name == config.CHROMA_COLLECTION
    assert metadata["corpus_version"] == "cvcfg"
    assert metadata["hnsw:space"] == "cosine"


def test_purge_keeps_live_collection_index(tmp_path) -> None:
    from app.index.store import purge_orphan_segments

    store = make_store(tmp_path)
    store.upsert([make_chunk("S1_groww", "S1", 1, "text")], [vector(0)])
    store.assert_model_identity()
    before = {p.name for p in (tmp_path / "chroma").iterdir() if p.is_dir()}
    assert before
    assert purge_orphan_segments(tmp_path / "chroma").removed == []
    after = {p.name for p in (tmp_path / "chroma").iterdir() if p.is_dir()}
    assert after == before
    assert store.count() == 1
    assert store.query(vector(0), top_k=1)


def test_purge_removes_only_orphan_dirs(tmp_path) -> None:
    from app.index.store import purge_orphan_segments

    store = make_store(tmp_path)
    store.upsert([make_chunk("S1_groww", "S1", 1, "text")], [vector(0)])
    live = {p.name for p in (tmp_path / "chroma").iterdir() if p.is_dir()}
    root = tmp_path / "chroma"
    orphan_one = root / "31b959ac-ab99-4e5f-b184-e03c796695e3"
    orphan_two = root / "7ba8cf6b-aabe-47b8-9f8b-bcffa4b646d5"
    for orphan in (orphan_one, orphan_two):
        (orphan / "nested").mkdir(parents=True)
        (orphan / "data_level0.bin").write_bytes(b"stale")
    keep_dir = root / "not-a-uuid"
    keep_dir.mkdir()
    (keep_dir / "important.txt").write_text("keep me", encoding="utf-8")
    removed = purge_orphan_segments(root)
    assert sorted(removed.removed) == sorted([orphan_one.name, orphan_two.name])
    assert not orphan_one.exists() and not orphan_two.exists()
    assert keep_dir.is_dir() and (keep_dir / "important.txt").is_file()
    remaining = {p.name for p in root.iterdir() if p.is_dir()}
    assert {name for name in remaining if name != "not-a-uuid"} == live
    assert store.count() == 1


def test_purge_is_noop_without_database(tmp_path) -> None:
    from app.index.store import purge_orphan_segments

    empty = tmp_path / "chroma"
    (empty / "31b959ac-ab99-4e5f-b184-e03c796695e3").mkdir(parents=True)
    assert purge_orphan_segments(empty).removed == []
    assert (empty / "31b959ac-ab99-4e5f-b184-e03c796695e3").is_dir()
    assert purge_orphan_segments(tmp_path / "missing").removed == []


def test_drop_purges_orphans(tmp_path) -> None:
    store = make_store(tmp_path)
    store.upsert([make_chunk("S1_groww", "S1", 1, "text")], [vector(0)])
    root = tmp_path / "chroma"
    store.drop()
    assert set(store.purged_segments) | set(store.skipped_segments)
    assert store.count() == 0
    store.upsert([make_chunk("S1_groww", "S1", 1, "text again")], [vector(0)])
    assert store.count() == 1


def test_drop_leaves_nothing_behind_when_not_locked(tmp_path) -> None:
    from app.index.store import purge_orphan_segments

    store = make_store(tmp_path)
    store.upsert([make_chunk("S1_groww", "S1", 1, "text")], [vector(0)])
    store.drop()
    result = purge_orphan_segments(tmp_path / "chroma")
    assert result.removed == []


def test_identity_metadata_maps_to_collection_keys() -> None:
    from app.index.store import identity_metadata

    assert identity_metadata() == {
        "embed_model": config.EMBED_MODEL,
        "embed_dim": config.EMBED_DIM,
    }
    assert identity_metadata({"model_id": "m", "dim": 5}) == {"embed_model": "m", "embed_dim": 5}


def test_fingerprint_documents_is_order_independent() -> None:
    from app.index.store import fingerprint_documents

    first = Document(
        source_id="S1_groww",
        scheme_id="S1",
        url="u1",
        title="t1",
        source_type="scheme_page",
        authority=AUTHORITY_MIRROR,
        extraction_method="bs4",
        retrieved_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
        content_hash="h1",
    )
    second = Document(
        source_id="S2_groww",
        scheme_id="S2",
        url="u2",
        title="t2",
        source_type="scheme_page",
        authority=AUTHORITY_MIRROR,
        extraction_method="bs4",
        retrieved_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
        content_hash="h2",
    )
    assert fingerprint_documents([first, second]) == fingerprint_documents([second, first])
    assert fingerprint_documents([first, second]) != fingerprint_documents([first])


def test_fingerprint_includes_source_id_not_just_content() -> None:
    from app.index.store import fingerprint_documents

    base = dict(
        scheme_id="S1",
        url="u",
        title="t",
        source_type="scheme_page",
        authority=AUTHORITY_MIRROR,
        extraction_method="bs4",
        retrieved_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
        content_hash="shared",
    )
    left = Document(source_id="S1_groww", **base)
    right = Document(source_id="S2_groww", **base)
    assert fingerprint_documents([left]) != fingerprint_documents([right])


def test_default_corpus_version_is_content_derived() -> None:
    from app.index.store import default_corpus_version

    version = default_corpus_version()
    assert version.startswith("cv")
    assert version == default_corpus_version()


def test_default_store_derives_corpus_version_from_corpus(tmp_path) -> None:
    from app.index.store import default_corpus_version

    store = ChromaStore(path=tmp_path / "chroma", collection_name="test_collection")
    assert store.corpus_version == default_corpus_version()
    assert store.stored_metadata()["corpus_version"] == default_corpus_version()
    store.assert_corpus_version()
