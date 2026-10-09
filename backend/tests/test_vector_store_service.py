"""
Phase 5 tests: VectorStore abstraction (add/search/delete/update/filter),
run against BOTH backends so the "swappable provider" contract (Rule 10)
is actually enforced by a test, not just claimed in a docstring.

Uses small hand-built vectors (not the real embedding model) so these
tests run fast and offline. Vectors are already unit-length so cosine
similarity comparisons below are exact, not approximate.

Run: pytest backend/tests/test_vector_store_service.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.vector_store_service import (
    ChromaVectorStore,
    FAISSVectorStore,
    VectorRecord,
)

# Two orthogonal-ish unit vectors + one near-duplicate of the first,
# so "nearest neighbour" has an unambiguous right answer.
VEC_A = [1.0, 0.0, 0.0]
VEC_A_NEAR = [0.98, 0.2, 0.0]
VEC_B = [0.0, 1.0, 0.0]


def _sample_records() -> list[VectorRecord]:
    return [
        VectorRecord(
            chunk_id="it_act_66c_001", text="Identity theft under Section 66C.",
            embedding=VEC_A, domain="cyber", document_type="act",
            act_name="Information Technology Act, 2000", section="66C",
            jurisdiction="India", language="en", source="test", year=2000,
        ),
        VectorRecord(
            chunk_id="contract_act_10_001", text="Essentials of a valid contract.",
            embedding=VEC_B, domain="contract", document_type="act",
            act_name="Indian Contract Act, 1872", section="10",
            jurisdiction="India", language="en", source="test", year=1872,
        ),
    ]


def _make_chroma(tmp_path):
    try:
        import chromadb  # noqa: F401
    except ImportError:
        pytest.skip("chromadb not installed")
    return ChromaVectorStore(str(tmp_path / "chroma"))


def _make_faiss(tmp_path):
    try:
        import faiss  # noqa: F401
    except ImportError:
        pytest.skip("faiss-cpu not installed")
    return FAISSVectorStore(str(tmp_path / "faiss"))


BACKEND_FACTORIES = [_make_chroma, _make_faiss]


@pytest.fixture(params=BACKEND_FACTORIES, ids=["chroma", "faiss"])
def store(request, tmp_path):
    factory = request.param
    return factory(tmp_path / request.param.__name__)


def test_add_and_count(store):
    written = store.add(_sample_records())
    assert written == 2
    assert store.count() == 2


def test_search_returns_nearest_first(store):
    store.add(_sample_records())
    results = store.search(VEC_A_NEAR, top_k=2)
    assert len(results) == 2
    assert results[0].chunk_id == "it_act_66c_001"
    assert results[0].score > results[1].score


def test_search_with_domain_filter(store):
    store.add(_sample_records())
    results = store.search(VEC_A_NEAR, top_k=5, where={"domain": "contract"})
    assert len(results) == 1
    assert results[0].chunk_id == "contract_act_10_001"


def test_delete_removes_from_search(store):
    store.add(_sample_records())
    store.delete(["it_act_66c_001"])
    assert store.count() == 1
    results = store.search(VEC_A_NEAR, top_k=5)
    assert all(r.chunk_id != "it_act_66c_001" for r in results)


def test_update_overwrites_text_not_duplicates(store):
    records = _sample_records()
    store.add(records)
    updated = records[0]
    updated.text = "Identity theft under Section 66C (amended)."
    store.update([updated])
    assert store.count() == 2  # still 2, not 3 -- upsert, not duplicate insert
    results = store.search(VEC_A, top_k=1)
    assert "amended" in results[0].text


def test_filter_is_metadata_only_no_vector_math(store):
    store.add(_sample_records())
    matches = store.filter({"domain": "cyber"})
    assert len(matches) == 1
    assert matches[0]["chunk_id"] == "it_act_66c_001"
    assert matches[0]["metadata"]["act_name"] == "Information Technology Act, 2000"


def test_empty_store_search_returns_empty(store):
    assert store.search(VEC_A, top_k=5) == []


def test_add_empty_list_is_noop(store):
    assert store.add([]) == 0
    assert store.count() == 0
