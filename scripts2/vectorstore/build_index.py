"""
Builds/updates the vector index from processed chunks + their embeddings
(Phase 5).

Reads:
    data/processed/<domain>/<domain>_all_chunks.jsonl     (Phase 3)
    data/embeddings/<domain>/<domain>_embeddings.jsonl     (Phase 4)
Writes:
    vector_store/chroma/  or  vector_store/faiss/          (Phase 5,
    backend chosen by VECTOR_STORE_BACKEND in .env)

The two input files are joined on chunk_id -- this is the "join the two
files back together" step referenced in generate_embeddings.py's
docstring. A chunk with no matching embedding (or vice versa) is skipped
with a warning rather than silently dropped, since a silent skip would
quietly shrink the knowledge base.

Usage:
    python scripts/vectorstore/build_index.py --domain cyber
    python scripts/vectorstore/build_index.py --all
    python scripts/vectorstore/build_index.py --all --rebuild   # wipe + rebuild from scratch
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.vector_store_service import (
    VectorRecord,
    get_vector_store,
    reset_vector_store_cache,
)
from backend.app.config import get_settings

ALL_DOMAINS = (
    "consumer", "contract", "cyber", "family", "property", "employment",
    "criminal", "constitutional", "corporate", "intellectual_property",
    "taxation", "environmental", "banking",
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _join_domain(domain: str) -> list[VectorRecord]:
    chunks_path = REPO_ROOT / "data" / "processed" / domain / f"{domain}_all_chunks.jsonl"
    embeddings_path = REPO_ROOT / "data" / "embeddings" / domain / f"{domain}_embeddings.jsonl"

    chunks = _read_jsonl(chunks_path)
    embeddings = _read_jsonl(embeddings_path)

    if not chunks:
        print(f"[{domain}] no processed chunks found ({chunks_path}) -- skipping")
        return []
    if not embeddings:
        print(
            f"[{domain}] chunks exist but no embeddings found ({embeddings_path}). "
            f"Run: python scripts/embeddings/generate_embeddings.py --domain {domain}"
        )
        return []

    embedding_by_id = {e["chunk_id"]: e["embedding"] for e in embeddings}

    records: list[VectorRecord] = []
    missing = 0
    for chunk in chunks:
        vec = embedding_by_id.get(chunk["chunk_id"])
        if vec is None:
            missing += 1
            continue
        records.append(VectorRecord(
            chunk_id=chunk["chunk_id"],
            text=chunk["text"],
            embedding=vec,
            domain=chunk.get("domain", domain),
            document_type=chunk.get("document_type"),
            act_name=chunk.get("act_name"),
            section=chunk.get("section"),
            chapter=chunk.get("chapter"),
            jurisdiction=chunk.get("jurisdiction"),
            language=chunk.get("language"),
            source=chunk.get("source"),
            year=chunk.get("year"),
        ))

    if missing:
        print(f"[{domain}] WARNING: {missing} chunk(s) had no matching embedding -- skipped")

    return records


def build_domain(store, domain: str) -> int:
    records = _join_domain(domain)
    if not records:
        return 0
    written = store.add(records)
    print(f"[{domain}] indexed {written} chunk(s)")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/update the legal vector index.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--domain", choices=ALL_DOMAINS, help="Index a single domain")
    group.add_argument("--all", action="store_true", help="Index every domain with chunks+embeddings")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Delete existing entries for the selected domain(s) before adding "
             "(use after re-chunking/re-embedding so stale vectors aren't left behind)",
    )
    args = parser.parse_args()

    domains = ALL_DOMAINS if args.all else [args.domain]

    reset_vector_store_cache()
    store = get_vector_store()
    settings = get_settings()
    print(f"Vector store backend: {store.name}  (dir: {settings.VECTOR_STORE_DIR})")

    if args.rebuild:
        for domain in domains:
            existing = store.filter({"domain": domain}, limit=100_000)
            ids = [e["chunk_id"] for e in existing]
            if ids:
                store.delete(ids)
                print(f"[{domain}] removed {len(ids)} existing chunk(s) before rebuild")

    total = 0
    for domain in domains:
        total += build_domain(store, domain)

    store.persist()
    print(f"\nTotal chunks indexed this run: {total}")
    print(f"Total chunks now in store: {store.count()}")


if __name__ == "__main__":
    main()
