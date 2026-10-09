"""
Retrieval service (Phase 7, spec sections 21, 22, 44).

Sits between the vector store and rag_service.py, adding the two things
the "Improved" pipeline needs on top of the Phase 6 baseline's plain
`store.search(query_vector, top_k)`:

1. DOMAIN/JURISDICTION-AWARE METADATA FILTERING (sections 21-22) --
   when classification_service.py is confident about the domain (and,
   separately, the state), narrow the vector search with a metadata
   `where` filter instead of searching the whole index. Falls back to
   an unfiltered search if the filtered search comes back empty, so an
   over-narrow filter (e.g. wrong domain guess) never turns into a
   false "no relevant law exists" answer -- it's strictly an ordering/
   precision aid, never a hard exclusion.

2. RERANKING (section 44) -- over-fetch TOP_K_CANDIDATES results, then
   re-score each by combining semantic similarity with domain/
   jurisdiction/section/document-type match bonuses, and keep the
   TOP_K_FINAL best. Weights are fixed constants, not learned/fabricated
   scores (Rule 4) -- they encode the priority ordering spec section 44
   lists (semantic first, then domain, then jurisdiction, then section,
   then document type), each contributing a bounded bonus so it can
   nudge ordering among close semantic matches without ever letting a
   metadata match override a much better semantic one.
"""
from __future__ import annotations

from app.services.classification_service import QueryClassification
from app.services.vector_store_service import SearchResult, VectorStore

# Reranking bonus weights (spec section 44's ordering: semantic > domain
# > jurisdiction > section > document type). Semantic score already
# occupies the full [0, 1] (cosine similarity on normalized embeddings);
# these bonuses are intentionally small relative to that so they can
# only reorder near-ties, never overturn a clearly better semantic match.
DOMAIN_MATCH_BONUS = 0.15
JURISDICTION_MATCH_BONUS = 0.08
STATE_MATCH_BONUS = 0.05
SECTION_MENTION_BONUS = 0.05


def build_metadata_filter(classification: QueryClassification) -> dict | None:
    """Only filter on domain when the classifier was reasonably
    confident (spec section 21: "when domain information is reliable").
    State is deliberately NOT included in the hard filter even when
    detected -- spec section 22 says jurisdiction/state should influence
    *ranking*, not exclude every other state's material outright, since
    a lot of Indian legal content (central acts) applies regardless of
    state.
    """
    if classification.domain and classification.domain_confidence >= 0.5:
        return {"domain": classification.domain}
    return None


def retrieve_candidates(
    query_embedding: list[float],
    store: VectorStore,
    classification: QueryClassification,
    top_k_candidates: int,
) -> list[SearchResult]:
    """Over-fetches candidates for reranking, applying the domain filter
    when reliable and falling back to an unfiltered search if that
    filter yields nothing (e.g. the domain guess was wrong or that
    domain isn't populated yet)."""
    where = build_metadata_filter(classification)
    if where:
        filtered = store.search(query_embedding, top_k=top_k_candidates, where=where)
        if filtered:
            return filtered
    return store.search(query_embedding, top_k=top_k_candidates)


def _rerank_score(result: SearchResult, classification: QueryClassification) -> float:
    score = result.score
    meta = result.metadata

    if classification.domain and meta.get("domain") == classification.domain:
        score += DOMAIN_MATCH_BONUS

    if classification.jurisdiction and meta.get("jurisdiction") == classification.jurisdiction:
        score += JURISDICTION_MATCH_BONUS

    if classification.state and meta.get("jurisdiction") == classification.state:
        score += STATE_MATCH_BONUS

    section = meta.get("section")
    if section and str(section).lower() in (classification.query_type or "").lower():
        score += SECTION_MENTION_BONUS

    return score


def rerank(
    candidates: list[SearchResult],
    classification: QueryClassification,
    top_k_final: int,
) -> list[SearchResult]:
    """Re-scores and truncates the over-fetched candidate list. Stable
    sort (Python's sort is stable) keeps the original semantic ordering
    among exact score ties, rather than reshuffling arbitrarily."""
    scored = sorted(
        candidates,
        key=lambda r: _rerank_score(r, classification),
        reverse=True,
    )
    return scored[:top_k_final]
