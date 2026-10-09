# ARCHITECTURE

Status: Phases 1-16 built and verified as described in `PHASES.md`
(offline, against fake/in-memory providers where the real backend needs
a network install this sandbox doesn't have). This document describes
the system that actually exists in this codebase today, not an aspiration.

## High-level flow

```
                     USER
                       │
        ┌──────────────┼──────────────┐
        ▼               ▼               ▼
   TEXT INPUT      VOICE INPUT     FILE UPLOAD
   (ChatInput)    (VoiceRecorder)  (FileUploader)
        │               │               │
        └───────────────┼───────────────┘
                         ▼
                 REACT FRONTEND (frontend/)
                         │  fetch, api.ts
                         ▼
                 FASTAPI BACKEND (backend/app/)
                    /api/chat, /api/upload,
                    /api/voice/transcribe,
                    /api/documents, /api/conversations*
                         │
                         ▼
              answer_question_improved()  (rag_service.py)
                         │
       ┌─────────────────┼─────────────────────┐
       ▼                 ▼                     ▼
 language_service  classification_service  ambiguity_service
   (en/hi/kn)      (domain/query-type/       (vague-phrasing +
                    jurisdiction/state/       low-domain-confidence
                    court)                    -> clarifying question,
                                               retrieval skipped)
       └─────────────────┼─────────────────────┘
                         ▼
              embedding_service (query embedding)
                         │
                         ▼
              retrieval_service: domain-filtered
              candidate search + reranking
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
 legal knowledge base chunks      uploaded-document chunks
 (vector_store_service, from      (document_service.py, same
  scripts/vectorstore/            vector index, tagged
  build_index.py)                 domain="uploaded_documents")
        └────────────────┬────────────────┘
                         ▼
                 gemini_service.py
              (LLMProvider abstraction,
               rate-limit retry + response cache)
                         │
                         ▼
              Answer + Sources + classification
                         │
                         ▼
              conversations/messages persisted
              (database/repositories.py, SQLite)
                         │
                         ▼
                 React chat UI renders answer,
                 clarification banner, or source cards
```

## Component map (where each spec-section requirement actually lives)

| Concern | Module |
|---|---|
| Language detection (en/hi/kn) | `backend/app/services/language_service.py` |
| Domain / query-type / jurisdiction / state / court classification | `backend/app/services/classification_service.py` |
| Ambiguity detection + localized clarification text | `backend/app/services/ambiguity_service.py` |
| Query reformulation against conversation history | `rag_service.py::_reformulate_query` |
| Embeddings (multilingual model + swappable dev fallback) | `backend/app/services/embedding_service.py` |
| Vector store (Chroma/FAISS behind one interface) | `backend/app/services/vector_store_service.py` |
| Domain-filtered retrieval + reranking | `backend/app/services/retrieval_service.py` |
| Uploaded-document extraction -> chunk -> embed -> document-scoped retrieval | `backend/app/services/document_service.py` |
| Speech-to-text (swappable provider) | `backend/app/services/voice_service.py` |
| LLM calls (Gemini, swappable) | `backend/app/services/gemini_service.py` |
| Baseline vs improved pipeline orchestration | `backend/app/services/rag_service.py` |
| Conversation/message/document persistence | `backend/app/database/` (SQLite via stdlib `sqlite3`) |
| HTTP API surface | `backend/app/api/*.py` |
| Chat UI | `frontend/src/` |
| Per-domain data collection -> raw -> processed -> embeddings pipeline | `data_collection/`, `data/`, `scripts/` (see `DATASET.md`) |
| Retrieval evaluation (baseline vs improved) | `evaluation/` (see `EVALUATION.md`) |

## Design decisions worth calling out

- **One vector index, not thirteen.** Spec section 42 explicitly allows
  either; a single `legal_chunks` index with a `domain` metadata field
  (filtered via `where={"domain": ...}`) is simpler to keep consistent
  than 13 separate collections, and uploaded documents reuse the exact
  same index/interface (tagged `domain="uploaded_documents"`) rather
  than a parallel storage system.
- **Baseline and improved are two real, separately-callable functions**
  (`answer_question` / `answer_question_improved`), not one pipeline
  with steps toggled by a flag — so Phase 15's evaluation compares two
  genuinely different code paths, not the same path minus some no-ops.
- **Providers are swappable by construction, not by convention.**
  `EmbeddingProvider`, `VectorStore`, `LLMProvider`, `STTProvider` are
  each an ABC with exactly one production implementation registered
  today; every RAG-pipeline test in `backend/tests/` injects a fake
  implementation of one of these instead of hitting a real network
  service, which is also what makes 122 of this project's tests
  runnable with zero installed dependencies (see `PHASES.md`,
  `backend/tests/run_tests.py`).
- **Nothing about a real legal corpus is fabricated.** `data_collection/`
  and `data/raw/` are still empty in this codebase (Rule 3/Rule 12 —
  no invented sources), so `evaluation/` and `MANUAL_TEST_CHECKLIST.md`
  are explicit about which results come from a synthetic fixture versus
  what still needs a real, network-connected run. See `DATASET.md` and
  `EVALUATION.md`.
