# API_DOCUMENTATION

Status: Phases 1-16 complete. Every endpoint in spec section 39 is now
wired to real logic (no stubs remain) — see `PHASES.md` for which
phase built each one, and `MANUAL_TEST_CHECKLIST.md` for what still
needs a live run with a real `GEMINI_API_KEY` and populated corpus.

Base URL: `http://localhost:8000/api` (see `backend/app/main.py`).
Interactive docs at `/docs` once the backend is running.

## GET /health

Liveness check. `{"status": "ok"}`.

## POST /chat

Runs the Phase 7 improved RAG pipeline (`rag_service.answer_question_improved`,
see `RAG_PIPELINE.md`), with real conversation persistence (Phase 10)
and document context (Phase 12).

**Request**

```json
{
  "conversation_id": "123",
  "message": "What is Section 66C?",
  "language": "auto",
  "document_ids": []
}
```

- `conversation_id`: omit/`null` to start a new conversation (one is
  created and returned); pass an existing id to continue it — prior
  turns (up to `MAX_HISTORY_TURNS`) are loaded and used for query
  reformulation (spec section 20).
- `language`: `"auto"` (detect from the message) | `"en"` | `"hi"` | `"kn"`.
- `document_ids`: ids of previously-uploaded documents (from `POST
  /upload`) to answer from, alongside or instead of the legal
  knowledge base (spec section 31).

**Response**

```json
{
  "answer": "### Answer\n...",
  "language": "en",
  "sources": [
    {
      "title": "Information Technology Act, 2000",
      "section": "66C",
      "domain": "cyber",
      "source_type": "legal_database",
      "document_type": "act",
      "year": 2000
    }
  ],
  "conversation_id": "123",
  "classification": {
    "language": "en",
    "domain": "cyber",
    "jurisdiction": "India",
    "state": null,
    "court": null,
    "query_type": "section_lookup",
    "ambiguity": false,
    "confidence": 1.0
  },
  "ambiguous": false
}
```

- `source_type`: `"legal_database"` | `"uploaded_document"` (spec
  section 31's "clearly identify" requirement).
- `document_type`: `"act"` | `"case"` | `"rule"` | `null` — a case-law
  source shows `"title — year"` on the frontend, never a section it
  doesn't have (spec section 27/28).
- If the question is judged ambiguous (spec section 23), `ambiguous`
  is `true`, `answer` holds a localized clarifying question (en/hi/kn)
  instead of a legal answer, and `sources` is empty — no retrieval or
  Gemini call happens in that case.

## POST /upload

Runs the full extraction -> cleaning -> chunking -> embedding ->
vector-indexing pipeline synchronously (Phase 12), reusing the exact
Phase 3-5 processing code.

**Request**: `multipart/form-data`, field `file` — PDF/DOCX/TXT (spec
section 29), size/type validated against `ALLOWED_UPLOAD_EXTENSIONS`/
`MAX_UPLOAD_MB`.

**Response** (success)

```json
{
  "document_id": "…",
  "filename": "rental_agreement.pdf",
  "file_type": "pdf",
  "status": "processed",
  "language": "en",
  "chunk_count": 14
}
```

On failure the document row is kept with `status="failed"` and a
user-safe message (never a stack trace, spec section 50) — `400` for
type/size validation, `422` for extraction/processing failure, `500`
for anything unexpected.

## GET /documents

Lists every uploaded document's status. `list[DocumentOut]`: `document_id`,
`filename`, `file_type`, `status` (`"processing"` | `"processed"` |
`"failed"`), `language`, `chunk_count`, `error`, `uploaded_at`.

## DELETE /documents/{document_id}

Removes the document's vector-store chunks, its stored file, and its
DB row. `404` if the id doesn't exist.

## POST /voice/transcribe

**Request**: `multipart/form-data`, field `audio` — `audio/webm` (or
another allowed type), size/type validated. Saved to a private temp
dir (never the permanent `uploads/`), transcribed, always cleaned up
(`finally`, spec section 51).

**Response**: `{"text": "...", "language": "en"}` — the frontend drops
`text` into the same chat input a typed question uses, so it flows
through `POST /chat` exactly like typed input (spec section 32,
Rule 9).

Errors: `503` if the STT model can't be reached/loaded
(`STTNotAvailableError`), `422` if transcription itself fails
(`STTTranscriptionError`), `500` for anything unexpected — never a raw
stack trace.

## Conversations (Phase 10, spec sections 37/39)

- `GET /conversations` -> `list[ConversationSummary]` (`conversation_id`,
  `title`, `updated_at`), ordered by recency.
- `GET /conversations/{id}` -> `ConversationDetail` (`conversation_id`,
  `title`, `messages: list[MessageOut]`) or `404`.
- `POST /conversations` -> creates and returns a new empty conversation.
- `PATCH /conversations/{id}` with `{"title": "..."}` -> renames it
  (freezes auto-derived-from-first-message titling) or `404`.
- `DELETE /conversations/{id}` -> deletes it and cascades its messages
  (`ON DELETE CASCADE`) or `404`.

`MessageOut` carries `id`, `role`, `content`, `language`, `sources`
(the same shape `POST /chat` returns), `classification`, `ambiguous`,
`timestamp` — so re-opening a past conversation renders identically to
how it looked live.

## Error format (spec section 50)

Every endpoint above raises `HTTPException` with a plain-language
`detail` string on failure — no Python stack trace is ever returned to
the client. See each endpoint's error codes above for the specific
mapping.
