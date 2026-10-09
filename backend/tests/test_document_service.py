"""
Phase 12 tests: document_service.py.

Runs the REAL extraction (extract_text.py, no pypdf/python-docx
needed for .txt fixtures) -> cleaning -> chunking -> embedding
pipeline, against a fake in-memory VectorStore/EmbeddingProvider (same
approach test_rag_service_improved.py uses) so this executes fully
offline in this sandbox -- no chromadb/faiss/sentence-transformers
install required. The `documents` table side is exercised against a
real temp SQLite file, same as test_document_repository.py.

Run: pytest backend/tests/test_document_service.py -v
(also runnable directly: python backend/tests/test_document_service.py)
"""
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.database.database import init_db
from backend.app.database import repositories as repo
from backend.app.services.embedding_service import EmbeddingProvider
from backend.app.services.vector_store_service import SearchResult, VectorStore, VectorRecord
from backend.app.services.document_service import (
    DocumentProcessingError,
    UPLOADED_DOMAIN,
    delete_document,
    process_uploaded_document,
    retrieve_document_context,
)

TESTS_RUN = []


def test(fn):
    TESTS_RUN.append(fn)
    return fn


def _fresh_db() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    init_db(db_path=tmp.name)
    return tmp.name


def _new_id() -> str:
    return uuid.uuid4().hex


