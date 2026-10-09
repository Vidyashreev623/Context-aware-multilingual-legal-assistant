# NyayaAI — Context-Aware Multilingual Indian Legal Assistant

A RAG-based legal assistant for Indian law, supporting English, Hindi, and
Kannada, with text/voice/document input and Gemini-generated, source-grounded
answers.

**Status: Phases 1-16 complete** (project setup through automated
testing) — see `PHASES.md` for what each phase built and how it was
verified. **Phase 17 (this commit): documentation.** The one thing not
done yet is Phase 2's *real* data collection (fetching actual Acts/
judgments) and the network-dependent installs (`sentence-transformers`,
`chromadb`/`faiss-cpu`, `faster-whisper`, `google-generativeai`,
`fastapi`, `pytest`) — this sandbox has no network egress to do either,
so every piece of RAG-pipeline logic is verified offline via dependency
injection (fake providers) instead. See `MANUAL_TEST_CHECKLIST.md` for
exactly what to run, for real, once you have network access and a
`GEMINI_API_KEY`.

## Project layout

```
nyaya-ai/
├── data_collection/   # per-domain source lists + raw downloads (Phase 2)
├── data/              # raw/ processed/ embeddings/, per legal domain (Phase 2-5)
├── scripts/           # extraction, cleaning, chunking, embeddings, vectorstore
├── backend/           # FastAPI app (RAG, Gemini, DB, APIs) + tests/
├── frontend/          # React + TypeScript + Vite chat UI
├── vector_store/      # Chroma/FAISS index files (gitignored, built by scripts/vectorstore)
├── uploads/            # user-uploaded documents (gitignored)
└── evaluation/         # retrieval evaluation harness + results (Phase 15)
```

Also see: `ARCHITECTURE.md` (system design), `RAG_PIPELINE.md` (baseline
vs improved pipeline detail), `DATASET.md` (collection -> processing ->
embeddings -> vector store), `EVALUATION.md` (Phase 15 methodology +
results), `API_DOCUMENTATION.md` (every endpoint), `RULES.md`
(non-negotiable implementation rules), `PHASES.md` (build log).

## Running locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set GEMINI_API_KEY, and adjust VECTOR_STORE_BACKEND/
# EMBEDDING_MODEL/STT_MODEL_SIZE if you want non-default providers
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for the interactive API docs, or
http://localhost:8000/api/health for a liveness check.

Run the test suite:

```bash
pytest backend/tests/ -v                      # full suite (needs network for deps)
python backend/tests/run_tests.py             # dependency-free subset, no install needed
```

### Data pipeline (once you have real sources)

```bash
# 1. Collect (see data_collection/<domain>/sources.md for what to fetch)
python scripts/collection/collect_cyber.py         # per domain

# 2. Process (extraction -> cleaning -> structure detection -> chunking -> metadata)
python scripts/processing/process_cyber.py         # per domain

# 3. Embed
python scripts/embeddings/generate_embeddings.py

# 4. Build the vector index
python scripts/vectorstore/build_index.py

# 5. Evaluate retrieval
python evaluation/evaluate.py
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Visit http://localhost:5173.

## Current capabilities

- Real end-to-end RAG: language detection -> domain/query-type/
  jurisdiction classification -> ambiguity detection -> query
  reformulation against conversation history -> domain-filtered
  retrieval -> reranking -> Gemini -> grounded, sourced answer.
- English, Hindi, and Kannada supported at every stage: query
  understanding, retrieval (shared multilingual embedding space), and
  response language.
- File upload (PDF/DOCX/TXT) is processed through the same
  extraction/chunking/embedding pipeline as the legal knowledge base,
  and questions can be answered from an uploaded document, the legal
  knowledge base, or both — with each source clearly labeled.
- Voice input: browser microphone -> `faster-whisper` transcription ->
  the same chat pipeline a typed question uses.
- Real conversation history: new/previous/rename/delete/continue, backed
  by SQLite.
- Source citations always come from actual retrieved-chunk metadata —
  never fabricated (see `RULES.md`).
- Retrieval evaluation harness (Precision@K, Recall@K, MRR, Hit Rate,
  baseline vs improved, multilingual parity) — currently run against a
  synthetic fixture corpus since real data hasn't been collected in
  this sandbox yet; see `EVALUATION.md`.
- 122 backend tests passing with zero installed dependencies
  (`backend/tests/run_tests.py`); 5 more test files need
  `pytest`/`fastapi`/`chromadb`/`faiss`/`sentence-transformers`/
  `faster-whisper` installed to run (see `PHASES.md`).

## What's still needed before a real demo

1. Real data collection (Phase 2) — this repo's `data_collection/` and
   `data/raw/` are intentionally empty; no sources are fabricated.
2. Install the real providers (`pip install -r backend/requirements.txt`
   with network access) and set a real `GEMINI_API_KEY`.
3. Work through `MANUAL_TEST_CHECKLIST.md` against the live app.
4. Re-run `evaluation/evaluate.py` against the real, populated corpus
   and update `EVALUATION.md`'s numbers.

## Roadmap

See `PHASES.md` for the full 17-phase build log — each phase was
delivered and verified (per that phase's own testing constraints)
before the next began.
