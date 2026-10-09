"""
Phase 7 tests: retrieval_service.py's metadata filtering and reranking.

Run: pytest backend/tests/test_retrieval_service.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.classification_service import classify_query
from backend.app.services.vector_store_service import SearchResult, VectorStore, VectorRecord
from backend.app.services.retrieval_service import build_metadata_filter, rerank, retrieve_candidates


class FakeVectorStore(VectorStore):
    name = "fake"

    def __init__(self, results: list[SearchResult]):
        self._results = results

    def add(self, records: list[VectorRecord]) -> int:
        return len(records)

    def search(self, query_embedding, top_k=10, where=None):
        if where:
            filtered = [r for r in self._results if all(r.metadata.get(k) == v for k, v in where.items())]
            return filtered[:top_k]
        return self._results[:top_k]

    def delete(self, chunk_ids):
        return 0

    def filter(self, where, limit=1000):
        return []

    def count(self):
        return len(self._results)


CONTRACT_RESULT = SearchResult(
    chunk_id="c1", text="Contract text", score=0.70,
    metadata={"act_name": "Indian Contract Act, 1872", "section": "10",
              "domain": "contract", "jurisdiction": "India"},
)
CYBER_RESULT = SearchResult(
    chunk_id="c2", text="Cyber text", score=0.75,
    metadata={"act_name": "IT Act, 2000", "section": "66C",
              "domain": "cyber", "jurisdiction": "India"},
)


def test_build_metadata_filter_uses_domain_when_confident():
    classification = classify_query("What are the essential elements of a valid contract?")
    where = build_metadata_filter(classification)
    assert where == {"domain": "contract"}


def test_build_metadata_filter_none_when_no_domain():
    classification = classify_query("hello there")
    assert build_metadata_filter(classification) is None


def test_retrieve_candidates_falls_back_when_filter_yields_nothing():
    # Domain classified as "contract" but the store only has "cyber" data --
    # filtered search returns nothing, so it must fall back to unfiltered.
    classification = classify_query("What are the essential elements of a valid contract?")
    store = FakeVectorStore([CYBER_RESULT])
    results = retrieve_candidates([1.0, 0.0, 0.0], store, classification, top_k_candidates=10)
    assert results == [CYBER_RESULT]


def test_rerank_promotes_domain_match_over_higher_raw_score():
    # CYBER_RESULT has a higher raw semantic score (0.75 vs 0.70), but
    # the query is clearly about contracts -- reranking should put the
    # domain-matching contract chunk first.
    classification = classify_query("What are the essential elements of a valid contract?")
    ranked = rerank([CYBER_RESULT, CONTRACT_RESULT], classification, top_k_final=2)
    assert ranked[0].chunk_id == "c1"


def test_rerank_respects_top_k_final():
    classification = classify_query("What are the essential elements of a valid contract?")
    ranked = rerank([CYBER_RESULT, CONTRACT_RESULT], classification, top_k_final=1)
    assert len(ranked) == 1