def _write_txt(tmp_dir: Path, name: str, text: str) -> Path:
    path = tmp_dir / name
    path.write_text(text, encoding="utf-8")
    return path


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, non-semantic: every chunk's embedding is a
    function of its position only, so tests can control which chunk
    is the query vector's exact nearest neighbour without depending on
    real semantic similarity."""
    name = "fake"

    @property
    def dimension(self) -> int:
        return 2

    def embed_batch(self, texts):
        # Alternates between two orthogonal unit vectors by index, so
        # a multi-chunk document produces distinguishable embeddings.
        return [[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0] for i, _ in enumerate(texts)]


class InMemoryVectorStore(VectorStore):
    """Minimal but fully-behaved VectorStore over a plain dict, so
    document_service's add/search(where=...)/filter/delete calls all
    behave like the real Chroma/FAISS backends without needing either
    installed."""
    name = "memory"

    def __init__(self):
        self._records: dict[str, VectorRecord] = {}

    def add(self, records):
        for r in records:
            self._records[r.chunk_id] = r
        return len(records)

    def search(self, query_embedding, top_k=10, where=None):
        out = []
        for r in self._records.values():
            meta = r.metadata()
            if where and not all(meta.get(k) == v for k, v in where.items()):
                continue
            score = sum(a * b for a, b in zip(query_embedding, r.embedding))
            out.append(SearchResult(chunk_id=r.chunk_id, text=r.text, score=score, metadata=meta))
        out.sort(key=lambda x: x.score, reverse=True)
        return out[:top_k]

    def delete(self, chunk_ids):
        n = 0
        for cid in chunk_ids:
            if cid in self._records:
                del self._records[cid]
                n += 1
        return n

    def filter(self, where, limit=1000):
        out = []
        for r in self._records.values():
            meta = r.metadata()
            if all(meta.get(k) == v for k, v in where.items()):
                out.append({"chunk_id": r.chunk_id, "metadata": meta})
                if len(out) >= limit:
                    break
        return out

    def count(self):
        return len(self._records)


# ---------------------------------------------------------------------------
# process_uploaded_document
# ---------------------------------------------------------------------------

@test
def test_process_uploaded_document_indexes_chunks_with_document_id():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_txt(
            Path(tmp), "rental.txt",
            "This rental agreement is made between the landlord and the tenant.\n\n"
            "The tenant shall pay a monthly rent of Rs. 20,000 on or before the "
            "5th of every month.\n\n"
            "Either party may terminate this agreement by giving three months' "
            "written notice to the other party.",
        )
        store = InMemoryVectorStore()
        doc_id = _new_id()
        result = process_uploaded_document(
            doc_id, path, "rental.txt",
            embedding_provider=FakeEmbeddingProvider(), vector_store=store,
        )
        assert result["chunk_count"] > 0
        assert result["language"] == "en"
        assert store.count() == result["chunk_count"]
        for record in store._records.values():
            assert record.document_id == doc_id
            assert record.domain == UPLOADED_DOMAIN
            assert record.act_name == "rental.txt"


@test
def test_process_uploaded_document_detects_hindi():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_txt(
            Path(tmp), "notice.txt",
            "यह एक किरायेदारी समझौता है। किरायेदार को हर महीने किराया देना होगा। "
            "कोई भी पक्ष तीन महीने का लिखित नोटिस देकर इस समझौते को समाप्त कर सकता है।",
        )
        store = InMemoryVectorStore()
        result = process_uploaded_document(
            _new_id(), path, "notice.txt",
            embedding_provider=FakeEmbeddingProvider(), vector_store=store,
        )
        assert result["language"] == "hi"


@test
def test_process_uploaded_document_rejects_empty_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_txt(Path(tmp), "empty.txt", "   \n\n   ")
        store = InMemoryVectorStore()
        try:
            process_uploaded_document(
                _new_id(), path, "empty.txt",
                embedding_provider=FakeEmbeddingProvider(), vector_store=store,
            )
            assert False, "expected DocumentProcessingError"
        except DocumentProcessingError:
            pass
        assert store.count() == 0


@test
def test_process_uploaded_document_rejects_missing_file():
    store = InMemoryVectorStore()
    try:
        process_uploaded_document(
            _new_id(), "/nonexistent/path.txt", "path.txt",
            embedding_provider=FakeEmbeddingProvider(), vector_store=store,
        )
        assert False, "expected DocumentProcessingError"
    except DocumentProcessingError:
        pass


# ---------------------------------------------------------------------------
# retrieve_document_context
# ---------------------------------------------------------------------------

@test
def test_retrieve_document_context_returns_empty_for_no_document_ids():
    store = InMemoryVectorStore()
    assert retrieve_document_context([], [1.0, 0.0], top_k=5, vector_store=store) == []


@test
def test_retrieve_document_context_scopes_to_given_document():
    store = InMemoryVectorStore()
    store.add([
        VectorRecord(
            chunk_id="doc1_c1", text="Notice period is three months.",
            embedding=[1.0, 0.0], domain=UPLOADED_DOMAIN, document_type="uploaded_document",
            act_name="rental.txt", jurisdiction="N/A", language="en", source="user upload",
            document_id="doc1",
        ),
        VectorRecord(
            chunk_id="doc2_c1", text="Salary shall be paid monthly.",
            embedding=[1.0, 0.0], domain=UPLOADED_DOMAIN, document_type="uploaded_document",
            act_name="offer_letter.txt", jurisdiction="N/A", language="en", source="user upload",
            document_id="doc2",
        ),
    ])
    results = retrieve_document_context(["doc1"], [1.0, 0.0], top_k=5, vector_store=store)
    assert len(results) == 1
    assert results[0].chunk_id == "doc1_c1"


@test
def test_retrieve_document_context_merges_multiple_documents_by_score():
    store = InMemoryVectorStore()
    store.add([
        VectorRecord(
            chunk_id="doc1_c1", text="less relevant", embedding=[0.0, 1.0],
            domain=UPLOADED_DOMAIN, document_type="uploaded_document", act_name="a.txt",
            jurisdiction="N/A", language="en", source="user upload", document_id="doc1",
        ),
        VectorRecord(
            chunk_id="doc2_c1", text="more relevant", embedding=[1.0, 0.0],
            domain=UPLOADED_DOMAIN, document_type="uploaded_document", act_name="b.txt",
            jurisdiction="N/A", language="en", source="user upload", document_id="doc2",
        ),
    ])
    results = retrieve_document_context(["doc1", "doc2"], [1.0, 0.0], top_k=5, vector_store=store)
    assert [r.chunk_id for r in results] == ["doc2_c1", "doc1_c1"]


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------

@test
def test_delete_document_removes_chunks_row_and_file():
    db = _fresh_db()
    with tempfile.TemporaryDirectory() as uploads_dir:
        doc_id = _new_id()
        repo.create_document(doc_id, filename="a.txt", file_type="txt", db_path=db)
        file_path = Path(uploads_dir) / f"{doc_id}.txt"
        file_path.write_text("dummy", encoding="utf-8")

        store = InMemoryVectorStore()
        store.add([
            VectorRecord(
                chunk_id=f"{doc_id}_c1", text="x", embedding=[1.0, 0.0],
                domain=UPLOADED_DOMAIN, document_type="uploaded_document", act_name="a.txt",
                jurisdiction="N/A", language="en", source="user upload", document_id=doc_id,
            ),
        ])

        deleted = delete_document(doc_id, uploads_dir=uploads_dir, vector_store=store, db_path=db)
        assert deleted is True
        assert store.count() == 0
        assert not file_path.exists()
        assert repo.get_document(doc_id, db_path=db) is None


@test
def test_delete_document_returns_false_for_unknown_id():
    db = _fresh_db()
    store = InMemoryVectorStore()
    with tempfile.TemporaryDirectory() as uploads_dir:
        assert delete_document("nope", uploads_dir=uploads_dir, vector_store=store, db_path=db) is False


if __name__ == "__main__":
    failures = 0
    for fn in TESTS_RUN:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS_RUN) - failures}/{len(TESTS_RUN)} passed")
    sys.exit(1 if failures else 0)
