# Manual test checklist (spec section 55)

Automated coverage (122/122 passing offline, 5 modules needing
pytest/fastapi/chromadb/faiss/sentence-transformers/faster-whisper
skipped in this sandbox — run `pip install -r backend/requirements.txt
&& pytest backend/tests/ -v` on a machine with network access; see
`backend/tests/run_tests.py`) proves the pipeline logic is correct
against fake/in-memory providers. It does NOT prove the real app works
end to end with a real `GEMINI_API_KEY`, a real populated legal corpus,
and a real browser. That's what this checklist is for — do this once
Phase 2's real data collection has actually run and `.env` has a real
`GEMINI_API_KEY`.

Run `uvicorn app.main:app --reload` (from `backend/`) and `npm run dev`
(from `frontend/`), then work through every row.

| # | Check | Status |
|---|-------|--------|
| 1 | English question gets a grounded answer with sources | Not yet run — needs real corpus + `GEMINI_API_KEY` |
| 2 | Kannada question gets a Kannada answer | Not yet run — same |
| 3 | Hindi question gets a Hindi answer | Not yet run — same |
| 4 | Follow-up question resolves context (spec section 20's "What is the punishment?" example) | Not yet run — same |
| 5 | Ambiguous question ("Can I file a case?") returns a clarification, not a guess | Logic verified offline (`test_ambiguity_service.py`, `evaluation/evaluate.py`'s `q_ambiguous_01/02`) — not yet run against the live UI |
| 6 | Contract-law question | Not yet run |
| 7 | Cyber-law question | Not yet run |
| 8 | Property-law question | Not yet run |
| 9 | Consumer-law question | Not yet run |
| 10 | Family-law question | Not yet run |
| 11 | Employment-law question | Not yet run |
| 12 | PDF upload processes and becomes answerable | Pipeline verified offline for `.txt` only (`test_document_service.py`); PDF path (`pypdf`) untested — no network to install it here |
| 13 | DOCX upload processes and becomes answerable | Same caveat — `python-docx` untested here |
| 14 | TXT upload processes and becomes answerable | **Verified for real** (`test_document_service.py`, including a Hindi fixture) |
| 15 | Question about an uploaded document answers from it, and the source card says so | Logic verified offline (`test_rag_service_improved.py`'s document-scoped tests, Phase 14's `source_type` tagging) — not yet run against a live upload |
| 16 | Microphone recording starts/stops in the browser | Frontend code present (`VoiceRecorder.tsx`, `useVoiceRecorder.ts`) — not yet exercised in a real browser from this sandbox |
| 17 | Voice transcription returns real text | `faster-whisper` model load needs `huggingface.co`, outside this sandbox's allowlist (see Phase 13 notes in `PHASES.md`) — the failure path itself IS tested (`test_voice_service.py`), the success path is not |
| 18 | Voice question flows through the same `/api/chat` path as typed | Verified by design/code review (voice transcript is dropped into the same `ChatInput` box) — not yet run live |
| 19 | Source display shows real Act/section/case citations, never fabricated | **Verified for real** (`test_rag_service.py::_build_sources` tests, "never fabricates missing fields" test) |
| 20 | Chat history: new/previous/delete/rename/continue | **Verified for real** against a real temp SQLite file (`test_conversation_repository.py`, 14/14) — not yet run against the live UI |
| 21 | Error handling shows spec section 50's plain-language messages, never a stack trace | Verified for the backend error-mapping paths (`test_voice_api.py`'s status-code tests, `rag_service.py`'s documented error strings) — full frontend error-banner sweep not yet run live |

## How to update this table

Replace each "Not yet run" cell with **PASS** or **FAIL — <what broke>**
as you actually click through the running app. Do not mark a row PASS
without having run it (Rule 4's "no fabricated results" applies to this
checklist too, not just `evaluation/*_results.json`).
