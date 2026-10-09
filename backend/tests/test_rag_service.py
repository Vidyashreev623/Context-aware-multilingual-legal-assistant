"""
Phase 6 tests: rag_service.py's basic RAG pipeline (query -> embed ->
vector search -> top-K -> Gemini -> answer).

Uses small fake providers (defined below) rather than the real Chroma/
FAISS/sentence-transformers/Gemini stack, via rag_service.answer_question's
dependency-injection parameters -- this is exactly why those parameters
exist. Verifies the pipeline's own logic (empty-KB handling, no-match
handling, context truncation, source dedup, Gemini error translation)
independent of any specific backend.

Run: pytest backend/tests/test_rag_service.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.embedding_service import EmbeddingProvider
from backend.app.services.vector_store_service import SearchResult, VectorStore, VectorRecord
from backend.app.services.gemini_service import (
    GeminiError,
    GeminiNotConfiguredError,
    GeminiRateLimitError,
    LLMProvider,
)
from backend.app.services.rag_service import (
    NO_KB_MESSAGE,
    NO_MATCH_MESSAGE,
    _build_context,
    _build_sources,
    answer_question,
)


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "fake"

    @property
    def dimension(self) -> int:
        return 3

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeVectorStore(VectorStore):
    """Minimal in-memory VectorStore for tests -- brute-force, no real
    ANN index, since these tests only care about rag_service's own
    logic, not search performance."""
    name = "fake"

    def __init__(self, results: list[SearchResult] | None = None):
        self._results = results or []

    def add(self, records: list[VectorRecord]) -> int:
        return len(records)

    def search(self, query_embedding, top_k=10, where=None):
        return self._results[:top_k]

    def delete(self, chunk_ids):
        return 0

    def filter(self, where, limit=1000):
        return []

    def count(self) -> int:
        return len(self._results) if self._results else 0


class FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, response: str = "This is a test answer.", raise_error: Exception | None = None):
        self._response = response
        self._raise_error = raise_error

    def generate(self, system_instructions: str, user_message: str) -> str:
        if self._raise_error:
            raise self._raise_error
        return self._response


def _sample_results() -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id="it_act_66c_001", text="Whoever fraudulently uses another's identity...",
            score=0.91,
            metadata={"act_name": "Information Technology Act, 2000", "section": "66C", "domain": "cyber"},
        ),
        SearchResult(
            chunk_id="it_act_66c_002", text="Punishment includes imprisonment and fine.",
            score=0.85,
            metadata={"act_name": "Information Technology Act, 2000", "section": "66C", "domain": "cyber"},
        ),
    ]


def test_empty_knowledge_base_returns_clear_message():
    store = FakeVectorStore(results=[])
    # count() == 0 path
    result = answer_question(
        "What is Section 66C?",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        llm_provider=FakeLLMProvider(),
    )
    assert result["answer"] == NO_KB_MESSAGE
    assert result["sources"] == []


def test_no_search_results_returns_no_match_message():
    class NonEmptyButNoResultsStore(FakeVectorStore):
        def count(self):
            return 5  # KB has data...

        def search(self, query_embedding, top_k=10, where=None):
            return []  # ...but nothing matched this query

    result = answer_question(
        "Completely unrelated question",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=NonEmptyButNoResultsStore(),
        llm_provider=FakeLLMProvider(),
    )
    assert result["answer"] == NO_MATCH_MESSAGE


def test_happy_path_returns_answer_and_sources():
    results = _sample_results()

    class Store(FakeVectorStore):
        def count(self):
            return len(results)

        def search(self, query_embedding, top_k=10, where=None):
            return results[:top_k]

    result = answer_question(
        "What is the punishment under Section 66C?",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=Store(),
        llm_provider=FakeLLMProvider(response="Section 66C prescribes imprisonment and a fine."),
    )
    assert "Section 66C prescribes imprisonment and a fine." in result["answer"]
    assert "not legal advice" in result["answer"].lower()  # disclaimer appended
    assert len(result["sources"]) == 1  # both chunks share the same (title, section) -> deduped
    assert result["sources"][0]["title"] == "Information Technology Act, 2000"
    assert result["sources"][0]["section"] == "66C"


def test_disclaimer_not_duplicated_if_llm_already_included_one():
    results = _sample_results()

    class Store(FakeVectorStore):
        def count(self):
            return len(results)

        def search(self, query_embedding, top_k=10, where=None):
            return results

    llm_response = "Some answer.\n\nThis is not legal advice, consult a lawyer."
    result = answer_question(
        "question",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=Store(),
        llm_provider=FakeLLMProvider(response=llm_response),
    )
    assert result["answer"].lower().count("not legal advice") == 1


def test_gemini_not_configured_error_gives_graceful_message():
    results = _sample_results()

    class Store(FakeVectorStore):
        def count(self):
            return len(results)

        def search(self, query_embedding, top_k=10, where=None):
            return results

    result = answer_question(
        "question",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=Store(),
        llm_provider=FakeLLMProvider(raise_error=GeminiNotConfiguredError("no key")),
    )
    assert "not configured" in result["answer"].lower()
    assert result["sources"] == []


def test_gemini_rate_limit_error_gives_graceful_message():
    results = _sample_results()

    class Store(FakeVectorStore):
        def count(self):
            return len(results)

        def search(self, query_embedding, top_k=10, where=None):
            return results

    result = answer_question(
        "question",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=Store(),
        llm_provider=FakeLLMProvider(raise_error=GeminiRateLimitError("quota")),
    )
    assert "limit reached" in result["answer"].lower()


def test_generic_gemini_error_gives_graceful_message():
    results = _sample_results()

    class Store(FakeVectorStore):
        def count(self):
            return len(results)

        def search(self, query_embedding, top_k=10, where=None):
            return results

    result = answer_question(
        "question",
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=Store(),
        llm_provider=FakeLLMProvider(raise_error=GeminiError("boom")),
    )
    assert "try again" in result["answer"].lower()


def test_build_context_stops_before_exceeding_max_chars():
    results = _sample_results()
    text, used = _build_context(results, max_chars=50)
    assert len(used) == 1  # second block would exceed the tiny budget
    assert "66C" in text


def test_build_context_always_keeps_at_least_one_block():
    results = _sample_results()
    text, used = _build_context(results, max_chars=1)  # smaller than any single block
    assert len(used) == 1
    assert text  # not empty


def test_build_sources_deduplicates_by_title_and_section():
    results = _sample_results()  # both chunks -> same act_name + section
    sources = _build_sources(results)
    assert len(sources) == 1


# --- Phase 14: source_type / document_type / year on _build_sources ---

def test_build_sources_tags_legal_database_source_type():
    results = _sample_results()  # domain="cyber", never UPLOADED_DOMAIN
    sources = _build_sources(results)
    assert sources[0]["source_type"] == "legal_database"


def test_build_sources_tags_uploaded_document_source_type():
    from backend.app.services.document_service import UPLOADED_DOMAIN

    results = [
        SearchResult(
            chunk_id="doc123_001", text="Notice period is 30 days.",
            score=0.9,
            metadata={
                "act_name": "rental_agreement.pdf", "section": None,
                "domain": UPLOADED_DOMAIN, "document_type": "uploaded_document",
                "document_id": "doc123",
            },
        ),
    ]
    sources = _build_sources(results)
    assert sources[0]["source_type"] == "uploaded_document"
    assert sources[0]["domain"] == UPLOADED_DOMAIN


def test_build_sources_mixes_uploaded_and_legal_database_without_cross_contamination():
    """Spec section 31: a single answer can draw on both an uploaded
    document and the legal knowledge base -- each source in the list
    must carry its OWN correct source_type, not one bleeding into the
    other."""
    from backend.app.services.document_service import UPLOADED_DOMAIN

    results = [
        SearchResult(
            chunk_id="doc123_001", text="Notice period is 30 days.",
            score=0.95,
            metadata={
                "act_name": "rental_agreement.pdf", "section": None,
                "domain": UPLOADED_DOMAIN, "document_type": "uploaded_document",
            },
        ),
        SearchResult(
            chunk_id="tp_act_001", text="Notice under the Transfer of Property Act...",
            score=0.7,
            metadata={
                "act_name": "Transfer of Property Act, 1882", "section": "106",
                "domain": "property", "document_type": "act", "year": 1882,
            },
        ),
    ]
    sources = _build_sources(results)
    assert len(sources) == 2
    by_type = {s["source_type"] for s in sources}
    assert by_type == {"uploaded_document", "legal_database"}
    uploaded = next(s for s in sources if s["source_type"] == "uploaded_document")
    legal = next(s for s in sources if s["source_type"] == "legal_database")
    assert uploaded["title"] == "rental_agreement.pdf"
    assert legal["title"] == "Transfer of Property Act, 1882"
    assert legal["year"] == 1882


def test_build_sources_case_law_has_no_section_but_has_year():
    """Spec section 27's answer format cites cases as 'Case name —
    Year', not 'Case name — Section' -- a case-law chunk legitimately
    has section=None, and document_type="case" is what tells the
    frontend that's expected rather than missing metadata."""
    results = [
        SearchResult(
            chunk_id="shreya_singhal_001", text="Section 66A was struck down as unconstitutional...",
            score=0.88,
            metadata={
                "act_name": "Shreya Singhal v. Union of India", "section": None,
                "domain": "cyber", "document_type": "case", "year": 2015,
            },
        ),
    ]
    sources = _build_sources(results)
    assert len(sources) == 1
    assert sources[0]["document_type"] == "case"
    assert sources[0]["section"] is None
    assert sources[0]["year"] == 2015
    assert sources[0]["source_type"] == "legal_database"


def test_build_sources_never_fabricates_missing_fields():
    """Spec section 28: sources come only from actual retrieved-chunk
    metadata -- a chunk with sparse metadata must surface exactly
    that sparseness (None), never a made-up placeholder."""
    results = [
        SearchResult(chunk_id="x", text="...", score=0.5, metadata={}),
    ]
    sources = _build_sources(results)
    assert sources[0]["title"] == "Unknown source"
    assert sources[0]["section"] is None
    assert sources[0]["domain"] is None
    assert sources[0]["document_type"] is None
    assert sources[0]["year"] is None
