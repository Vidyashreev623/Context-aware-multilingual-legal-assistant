# RAG_PIPELINE

Status: Phases 1-16 complete (see `PHASES.md`). This document reflects
`rag_service.py` as it exists today, including document context
(Phase 12), full multilingual query understanding (Phase 11), and
conversation-history-driven query reformulation (Phase 10) — the
"not yet implemented" caveats below from earlier phases have been
resolved and are kept only as history of what changed.

## Baseline pipeline (Phase 6)

```
Query -> Embedding -> Vector Search (top-K) -> Gemini -> Answer
```

Implemented in `backend/app/services/rag_service.py::answer_question()`.
No language/domain/jurisdiction/ambiguity handling, no reranking. Exists
specifically so Phase 15's evaluation has a real, simpler pipeline to
compare the improved one against — not a stub.

## Improved pipeline (Phase 7)

```
Query
  -> Language Detection        (language_service.py)
  -> Domain / Query-Type /
     Jurisdiction Classification (classification_service.py)
  -> Ambiguity Detection        (ambiguity_service.py)
       -> if ambiguous: return clarifying question, skip retrieval
  -> Query Reformulation        (rag_service._reformulate_query --
                                  activates once real conversation
                                  history exists, Phase 10)
  -> Embedding
  -> Metadata-filtered candidate retrieval (retrieval_service.py):
       filters on domain when the classifier is confident (>=0.5),
       falls back to an unfiltered search if that filter returns nothing
  -> Reranking (retrieval_service.rerank): semantic score + domain/
     jurisdiction/state/section match bonuses, spec section 44's stated
     priority order
  -> Document context merge (Phase 12): if document_ids are attached,
     document-scoped chunks fill context slots first, legal-KB results
     (still domain-filtered/reranked) fill the rest
  -> Context Selection (character-budget truncation, same as baseline)
  -> Gemini
  -> Answer + Sources (each tagged source_type + document_type + year,
     Phase 14) + classification metadata
```

Implemented in `rag_service.py::answer_question_improved()`, wired to
`POST /api/chat` (Phase 8), with conversation persistence (Phase 10)
and document context (Phase 12) both live.

### Multilingual query understanding (Phase 11)

Phase 7 shipped English-only domain/query-type/jurisdiction keyword
tables, with `ambiguity_service.py` explicitly exempting non-English
queries from the low-confidence ambiguity check as a documented
stopgap. Phase 11 closed that gap: `classification_service.py` has
real Hindi (Devanagari) and Kannada keyword tables for all 13 domains,
per-language query-type patterns, and Hindi/Kannada state/court
detection; `classify_query` dispatches by detected language. The
non-English ambiguity carve-out is removed, and the clarification
question itself (spec section 23) is localized per response language
(`CLARIFICATION_TEXT["en"/"hi"/"kn"]`) rather than always English.

Remaining, documented gap: `ambiguity_service.py`'s *vague-phrasing*
regexes (signal 1, e.g. "can I file a case?") are still English-only —
a vague Hindi/Kannada query is still caught by signal 2 (low domain
confidence) in the common case, but a vague query that happens to also
contain a domain keyword could slip through signal 1 specifically.

### Voice input (Phase 13)

`voice_service.py`'s `STTProvider` abstraction wraps `faster-whisper`
(multilingual, covers en/hi/kn with one model). The frontend posts a
real `audio/webm` blob to `/api/voice/transcribe`, and the returned
transcript is dropped into the same text box a typed question goes
through — voice questions ride the exact same `/api/chat` path
(history, document attachments, language resolution) as typed ones,
with no separate voice-only pipeline to keep in sync (Rule 9).

### Known limitations, honestly stated

- **Domain classification is keyword-based**, not a trained classifier
  (no labeled Indian-legal-query dataset exists to train one on for
  this project, and Rule 4 forbids fabricated evaluation numbers for a
  model that was never really evaluated).
- **Confidence scores are keyword-hit ratios**, not calibrated
  probabilities. They're useful as a relative signal (this query
  matched one domain's keywords much more than any other) but should
  not be read as "94% sure."
- **Retrieval evaluation (Phase 15) currently runs against a synthetic
  fixture corpus**, not the real legal knowledge base — `data/raw/` is
  still empty (no network to actually collect real Acts/judgments in
  this sandbox). See `EVALUATION.md` for exact numbers and what to
  re-run once real data exists.
- **The real embedding model, real vector-store backends
  (Chroma/FAISS), Gemini calls, and `faster-whisper` model loading are
  all unverified end-to-end in this sandbox** — each needs a `pip
  install` and/or model download over a network this sandbox's egress
  allowlist doesn't cover. Every pipeline *around* them is verified for
  real via dependency injection (fake providers), per `PHASES.md`.
  `MANUAL_TEST_CHECKLIST.md` tracks what still needs a live run.
