"""
Phase 12 tests: the `documents` table (database.py + repositories.py)
against a REAL sqlite3 file, same style/rationale as
test_conversation_repository.py (stdlib-only, actually runnable in
this sandbox).

Run: pytest backend/tests/test_document_repository.py -v
(also runnable directly: python backend/tests/test_document_repository.py)
"""
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.database.database import init_db
from backend.app.database import repositories as repo

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


@test
def test_create_document_starts_processing():
    db = _fresh_db()
    doc_id = _new_id()
    doc = repo.create_document(doc_id, filename="rental_agreement.pdf", file_type="pdf", db_path=db)
    assert doc.status == "processing"
    assert doc.chunk_count == 0
    assert doc.conversation_id is None

    fetched = repo.get_document(doc_id, db_path=db)
    assert fetched is not None
    assert fetched.filename == "rental_agreement.pdf"
    assert fetched.status == "processing"


@test
def test_get_unknown_document_returns_none():
    db = _fresh_db()
    assert repo.get_document("does-not-exist", db_path=db) is None


@test
def test_mark_document_processed_sets_language_and_chunk_count():
    db = _fresh_db()
    doc_id = _new_id()
    repo.create_document(doc_id, filename="lease.txt", file_type="txt", db_path=db)
    repo.mark_document_processed(doc_id, language="en", chunk_count=7, db_path=db)

    doc = repo.get_document(doc_id, db_path=db)
    assert doc.status == "processed"
    assert doc.language == "en"
    assert doc.chunk_count == 7
    assert doc.error is None


@test
def test_mark_document_failed_sets_error_and_leaves_chunk_count_zero():
    db = _fresh_db()
    doc_id = _new_id()
    repo.create_document(doc_id, filename="scan.pdf", file_type="pdf", db_path=db)
    repo.mark_document_failed(doc_id, "No extractable text.", db_path=db)

    doc = repo.get_document(doc_id, db_path=db)
    assert doc.status == "failed"
    assert doc.error == "No extractable text."
    assert doc.chunk_count == 0


@test
def test_list_documents_orders_by_recency():
    db = _fresh_db()
    first = _new_id()
    second = _new_id()
    repo.create_document(first, filename="a.txt", file_type="txt", db_path=db)
    repo.create_document(second, filename="b.txt", file_type="txt", db_path=db)

    docs = repo.list_documents(db_path=db)
    ids = [d.id for d in docs]
    # Most-recently-uploaded first (uploaded_at DESC).
    assert ids[0] == second
    assert ids[1] == first


@test
def test_delete_document_record_removes_row():
    db = _fresh_db()
    doc_id = _new_id()
    repo.create_document(doc_id, filename="a.txt", file_type="txt", db_path=db)
    assert repo.delete_document_record(doc_id, db_path=db) is True
    assert repo.get_document(doc_id, db_path=db) is None


@test
def test_delete_document_record_returns_false_when_missing():
    db = _fresh_db()
    assert repo.delete_document_record("nope", db_path=db) is False


@test
def test_attach_document_to_conversation_sets_once():
    db = _fresh_db()
    doc_id = _new_id()
    repo.create_document(doc_id, filename="a.txt", file_type="txt", db_path=db)
    conv = repo.create_conversation(db_path=db)
    other_conv = repo.create_conversation(db_path=db)

    repo.attach_document_to_conversation(doc_id, conv.id, db_path=db)
    doc = repo.get_document(doc_id, db_path=db)
    assert doc.conversation_id == conv.id

    # A second attach attempt (e.g. the document is referenced again
    # in a later, different conversation) must NOT overwrite the first
    # link -- "WHERE conversation_id IS NULL" guards this.
    repo.attach_document_to_conversation(doc_id, other_conv.id, db_path=db)
    doc_again = repo.get_document(doc_id, db_path=db)
    assert doc_again.conversation_id == conv.id


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
