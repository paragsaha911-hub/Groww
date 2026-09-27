from __future__ import annotations

import re
import shutil
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Protocol, runtime_checkable

from app import config
from app.index.embed import model_identity
from app.models import AUTHORITY_OFFICIAL, Chunk, Document, ScoredChunk, as_utc

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
CHROMA_DB_NAME = "chroma.sqlite3"
SEGMENT_DIR_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def live_segment_ids(path: Path) -> set[str] | None:
    database = Path(path) / CHROMA_DB_NAME
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = connection.execute("select id from segments").fetchall()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def _remove_dir(path: Path, attempts: int = 3, delay: float = 0.25) -> bool:
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if attempt == attempts - 1:
                return False
            time.sleep(delay)
    return False


class PurgeResult(NamedTuple):
    removed: list[str]
    skipped: list[str]


def purge_orphan_segments(path: Path) -> PurgeResult:
    path = Path(path)
    if not path.is_dir():
        return PurgeResult([], [])
    live = live_segment_ids(path)
    if live is None:
        return PurgeResult([], [])
    removed: list[str] = []
    skipped: list[str] = []
    for entry in sorted(path.iterdir()):
        if not entry.is_dir() or not SEGMENT_DIR_PATTERN.match(entry.name):
            continue
        if entry.name in live:
            continue
        if _remove_dir(entry):
            removed.append(entry.name)
        else:
            skipped.append(entry.name)
    return PurgeResult(removed, skipped)

CHUNK_METADATA_FIELDS = (
    "chunk_id",
    "source_id",
    "scheme_id",
    "scheme_name",
    "category",
    "section_title",
    "heading_path",
    "ordinal",
    "char_start",
    "char_end",
    "url",
    "retrieved_at",
    "document_date",
    "authority",
    "corpus_version",
    "page",
    "token_count",
)


class ModelIdentityMismatchError(RuntimeError):
    pass


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> int: ...

    def query(
        self, vector: list[float], top_k: int, where: dict[str, Any] | None = None
    ) -> list[ScoredChunk]: ...

    def count(self) -> int: ...

    def drop(self) -> None: ...


def coerce_metadata_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return as_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def chunk_metadata(chunk: Chunk) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in CHUNK_METADATA_FIELDS:
        metadata[field] = coerce_metadata_value(getattr(chunk, field, None))
    if metadata.get("page") == "":
        metadata["page"] = -1
    if not metadata.get("document_date"):
        metadata["document_date"] = ""
    return metadata


def metadata_where(where: dict[str, Any] | None) -> dict[str, Any] | None:
    if not where:
        return None
    coerced = {key: coerce_metadata_value(value) for key, value in where.items()}
    return coerced or None


def chunk_from_metadata(
    source_id: str, metadata: dict[str, Any], document: str, ordinal: int
) -> Chunk:
    page = metadata.get("page")
    document_date = metadata.get("document_date") or None
    return Chunk(
        chunk_id=metadata.get("chunk_id") or "",
        source_id=source_id,
        scheme_id=metadata.get("scheme_id") or "",
        scheme_name=metadata.get("scheme_name") or "",
        category=metadata.get("category") or "",
        section_title=metadata.get("section_title") or "",
        heading_path=metadata.get("heading_path") or "",
        text=document,
        ordinal=int(metadata.get("ordinal") or ordinal),
        char_start=int(metadata.get("char_start") or 0),
        char_end=int(metadata.get("char_end") or 0),
        url=metadata.get("url") or "",
        retrieved_at=as_utc(metadata.get("retrieved_at")) or EPOCH,
        authority=metadata.get("authority") or "",
        corpus_version=metadata.get("corpus_version") or "",
        page=None if page in (None, "", -1, "-1") else int(page),
        token_count=int(metadata.get("token_count") or 0),
        document_date=date.fromisoformat(document_date) if document_date else None,
    )


IDENTITY_METADATA_KEYS = {"model_id": "embed_model", "dim": "embed_dim"}


