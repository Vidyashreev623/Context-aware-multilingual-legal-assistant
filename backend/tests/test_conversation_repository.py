"""
Phase 10 tests: database.py + repositories.py against a REAL sqlite3
database file (stdlib only -- no network/pip install needed, unlike
Phases 3-6's chromadb/faiss/sentence-transformers/google-generativeai
deps), so unlike those phases this one is actually executed in this
sandbox, not just reviewed by hand.

Run: pytest backend/tests/test_conversation_repository.py -v
(also runnable directly: python backend/tests/test_conversation_repository.py)
"""
import sys
import tempfile
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


@test
def test_create_and_get_conversation():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    assert conv.title == "New Chat"
    fetched = repo.get_conversation(conv.id, db_path=db)
    assert fetched is not None
    assert fetched.id == conv.id


@test
def test_get_unknown_conversation_returns_none():
    db = _fresh_db()
    assert repo.get_conversation("does-not-exist", db_path=db) is None


@test
def test_get_or_create_falls_back_on_unknown_id():
    db = _fresh_db()
    conv = repo.get_or_create_conversation("unknown-id", db_path=db)
    assert conv.id != "unknown-id"
    assert repo.get_conversation(conv.id, db_path=db) is not None


@test
def test_get_or_create_reuses_existing():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    reused = repo.get_or_create_conversation(conv.id, db_path=db)
    assert reused.id == conv.id


@test
def test_get_or_create_none_id_creates_new():
    db = _fresh_db()
    conv = repo.get_or_create_conversation(None, db_path=db)
    assert repo.get_conversation(conv.id, db_path=db) is not None


@test
def test_add_message_and_get_messages_ordered():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    repo.add_message(conv.id, "user", "What is Section 66C?", db_path=db)
    repo.add_message(
        conv.id, "assistant", "Section 66C deals with identity theft...",
        language="en", sources=[{"title": "IT Act, 2000", "section": "66C", "domain": "cyber"}],
        classification={"domain": "cyber", "confidence": 0.9},
        db_path=db,
    )
    messages = repo.get_messages(conv.id, db_path=db)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].sources[0]["section"] == "66C"
    assert messages[1].classification["domain"] == "cyber"


@test
def test_first_user_message_sets_conversation_title():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    repo.add_message(conv.id, "user", "What are the essentials of a valid contract?", db_path=db)
    updated = repo.get_conversation(conv.id, db_path=db)
    assert updated.title == "What are the essentials of a valid contract?"


@test
def test_long_first_message_title_is_truncated():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    long_msg = "What happens under Indian contract law " * 5
    repo.add_message(conv.id, "user", long_msg, db_path=db)
    updated = repo.get_conversation(conv.id, db_path=db)
    assert len(updated.title) <= 61  # _TITLE_MAX_LEN + ellipsis
    assert updated.title.endswith("…")


@test
def test_explicit_rename_is_not_overwritten_by_later_messages():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    repo.add_message(conv.id, "user", "first message", db_path=db)
    repo.rename_conversation(conv.id, "My renamed chat", db_path=db)
    repo.add_message(conv.id, "user", "second message", db_path=db)
    updated = repo.get_conversation(conv.id, db_path=db)
    assert updated.title == "My renamed chat"


@test
def test_list_conversations_ordered_by_recency():
    db = _fresh_db()
    c1 = repo.create_conversation(db_path=db)
    c2 = repo.create_conversation(db_path=db)
    # touch c1 again so it becomes the most recently updated
    repo.add_message(c1.id, "user", "hello again", db_path=db)
    listed = repo.list_conversations(db_path=db)
    assert listed[0].id == c1.id
    assert listed[1].id == c2.id


@test
def test_delete_conversation_cascades_messages():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    repo.add_message(conv.id, "user", "hi", db_path=db)
    assert repo.delete_conversation(conv.id, db_path=db) is True
    assert repo.get_conversation(conv.id, db_path=db) is None
    assert repo.get_messages(conv.id, db_path=db) == []


@test
def test_delete_unknown_conversation_returns_false():
    db = _fresh_db()
    assert repo.delete_conversation("nope", db_path=db) is False


@test
def test_get_recent_history_shape_and_limit():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    repo.add_message(conv.id, "user", "What is Section 66C?", db_path=db)
    repo.add_message(conv.id, "assistant", "It deals with identity theft.", db_path=db)
    repo.add_message(conv.id, "user", "What is the punishment?", db_path=db)
    history = repo.get_recent_history(conv.id, max_turns=2, db_path=db)
    assert history == [
        {"role": "assistant", "content": "It deals with identity theft."},
        {"role": "user", "content": "What is the punishment?"},
    ]


@test
def test_get_recent_history_empty_for_new_conversation():
    db = _fresh_db()
    conv = repo.create_conversation(db_path=db)
    assert repo.get_recent_history(conv.id, max_turns=6, db_path=db) == []


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
