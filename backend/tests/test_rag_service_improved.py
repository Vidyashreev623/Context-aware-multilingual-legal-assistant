"""
Phase 7 tests: rag_service.py's improved pipeline (answer_question_improved) --
language/domain/jurisdiction/ambiguity detection, reformulation hook,
metadata filtering, reranking -- on top of the same Gemini/vector-store
plumbing test_rag_service.py already covers for the baseline.

Run: pytest backend/tests/test_rag_service_improved.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.embedding_service import EmbeddingProvider
from backend.app.services.vector_store_service import SearchResult, VectorStore, VectorRecord
from backend.app.services.gemini_service import LLMProvider
from backend.app.services.rag_service import NO_KB_MESSAGE, answer_question_improved


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "fake"

    @property
    def dimension(self) -> int:
        return 3

    def embed_batch(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeVectorStore(VectorStore):
    name = "fake"

    def __init__(self, results: list[SearchResult]):
        self._results = results

    def add(self, records):
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


class FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, response: str = "This is a test answer. Not legal advice."):
        self._response = response

    def generate(self, system_instructions, user_message):
        return self._response


CONTRACT_RESULT = SearchResult(
    chunk_id="c1", text="A contract requires offer, acceptance, and consideration.",
    score=0.70,
    metadata={"act_name": "Indian Contract Act, 1872", "section": "10",
              "domain": "contract", "jurisdiction": "India"},
)
CYBER_RESULT = SearchResult(
    chunk_id="c2", text="Identity theft is punishable under Section 66C.",
    score=0.75,
    metadata={"act_name": "Information Technology Act, 2000", "section": "66C",
              "domain": "cyber", "jurisdiction": "India"},
)


def test_ambiguous_query_short_circuits_before_retrieval():
    result = answer_question_improved(
        "Can I file a case?",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore([CONTRACT_RESULT, CYBER_RESULT]),
        llm_provider=FakeLLMProvider(),
    )
    assert result["ambiguous"] is True
    assert result["sources"] == []
    assert "specify" in result["answer"].lower()


def test_empty_knowledge_base_message_unchanged_from_baseline():
    result = answer_question_improved(
        "What are the essential elements of a valid contract?",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore([]),
        llm_provider=FakeLLMProvider(),
    )
    assert result["answer"] == NO_KB_MESSAGE


def test_domain_classification_reranks_correctly_matched_chunk_first():
    result = answer_question_improved(
        "What are the essential elements of a valid contract?",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore([CYBER_RESULT, CONTRACT_RESULT]),
        llm_provider=FakeLLMProvider(),
    )
    assert result["classification"]["domain"] == "contract"
    assert result["sources"][0]["title"] == "Indian Contract Act, 1872"


def test_classification_shape_present_on_happy_path():
    result = answer_question_improved(
        "What is Section 66C?",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore([CYBER_RESULT]),
        llm_provider=FakeLLMProvider(),
    )
    assert result["ambiguous"] is False
    c = result["classification"]
    assert set(c.keys()) == {
        "language", "domain", "jurisdiction", "state", "court",
        "query_type", "ambiguity", "confidence",
    }


# --- Phase 14: document_ids + legal-KB source merging (spec section 31) ---

UPLOADED_RESULT = SearchResult(
    chunk_id="doc1_001", text="The notice period under this agreement is 30 days.",
    score=0.60,
    metadata={
        "act_name": "rental_agreement.pdf", "section": None,
        "domain": "uploaded_documents", "document_type": "uploaded_document",
        "document_id": "doc1",
    },
)


def test_document_ids_uses_the_injected_vector_store_not_a_second_real_one():
    """Regression test for the Phase 14 bug fix: retrieve_document_context
    must be called with the SAME (possibly fake, DI'd) store this
    function already resolved -- previously it silently called
    get_vector_store() again on its own, so a test-injected FakeVectorStore
    was never actually consulted for document-scoped retrieval. Passing
    document_ids against a FakeVectorStore that only knows about
    UPLOADED_RESULT (no real Chroma/FAISS involved at all) is exactly what
    would have failed/misbehaved before the fix."""
    result = answer_question_improved(
        "What is the notice period in this agreement?",
        document_ids=["doc1"],
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore([UPLOADED_RESULT]),
        llm_provider=FakeLLMProvider(),
    )
    assert result["sources"]
    assert result["sources"][0]["source_type"] == "uploaded_document"
    assert result["sources"][0]["title"] == "rental_agreement.pdf"


def test_document_and_legal_kb_sources_both_present_and_correctly_typed():
    """Spec section 31: 'Uploaded Document + Indian Legal Database ->
    Gemini' -- when both have relevant content, the returned sources
    must include both, each correctly labeled."""
    result = answer_question_improved(
        "What does the law say about notice periods, and what does my agreement say?",
        document_ids=["doc1"],
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore([UPLOADED_RESULT, CONTRACT_RESULT]),
        llm_provider=FakeLLMProvider(),
    )
    source_types = {s["source_type"] for s in result["sources"]}
    assert "uploaded_document" in source_types
    assert "legal_database" in source_types


def test_document_scoped_answer_works_even_with_empty_legal_kb():
    """Spec section 12/31: a fresh install with an empty legal KB should
    still be able to answer purely from an uploaded document -- the
    store.count()==0 short-circuit must not fire when documents are
    attached."""
    result = answer_question_improved(
        "What is the notice period in this agreement?",
        document_ids=["doc1"],
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeVectorStore([UPLOADED_RESULT]),
        llm_provider=FakeLLMProvider(),
    )
    assert result["answer"] != NO_KB_MESSAGE
    assert result["sources"][0]["source_type"] == "uploaded_document"
