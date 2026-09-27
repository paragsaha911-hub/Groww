from __future__ import annotations

import argparse
import json

from app import config
from app.index import embed as embed_mod
from app.index import report as report_mod
from app.index import store as store_mod
from app.ingest import fetch as fetch_mod
from app.ingest import parse as parse_mod
from app.ingest import chunk as chunk_mod
from app.models import Chunk, Document


def _scheme_label(source: dict) -> str:
    scheme = config.scheme_by_id(source.get("scheme_id", ""))
    return scheme.name if scheme else source.get("scheme_id", "?")


def _select(args: argparse.Namespace) -> list[dict]:
    sources = list(config.SOURCES)
    if args.scheme:
        sources = [s for s in sources if s.get("scheme_id") in set(args.scheme)]
    if args.authority:
        sources = [s for s in sources if s.get("authority") == args.authority]
    return sources


def stage_fetch(sources: list[dict], force: bool, dry_run: bool) -> dict[str, fetch_mod.FetchResult]:
    results: dict[str, fetch_mod.FetchResult] = {}
    for source in sources:
        if dry_run:
            verdict, reason, status = fetch_mod.robots_verdict(source["url"])
            results[source["source_id"]] = fetch_mod.FetchResult(
                source_id=source["source_id"],
                url=source["url"],
                ok=verdict == fetch_mod.VERDICT_ALLOW,
                reason=f"{reason} (dry-run, not fetched)",
                http_status=status,
                robots_verdict=verdict,
            )
            continue
        results[source["source_id"]] = fetch_mod.fetch_source(source, force=force)
    return results


def stage_parse(
    sources: list[dict], results: dict[str, fetch_mod.FetchResult]
) -> list[tuple[dict, parse_mod.ParsedDocument | None, str]]:
    outcomes = []
    for source in sources:
        result = results.get(source["source_id"])
        if result is None or not result.ok:
            reason = result.reason if result else "not_fetched"
            outcomes.append((source, None, str(reason)))
            continue
        parsed = parse_mod.parse_document(result, source)
        parse_mod.write_outputs(parsed, source)
        outcomes.append((source, parsed, "ok"))
    return outcomes


def report_fetch(sources: list[dict], results: dict[str, fetch_mod.FetchResult]) -> None:
    print(f"{'source_id':26} {'auth':9} {'ok':5} {'reason':22} {'status':7} robots")
    for source in sources:
        result = results[source["source_id"]]
        print(
            f"{result.source_id:26} {source.get('authority', ''):9} "
            f"{str(result.ok):5} {str(result.reason):22} "
            f"{str(result.http_status or '-'):7} {result.robots_verdict}"
        )


def report_parse(outcomes: list[tuple[dict, parse_mod.ParsedDocument | None, str]]) -> None:
    print()
    print(f"{'source_id':26} {'scheme':26} {'complete':9} {'tokens':7} missing_facts")
    incomplete = 0
    for source, parsed, status in outcomes:
        if parsed is None:
            print(f"{source['source_id']:26} {_scheme_label(source)[:25]:26} {'-':9} {'-':7} status={status}")
            incomplete += 1
            continue
        missing = parse_mod.missing_expected_facts(parsed.fields, source)
        flag = "yes" if parsed.is_complete else "NO"
        if not parsed.is_complete:
            incomplete += 1
        print(
            f"{source['source_id']:26} {_scheme_label(source)[:25]:26} {flag:9} "
            f"{parsed_token_count(parsed):7} {','.join(missing) or '-'}"
        )
    print()
    print(f"coverage: {len(outcomes) - incomplete}/{len(outcomes)} complete")
    if incomplete:
        print("INCOMPLETE SOURCES ARE EXCLUDED FROM THE EVALUATION SET (G-9)")


def parsed_token_count(parsed: parse_mod.ParsedDocument) -> int:
    from app.models import approx_token_count

    return approx_token_count(parsed.text)


def corpus_fingerprint(documents: list[Document]) -> str:
    return store_mod.fingerprint_documents(documents)


