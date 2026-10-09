# DATASET

_This document is filled in as the corresponding phase is completed —
see PHASES.md. Writing it now would mean documenting a system that
doesn't exist yet, which the project rules explicitly forbid (no
fabricated content)._

## Processing pipeline (Phase 3 — done)

```
data/raw/<domain>/<acts|cases|sections|rules>/<file>.{pdf,docx,txt}
        │
        ▼  scripts/extraction/extract_any.py
   raw text
        │
        ▼  scripts/cleaning/clean_text.py
   de-hyphenated, header/footer/page-number stripped, whitespace-normalized text
        │
        ▼  scripts/cleaning/normalize_legal_text.py
   unicode/quote/section-marker normalized text
        │
        ▼  scripts/chunking/legal_chunker.py (structure detection)
   Act → Chapter → Section → Subsection → Clause hierarchy
   (falls back to generic paragraph chunking for case law / undstructured text)
        │
        ▼  scripts/chunking/create_chunks.py (schema + chunk_id + validation)
   chunk records matching the spec section 15 schema
        │
        ▼  scripts/processing/process_<domain>.py
   data/processed/<domain>/<acts|cases|...>/<file>.chunks.jsonl
   data/processed/<domain>/<domain>_all_chunks.jsonl  (combined, for Phase 4 embedding)
```

**Metadata provenance (Rule 3 — never fabricate a source):** every raw
file must resolve to real metadata before it is processed, from one of:
1. A `<file>.meta.json` sidecar next to the raw file, or
2. A `verified: true` entry in `data_collection/<domain>/manifest.json`
   whose `document_name` matches the sidecar's `document_name` (or the
   file's stem if there's no sidecar).

A file with neither is **skipped** with a warning — it is never
processed with a guessed act name, jurisdiction, or source URL.

Run `python backend/tests/test_chunking.py`-style checks via
`pytest backend/tests/test_chunking.py -v` (8 tests: structure
detection, the subsection false-positive regression, generic
fallback chunking, schema validation, metadata provenance). Runnable
directly without pytest too: `python backend/tests/test_chunking.py`
returns the same 8/8, per `backend/tests/run_tests.py` (Phase 16).

## Embeddings (Phase 4 — done)

`scripts/embeddings/generate_embeddings.py` reads every domain's
`data/processed/<domain>/<domain>_all_chunks.jsonl`, embeds each
chunk's text via `backend/app/services/embedding_service.py`'s
`EmbeddingProvider` abstraction, and writes vectors alongside chunk
metadata to `data/embeddings/`.

Model: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`
(configurable via `EMBEDDING_MODEL`) — chosen because it supports
English, Hindi, and Kannada in one shared embedding space, so the
legal knowledge base stays in its authoritative source language (almost
always English, since that's the language Indian Acts are published
in) while a Hindi or Kannada query still retrieves it (spec section
17). Needs `pip install sentence-transformers` + a one-time model
download — not runnable in this sandbox (no network egress to
huggingface.co/pypi.org here). A `DeterministicDevFallbackProvider`
(hash-based, NOT semantically meaningful) exists only to exercise the
surrounding batching/storage plumbing offline, gated behind
`ALLOW_DEV_EMBEDDING_FALLBACK` and never used to serve a real answer.

## Vector database (Phase 5 — done)

`scripts/vectorstore/build_index.py` joins Phase 3's chunks with
Phase 4's embeddings (on `chunk_id`) and loads them into one shared
`legal_chunks` index (spec section 42 explicitly allows one index with
metadata filters instead of 13 separate collections — chosen for
consistency; `domain` is just another metadata field). Backend is
Chroma by default, FAISS as an alternative, both behind the
`VectorStore` interface in `vector_store_service.py` (Rule 10) so
nothing outside that one file imports `chromadb`/`faiss` directly.
`scripts/vectorstore/query_index.py` is a manual smoke-test CLI.

## Current corpus size

`data/raw/` and `data_collection/*/collected/` are still empty in this
codebase — Rule 3/Rule 12 forbid fabricating sources, and this sandbox
has no network access to actually fetch real Acts, rules, or judgments.
The per-domain `data_collection/<domain>/sources.md` files list which
real sources to collect from; nothing has been downloaded yet. Phase 15's
evaluation therefore runs against a small hand-written fixture corpus
instead (`evaluation/fixture_corpus.py`) — see `EVALUATION.md` for what
that means for the reported numbers, and re-run Phase 2 for real (on a
machine with network access) before treating this as a populated legal
knowledge base.