def identity_metadata(identity: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = identity or model_identity()
    return {stored: identity[key] for key, stored in IDENTITY_METADATA_KEYS.items()}


def fingerprint_documents(documents: Iterable[Document]) -> str:
    return config.corpus_fingerprint(
        [f"{document.source_id}:{document.content_hash}" for document in documents]
    )


def default_corpus_version() -> str:
    try:
        from app.ingest.parse import load_corpus

        documents = load_corpus(include_incomplete=False)
    except (ImportError, OSError, ValueError, KeyError, TypeError):
        return config.corpus_version()
    if not documents:
        return config.corpus_version()
    return fingerprint_documents(documents)


class ChromaStore:
    def __init__(
        self,
        corpus_version: str | None = None,
        collection_name: str | None = None,
        path: Path | None = None,
        client: Any = None,
    ) -> None:
        self.corpus_version = corpus_version or default_corpus_version()
        self.collection_name = collection_name or config.CHROMA_COLLECTION
        self.path = Path(path) if path else config.CHROMA_DIR
        self.path.mkdir(parents=True, exist_ok=True)
        self.purged_segments: list[str] = []
        self.skipped_segments: list[str] = []
        if client is not None:
            self.client = client
        else:
            import chromadb

            self.client = chromadb.PersistentClient(path=str(self.path))
        self.collection = self._collection()

    def _collection(self) -> Any:
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "hnsw:M": config.CHROMA_HNSW_M,
                "hnsw:construction_ef": config.CHROMA_HNSW_CONSTRUCTION_EF,
                "corpus_version": self.corpus_version,
                **identity_metadata(),
            },
        )

    def stored_metadata(self) -> dict[str, Any]:
        return dict(self.collection.metadata or {})

    def assert_model_identity(self) -> None:
        stored = self.stored_metadata()
        mismatches: list[str] = []
        for key, expected in identity_metadata().items():
            actual = stored.get(key)
            if actual != expected:
                mismatches.append(f"{key}: stored {actual!r} != current {expected!r}")
        if mismatches:
            raise ModelIdentityMismatchError(
                "vector index was built with a different embedding model; re-index required. "
                + "; ".join(mismatches)
            )

    def assert_corpus_version(self) -> None:
        stored = self.stored_metadata().get("corpus_version")
        if stored != self.corpus_version:
            raise ModelIdentityMismatchError(
                f"vector index corpus_version {stored!r} != current {self.corpus_version!r}; "
                "re-index required. Run `python -m scripts.ingest --rebuild`."
            )

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"got {len(chunks)} chunks but {len(vectors)} vectors; they must match"
            )
        if not chunks:
            return 0
        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk_metadata(chunk) for chunk in chunks],
            embeddings=[list(vector) for vector in vectors],
        )
        return len(chunks)

    def query(
        self, vector: list[float], top_k: int, where: dict[str, Any] | None = None
    ) -> list[ScoredChunk]:
        self.assert_model_identity()
        if top_k <= 0:
            return []
        result = self.collection.query(
            query_embeddings=[list(vector)],
            n_results=top_k,
            where=metadata_where(where),
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        scored: list[ScoredChunk] = []
        for rank, chunk_id in enumerate(ids, start=1):
            metadata = dict(metadatas[rank - 1] or {})
            similarity = 1.0 - float(distances[rank - 1])
            scored.append(
                ScoredChunk(
                    chunk=chunk_from_metadata(
                        source_id=metadata.get("source_id") or "",
                        metadata=metadata,
                        document=documents[rank - 1] or "",
                        ordinal=rank,
                    ),
                    rank=rank,
                    fused_score=similarity,
                    cosine_score=similarity,
                )
            )
        return scored

    def official_chunk_ids(self) -> set[str]:
        return set(
            self.collection.get(where={"authority": AUTHORITY_OFFICIAL}, include=["metadatas"]).get(
                "ids", []
            )
        )

    def ids(self) -> list[str]:
        return list(self.collection.get(include=["metadatas"]).get("ids", []))

    def count(self) -> int:
        return int(self.collection.count())

    def drop(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except ValueError:
            pass
        self._apply_purge()
        self.collection = self._collection()

    def purge(self) -> PurgeResult:
        self._apply_purge()
        return PurgeResult(list(self.purged_segments), list(self.skipped_segments))

    def _apply_purge(self) -> None:
        result = purge_orphan_segments(self.path)
        self.purged_segments = list(result.removed)
        self.skipped_segments = list(result.skipped)

    def where(self, filters: dict[str, Any]) -> list[str]:
        return list(self.collection.get(where=metadata_where(filters)).get("ids", []))


def build_store(
    chunks: Iterable[Chunk], embedder: Any, store: ChromaStore | None = None
) -> tuple[ChromaStore, int]:
    target = store or ChromaStore()
    chunk_list = list(chunks)
    if not chunk_list:
        return target, 0
    vectors = embedder.encode([chunk.text for chunk in chunk_list])
    return target, target.upsert(chunk_list, vectors)