def stage_chunk(documents: list[Document]) -> list[Chunk]:
    chunker = chunk_mod.get_chunker()
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunker.split(document))
    return chunks


def report_stage_table(counts: dict[str, int | str]) -> None:
    print()
    print("stage summary")
    print(f"{'stage':10} {'fetched':9} {'parsed':8} {'chunks':8} {'vectors':9} {'collection':12}")
    for stage in ("fetch", "parse", "embed", "index"):
        if not any(key.startswith(f"{stage}_") for key in counts):
            continue
        row = [
            str(counts.get(f"{stage}_{key}", "-"))
            for key in ("fetched", "parsed", "chunks", "vectors", "collection")
        ]
        print(f"{stage:10} {row[0]:9} {row[1]:8} {row[2]:8} {row[3]:9} {row[4]:12}")
    if str(counts.get("index_vectors", "")) not in ("", "-"):
        if counts.get("index_vectors") == counts.get("index_collection"):
            print("idempotent: vectors stored equals collection count (no duplicates)")


def stage_index(
    documents: list[Document], corpus_version: str, rebuild: bool, dry_run: bool
) -> tuple[store_mod.ChromaStore, int, int]:
    chunks = stage_chunk(documents)
    if not chunks:
        raise SystemExit(
            "no complete sources to index; run `python -m scripts.ingest --stage parse` first"
        )
    print(f"corpus_version: {corpus_version}")
    print(f"documents={len(documents)} chunks={len(chunks)} chunker={config.CHUNKER}")
    if dry_run:
        return store_mod.ChromaStore(corpus_version=corpus_version), 0, len(chunks)

    store = store_mod.ChromaStore(corpus_version=corpus_version)
    backlog = store.purge()
    if backlog.removed:
        print(f"purged orphan index dirs: {len(backlog.removed)}")
    if backlog.skipped:
        print(f"skipped locked orphan index dirs: {len(backlog.skipped)}")
    if rebuild:
        store.drop()
        print("rebuild: dropped existing collection")
        if store.purged_segments:
            print(f"purged orphan index dirs: {len(store.purged_segments)}")
        if store.skipped_segments:
            print(f"skipped locked orphan index dirs: {len(store.skipped_segments)}")
    else:
        stale = []
        if store.count():
            try:
                store.assert_corpus_version()
            except store_mod.ModelIdentityMismatchError as error:
                stale.append(str(error))
            try:
                store.assert_model_identity()
            except store_mod.ModelIdentityMismatchError as error:
                stale.append(str(error))
        if stale:
            for message in stale:
                print(f"stale index: {message}")
            raise SystemExit("re-run with --rebuild to replace the stale index")

    embedder = embed_mod.MiniLMEmbedder(corpus_version=corpus_version)
    vectors = embedder.encode([chunk.text for chunk in chunks])
    written = store.upsert(chunks, vectors)
    report_mod.write_reports(
        chunks,
        vectors,
        config.PROCESSED_DIR,
        {
            "corpus_version": corpus_version,
            "chunker": config.CHUNKER,
            "chunk_size": config.CHUNK_SIZE,
            "chunk_overlap": config.CHUNK_OVERLAP,
            "embed_model": config.EMBED_MODEL,
            "embed_dim": config.EMBED_DIM,
            "documents": len(documents),
        },
    )
    print(f"reports      : {config.PROCESSED_DIR / 'chunks.txt'}")
    print(f"reports      : {config.PROCESSED_DIR / 'embeddings.txt'}")
    return store, written, len(chunks)


