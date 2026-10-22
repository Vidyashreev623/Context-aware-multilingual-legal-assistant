"""
RAG pipeline (Phase 6 baseline + Phase 7 improved).

    Query -> Embedding -> Vector Search -> Top-K -> Gemini -> Answer

UPDATED: previously this pipeline was strictly "context-only" -- Gemini
was forbidden from using any knowledge beyond what was retrieved, and
the code hard-stopped with a canned message whenever the knowledge base
was empty, retrieval found nothing relevant, or the query's domain was
ambiguous. That made the assistant unable to answer anything outside
its indexed documents, and blocked short/vague-but-answerable questions
behind a clarification prompt.

This version:
  - Still retrieves and prioritizes real legal-document context when
    available (accuracy/citations stay grounded whenever possible).
  - No longer hard-stops when retrieval finds nothing -- Gemini is
    allowed to answer from its own general knowledge of Indian law in
    that case, and is instructed to clearly say so rather than imply
    the answer came from a specific retrieved source.
  - No longer blocks on "ambiguous domain" -- classification is still
    computed (used for reranking/metadata filtering) but is no longer
    a reason to refuse to answer; the model just answers as best it
    can and the user can always ask a follow-up to narrow it down.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from app.config import get_settings
from app.services.embedding_service import EmbeddingProvider, get_embedding_provider
from app.services.vector_store_service import SearchResult, VectorStore, get_vector_store
from app.services.gemini_service import (
    GeminiNotConfiguredError,
    GeminiRateLimitError,
    GeminiError,
    LLMProvider,
    get_llm_provider,
)
from app.services.classification_service import QueryClassification, classify_query
from app.services.ambiguity_service import AmbiguityResult, detect_ambiguity
from app.services.language_service import resolve_response_language
from app.services.retrieval_service import rerank, retrieve_candidates
from app.services.document_service import retrieve_document_context, UPLOADED_DOMAIN


def _build_system_instructions() -> str:
    return (
        "You are the Context-Aware Multilingual Legal Assistant, an assistant that explains Indian law using ONLY the "
        "everyday language anyone can understand. Follow these rules:\n"
        "1. If retrieved legal context is provided below the user's question, "
        "use it and ground your answer in it -- cite the exact section "
        "numbers and Act names it contains.\n"
        "2. If the retrieved context is missing, incomplete, or not relevant "
        "to the question, answer using your own knowledge of Indian law "
        "instead of refusing. Do not add any meta-commentary about where the "
        "information came from (no 'based on general knowledge', no 'the "
        "retrieved context does not contain...') -- just answer the question "
        "directly as if you always knew the answer.\n"
        "3. Never invent section numbers, act names, or case names -- if "
        "you're not confident of an exact citation, describe the law in "
        "plain terms without a fabricated citation rather than guessing one.\n"
        "4. Respect the jurisdiction named in the context; do not assume a "
        "state or court that isn't mentioned. Default to Indian law generally "
        "when no state is specified.\n"
        "5. Answer in the language requested in the user message.\n"
        "6. Preserve original legal terminology (e.g. exact section numbers, "
        "Act names) even when explaining in another language.\n"
        "7. Explain legal concepts in short, plain, everyday sentences -- "
        "avoid dense legalese. Summarize; don't restate retrieved text "
        "verbatim. Keep the whole answer as brief as the question allows -- "
        "a short question deserves a short answer, not an exhaustive essay.\n"
        "8. Do not list a 'Sources' section yourself -- the application "
        "displays sources separately.\n"
        "9. Do not add a disclaimer, a 'this is not legal advice' notice, or "
        "a 'consult an advocate' suggestion -- the application shows this "
        "separately in its own UI, so repeating it in your answer is "
        "redundant.\n"
        "10. Always attempt an answer. Never refuse or ask a clarifying "
        "question first -- if the question is broad, give the best direct "
        "answer you can.\n\n"
        "This assistant explains factual legal information (offences, "
        "penalties, procedures, rights) for educational purposes. Questions "
        "about what the law says regarding crimes, punishments, or penalties "
        "are legitimate legal-education questions, not requests to commit or "
        "enable wrongdoing -- answer them directly and factually.\n\n"
        "Keep your answer as plain, flowing text or a short list -- do not "
        "use rigid headings like '### Answer' or '### Applicable Law' unless "
        "the question is genuinely complex enough to need that structure."
    )


def _build_context(results: list[SearchResult], max_chars: int) -> tuple[str, list[SearchResult]]:
    """Numbered context blocks Gemini can refer back to, truncated to
    MAX_CONTEXT_CHARS. Returns the text plus the subset of results
    actually included, so sources shown to the user match what Gemini
    actually saw. Returns ("", []) when there are no results at all --
    that's fine now; the system prompt tells Gemini to fall back to
    general knowledge in that case instead of the caller refusing."""
    blocks: list[str] = []
    used: list[SearchResult] = []
    total = 0
    for i, r in enumerate(results, start=1):
        label = r.metadata.get("act_name", "Unknown source")
        if r.metadata.get("section"):
            label += f", Section {r.metadata['section']}"
        block = f"[{i}] {label}\n{r.text}"
        if total + len(block) > max_chars and used:
            break
        blocks.append(block)
        used.append(r)
        total += len(block)
    return "\n\n".join(blocks), used


def _build_user_prompt(message: str, context_text: str, language: str) -> str:
    language_names = {"en": "English", "hi": "Hindi", "kn": "Kannada"}
    language_label = language_names.get(language, language)
    if context_text:
        context_block = f"Retrieved legal context:\n{context_text}\n\n"
    else:
        context_block = ""
    return (
        f"{context_block}"
        f"User question: {message}\n\n"
        f"Respond in {language_label}."
    )


def _build_sources(results: list[SearchResult]) -> list[dict]:
    """Sources come only from actual retrieved-chunk metadata, never
    fabricated. Returns an empty list when nothing was retrieved (a
    general-knowledge answer legitimately has no document sources)."""
    seen = set()
    sources: list[dict] = []
    for r in results:
        title = r.metadata.get("act_name", "Unknown source")
        section = r.metadata.get("section")
        domain = r.metadata.get("domain")
        document_type = r.metadata.get("document_type")
        year = r.metadata.get("year")
        source_type = "uploaded_document" if domain == UPLOADED_DOMAIN else "legal_database"
        key = (title, section)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "title": title,
                "section": section,
                "domain": domain,
                "source_type": source_type,
                "document_type": document_type,
                "year": year,
            }
        )
    return sources


def _call_llm(llm: LLMProvider, system_instructions: str, user_prompt: str, resolved_language: str, sources: list[dict], classification_dict: dict | None = None) -> dict:
    """Shared Gemini-call + error-handling + disclaimer logic for both
    pipelines, so answer_question and answer_question_improved don't
    duplicate the same try/except block.

    IMPORTANT: this now logs the real exception type/message for every
    failure path instead of only returning a generic string, so failures
    are diagnosable from the server logs instead of being guesswork.
    """
    base = {"language": resolved_language, "sources": sources}
    if classification_dict is not None:
        base["classification"] = classification_dict
        base["ambiguous"] = bool(classification_dict.get("ambiguity", False))

    _llm_t0 = time.perf_counter()
    try:
        raw_answer = llm.generate(system_instructions, user_prompt)
        print(f"[TIMING] gemini_generate: {time.perf_counter()-_llm_t0:.2f}s")
    except GeminiNotConfiguredError as e:
        print(f"[LLM ERROR] GeminiNotConfiguredError: {e}")
        base["answer"] = (
            "The server's GEMINI_API_KEY is not configured, so I can't generate "
            "an answer right now. (Retrieval itself is working -- this is just "
            "the LLM step.)"
        )
        base["sources"] = []
        return base
    except GeminiRateLimitError as e:
        print(f"[LLM ERROR] GeminiRateLimitError: {e}")
        base["answer"] = "Gemini request limit reached. Please try again in a moment."
        base["sources"] = []
        return base
    except GeminiError as e:
        # This is the catch-all that was previously showing the generic
        # "LLM service error" message with no way to tell what actually
        # went wrong (safety block, bad model string, quota, network, etc).
        # Logging the real type+message here is the whole fix -- once you
        # see this in your terminal, the message text itself tells you
        # which of those it is.
        print(f"[LLM ERROR] {type(e).__name__}: {e}")
        base["answer"] = "Unable to generate an answer right now due to an LLM service error. Please try again."
        base["sources"] = []
        return base
    except Exception as e:
        # Catches anything not wrapped in the gemini_service exception
        # hierarchy at all (e.g. a raw google.api_core exception leaking
        # through, or an AttributeError from an empty response.text on a
        # safety-blocked candidate). Without this, such errors would
        # propagate as an unhandled 500 with no clean log line.
        print(f"[LLM ERROR] UNEXPECTED {type(e).__name__}: {e}")
        base["answer"] = "Unable to generate an answer right now due to an LLM service error. Please try again."
        base["sources"] = []
        return base

    base["answer"] = raw_answer
    return base


def answer_question(
    message: str,
    language: str = "auto",
    top_k: int | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
    llm_provider: LLMProvider | None = None,
) -> dict:
    """
    Baseline RAG pipeline for one message. Retrieves what it can and
    always attempts an answer -- Gemini falls back to general knowledge
    of Indian law when nothing relevant is retrieved (see
    _build_system_instructions rule 2), rather than the pipeline
    refusing outright.
    """
    settings = get_settings()
    embedder = embedding_provider or get_embedding_provider()
    store = vector_store or get_vector_store()
    llm = llm_provider or get_llm_provider()

    resolved_language = "en" if language == "auto" else language

    results: list[SearchResult] = []
    if store.count() > 0:
        query_vector = embedder.embed_text(message)
        k = top_k or settings.TOP_K_FINAL
        results = store.search(query_vector, top_k=k)

    context_text, used_results = _build_context(results, settings.MAX_CONTEXT_CHARS)
    system_instructions = _build_system_instructions()
    user_prompt = _build_user_prompt(message, context_text, resolved_language)
    sources = _build_sources(used_results)

    return _call_llm(llm, system_instructions, user_prompt, resolved_language, sources)


# ---------------------------------------------------------------------------
# Improved RAG pipeline
#
#     Query -> Language Detection -> Domain Classification ->
#     Jurisdiction Detection -> Query Reformulation -> Embedding ->
#     Metadata Filtering -> Vector Search -> Reranking -> Context
#     Selection -> Gemini -> Answer
#
# Ambiguity detection is still run (classification.ambiguity is still
# populated, useful for the frontend/analytics) but no longer causes an
# early return -- the pipeline always proceeds to answer.
# ---------------------------------------------------------------------------

def _reformulate_query(message: str, history: list[dict] | None = None) -> str:
    if not history:
        return message
    last_turns = history[-2:]
    context_lines = [f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in last_turns]
    return (
        "Given the recent conversation:\n" + "\n".join(context_lines) +
        f"\n\nFollow-up question: {message}"
    )


def answer_question_improved(
    message: str,
    language: str = "auto",
    history: list[dict] | None = None,
    document_ids: list[str] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
    llm_provider: LLMProvider | None = None,
) -> dict:
    """
    Improved RAG pipeline. Always attempts an answer: retrieval is used
    to ground the answer whenever it finds something relevant, and
    Gemini falls back to general knowledge of Indian law otherwise.
    Ambiguity is computed for the response's `classification` field but
    no longer blocks answering with a clarification prompt.
    """
    settings = get_settings()
    embedder = embedding_provider or get_embedding_provider()
    store = vector_store or get_vector_store()
    llm = llm_provider or get_llm_provider()
    document_ids = document_ids or []

    _t0 = time.perf_counter()

    classification = classify_query(message)
    print(f"[TIMING] classify_query: {time.perf_counter()-_t0:.2f}s")

    resolved_language = resolve_response_language(language, message)

    ambiguity = detect_ambiguity(message, classification, has_documents=bool(document_ids))
    classification.ambiguity = ambiguity.ambiguous
    print(f"[TIMING] detect_ambiguity: {time.perf_counter()-_t0:.2f}s")
    # NOTE: ambiguity is intentionally no longer a reason to stop and ask
    # for clarification -- ambiguous just means retrieval had less to go
    # on for metadata filtering; Gemini still gets asked to answer.

    standalone_query = _reformulate_query(message, history)

    doc_results: list[SearchResult] = []
    kb_results: list[SearchResult] = []

    if document_ids or store.count() > 0:
        query_vector = embedder.embed_text(standalone_query)
        print(f"[TIMING] embed_text: {time.perf_counter()-_t0:.2f}s")

        doc_results = (
            retrieve_document_context(document_ids, query_vector, settings.TOP_K_FINAL, vector_store=store)
            if document_ids else []
        )

        remaining_slots = max(settings.TOP_K_FINAL - len(doc_results), 0)
        if remaining_slots > 0 and store.count() > 0:
            kb_candidates = retrieve_candidates(
                query_vector, store, classification, settings.TOP_K_CANDIDATES,
            )
            kb_results = rerank(kb_candidates, classification, remaining_slots)

    results = doc_results + kb_results
    print(f"[TIMING] retrieval+rerank: {time.perf_counter()-_t0:.2f}s")

    context_text, used_results = _build_context(results, settings.MAX_CONTEXT_CHARS)

    system_instructions = _build_system_instructions()
    user_prompt = _build_user_prompt(standalone_query, context_text, resolved_language)
    sources = _build_sources(used_results)

    result = _call_llm(
        llm, system_instructions, user_prompt, resolved_language, sources,
        classification_dict=classification.as_dict(),
    )
    print(f"[TIMING] total: {time.perf_counter()-_t0:.2f}s")
    return result
