"""
Generates embeddings for processed legal chunks (Phase 4).

Reads:  data/processed/<domain>/<domain>_all_chunks.jsonl   (from Phase 3)
Writes: data/embeddings/<domain>/<domain>_embeddings.jsonl

Each output record is:
    {
      "chunk_id": "...",
      "domain": "...",
      "embedding_model": "...",
      "dimension": 768,
      "embedding": [0.0123, -0.045, ...]
    }

Kept separate from data/processed/ (rather than bolted onto the chunk
records) so re-embedding with a different model never touches the
chunk/metadata pipeline, and vice versa — Phase 5's vector-store build
step is the only thing that needs to join the two files back together
(on chunk_id).

Usage:
    python scripts/embeddings/generate_embeddings.py --domain cyber
    python scripts/embeddings/generate_embeddings.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.embedding_service import get_embedding_provider

ALL_DOMAINS = (
    "consumer", "contract", "cyber", "family", "property", "employment",
    "criminal", "constitutional", "corporate", "intellectual_property",
    "taxation", "environmental", "banking",
)

BATCH_SIZE = 32


def _read_chunks(domain: str) -> list[dict]:
    chunks_path = REPO_ROOT / "data" / "processed" / domain / f"{domain}_all_chunks.jsonl"
    if not chunks_path.exists():
        return []
    chunks = []
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def embed_domain(domain: str) -> int:
    chunks = _read_chunks(domain)
    if not chunks:
        print(f"[{domain}] no processed chunks found (run scripts/processing/process_{domain}.py first) — skipping")
        return 0

    provider = get_embedding_provider()
    out_dir = REPO_ROOT / "data" / "embeddings" / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{domain}_embeddings.jsonl"

    written = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start:start + BATCH_SIZE]
            texts = [c["text"] for c in batch]
            vectors = provider.embed_batch(texts)
            for chunk, vector in zip(batch, vectors):
                record = {
                    "chunk_id": chunk["chunk_id"],
                    "domain": domain,
                    "embedding_model": provider.name,
                    "dimension": len(vector),
                    "embedding": vector,
                }
                out_f.write(json.dumps(record) + "\n")
                written += 1

    print(f"[{domain}] embedded {written} chunk(s) with '{provider.name}' -> {out_path}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate embeddings for processed legal chunks.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--domain", choices=ALL_DOMAINS, help="Embed a single domain")
    group.add_argument("--all", action="store_true", help="Embed every domain that has processed chunks")
    args = parser.parse_args()

    domains = ALL_DOMAINS if args.all else [args.domain]
    total = 0
    for domain in domains:
        total += embed_domain(domain)
    print(f"\nTotal chunks embedded: {total}")


if __name__ == "__main__":
    main()