def report_index(store: store_mod.ChromaStore, written: int, chunk_count: int) -> None:
    total = store.count()
    official = len(store.official_chunk_ids())
    identity = store.stored_metadata()
    print()
    print(f"collection     : {store.collection_name}")
    print(f"path           : {store.path}")
    print(f"corpus_version : {identity.get('corpus_version')}")
    print(f"embed_model    : {identity.get('embed_model')}")
    print(f"embed_dim      : {identity.get('embed_dim')}")
    print(f"space          : {identity.get('hnsw:space')}")
    print(f"written        : {written}")
    print(f"total_chunks   : {total}")
    print(f"official_chunks: {official}")
    print(f"mirror_chunks  : {total - official}")
    if total > chunk_count:
        print(
            f"WARNING: {total - chunk_count} chunks in the index are not in the current corpus; "
            "re-run with --rebuild"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest configured sources.")
    parser.add_argument(
        "--stage", choices=["fetch", "parse", "index", "all"], default="all"
    )
    parser.add_argument("--scheme", action="append", help="limit to scheme id, repeatable")
    parser.add_argument("--authority", choices=["official", "mirror"])
    parser.add_argument("--force", action="store_true", help="ignore the content-hash cache")
    parser.add_argument("--dry-run", action="store_true", help="no writes, no network")
    parser.add_argument(
        "--rebuild", action="store_true", help="drop the collection and re-index from scratch"
    )
    args = parser.parse_args()

    config.ensure_dirs()
    sources = _select(args)
    counts: dict[str, int | str] = {}

    if args.stage == "parse":
        results = {s["source_id"]: fetch_mod.FetchResult(
            source_id=s["source_id"], url=s["url"], ok=True, reason="assumed_present"
        ) for s in sources}
        existing = json.loads((config.RAW_DIR / "index.json").read_text(encoding="utf-8")) if (
            config.RAW_DIR / "index.json"
        ).is_file() else {}
        for source_id, payload in existing.items():
            results[source_id] = fetch_mod.FetchResult(**payload)

    if args.stage in ("fetch", "all"):
        results = stage_fetch(sources, args.force, args.dry_run)
        report_fetch(sources, results)
        counts["fetch_fetched"] = sum(1 for r in results.values() if r.ok)
        if not args.dry_run:
            index_path = config.RAW_DIR / "index.json"
            index = {}
            if index_path.is_file():
                try:
                    index = json.loads(index_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    index = {}
            for source_id, result in results.items():
                index[source_id] = {
                    "source_id": result.source_id,
                    "url": result.url,
                    "ok": result.ok,
                    "raw_path": result.raw_path,
                    "content_hash": result.content_hash,
                    "http_status": result.http_status,
                    "reason": result.reason,
                    "retrieved_at": result.retrieved_at.isoformat() if result.retrieved_at else None,
                    "byte_length": result.byte_length,
                    "content_type": result.content_type,
                    "kind": result.kind,
                    "extraction_method": result.extraction_method,
                    "robots_verdict": result.robots_verdict,
                }
            index_path.write_text(
                json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    if args.stage in ("parse", "all") and not args.dry_run:
        outcomes = stage_parse(sources, results)
        report_parse(outcomes)
        counts["parse_parsed"] = sum(1 for _, parsed, _ in outcomes if parsed is not None)

    if args.stage == "index":
        results = {s["source_id"]: fetch_mod.FetchResult(
            source_id=s["source_id"], url=s["url"], ok=True, reason="assumed_present"
        ) for s in sources}

    if args.stage in ("index", "all"):
        corpus = parse_mod.load_corpus(include_incomplete=False)
        if not corpus:
            raise SystemExit(
                "no complete sources to index; run `python -m scripts.ingest --stage parse` first"
            )
        corpus_version = corpus_fingerprint(corpus)
        documents = corpus
        if args.scheme:
            wanted = set(args.scheme)
            documents = [d for d in documents if d.scheme_id in wanted]
        if args.authority:
            documents = [d for d in documents if d.authority == args.authority]
        if not documents:
            raise SystemExit("no sources match the requested filters")
        config.set_corpus_version(corpus_version)
        store, written, chunk_count = stage_index(
            documents, corpus_version, args.rebuild, args.dry_run
        )
        counts["index_vectors"] = written
        counts["embed_vectors"] = written
        if not args.dry_run:
            report_index(store, written, chunk_count)
            counts["index_collection"] = store.count()
            counts["index_chunks"] = chunk_count
            report_stage_table(counts)


if __name__ == "__main__":
    main()
