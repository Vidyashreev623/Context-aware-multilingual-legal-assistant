"""
Manual smoke-test for Phase 5: embed a query and print the top-K matches
from the vector store, so you can eyeball "does this query retrieve the
relevant legal section" before the full RAG pipeline (Phase 6/7) exists.

This is NOT the retrieval evaluation harness (that's Phase 15 --
scripts/evaluation/evaluate_retrieval.py, with Precision@K/Recall@K/MRR
against a labeled question set). This script is just for eyeballing one
query at a time while building/debugging the index.

Usage:
    python scripts/vectorstore/query_index.py "What is Section 66C?"
    python scripts/vectorstore/query_index.py "What is Section 66C?" --domain cyber --top-k 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.embedding_service import get_embedding_provider
from backend.app.services.vector_store_service import get_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the legal vector index directly.")
    parser.add_argument("query", help="Question text, e.g. 'What is Section 66C?'")
    parser.add_argument("--domain", default=None, help="Restrict to one domain, e.g. cyber")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    provider = get_embedding_provider()
    store = get_vector_store()

    if store.count() == 0:
        print(
            "Vector store is empty. Build it first:\n"
            "  python scripts/vectorstore/build_index.py --all"
        )
        return

    query_vector = provider.embed_text(args.query)
    where = {"domain": args.domain} if args.domain else None
    results = store.search(query_vector, top_k=args.top_k, where=where)

    print(f"Query: {args.query}")
    print(f"Backend: {store.name}  |  Total chunks in store: {store.count()}\n")

    if not results:
        print("No results.")
        return

    for i, r in enumerate(results, start=1):
        meta = r.metadata
        label = meta.get("act_name", "?")
        if meta.get("section"):
            label += f" — Section {meta['section']}"
        print(f"{i}. [{r.score:.3f}] {label}  (domain={meta.get('domain')})")
        snippet = r.text[:160].replace("\n", " ")
        print(f"   {snippet}{'...' if len(r.text) > 160 else ''}\n")


if __name__ == "__main__":
    main()
