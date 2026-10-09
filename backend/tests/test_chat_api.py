"""
Phase 14 tests: the /api/chat endpoint (api/chat.py) end to end through
a real FastAPI TestClient, focused on spec section 28's citation
contract -- every source in a real HTTP response carries `source_type`
(and, since Phase 14, `document_type`/`year`), and mixed uploaded-
document + legal-database answers surface both correctly.

Uses a real temporary SQLite file for conversation persistence (same
approach test_conversation_repository.py already validated for the DB
layer itself) with the RAG pipeline itself faked out (rag_service.answer_question_improved
is heavier -- Chroma/FAISS/sentence-transformers/Gemini -- and already
has its own dedicated, thorough test suite in test_rag_service_improved.py;
this file's job is to confirm the HTTP layer wires that result through
correctly, not to re-test the pipeline's own retrieval logic).

Run: pytest backend/tests/test_chat_api.py -v
"""
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR.parent))


@pytest.fixture()
def client(monkeypatch):
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db.name}")

    from app.config import get_settings
    get_settings.cache_clear()

    from app.main import app
    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()
    Path(tmp_db.name).unlink(missing_ok=True)


def _fake_result(sources):
    return {
        "answer": "Section 66C deals with identity theft.\n\n_This is general legal information, not legal advice._",
        "language": "en",
        "sources": sources,
        "classification": {
            "language": "en", "domain": "cyber", "jurisdiction": "India",
            "state": None, "court": None, "query_type": "section_lookup",
            "ambiguity": False, "confidence": 0.9,
        },
        "ambiguous": False,
    }


LEGAL_SOURCE = {
    "title": "Information Technology Act, 2000", "section": "66C",
    "domain": "cyber", "source_type": "legal_database",
    "document_type": "act", "year": 2000,
}
CASE_SOURCE = {
    "title": "Shreya Singhal v. Union of India", "section": None,
    "domain": "cyber", "source_type": "legal_database",
    "document_type": "case", "year": 2015,
}
UPLOADED_SOURCE = {
    "title": "rental_agreement.pdf", "section": None,
    "domain": "uploaded_documents", "source_type": "uploaded_document",
    "document_type": "uploaded_document", "year": None,
}


def test_chat_response_carries_document_type_and_year_on_sources(client, monkeypatch):
    import app.api.chat as chat_api
    monkeypatch.setattr(chat_api, "answer_question_improved", lambda **kw: _fake_result([LEGAL_SOURCE]))

    res = client.post("/api/chat", json={"message": "What is Section 66C?", "language": "en"})
    assert res.status_code == 200
    body = res.json()
    assert body["sources"][0]["document_type"] == "act"
    assert body["sources"][0]["year"] == 2000
    assert body["sources"][0]["source_type"] == "legal_database"


def test_chat_response_case_law_source_has_no_section(client, monkeypatch):
    import app.api.chat as chat_api
    monkeypatch.setattr(chat_api, "answer_question_improved", lambda **kw: _fake_result([CASE_SOURCE]))

    res = client.post("/api/chat", json={"message": "Was Section 66A struck down?", "language": "en"})
    body = res.json()
    assert body["sources"][0]["document_type"] == "case"
    assert body["sources"][0]["section"] is None
    assert body["sources"][0]["year"] == 2015


def test_chat_response_mixed_uploaded_and_legal_sources(client, monkeypatch):
    import app.api.chat as chat_api
    monkeypatch.setattr(
        chat_api, "answer_question_improved",
        lambda **kw: _fake_result([UPLOADED_SOURCE, LEGAL_SOURCE]),
    )

    res = client.post(
        "/api/chat",
        json={"message": "What does my agreement say vs the law?", "language": "en", "document_ids": ["doc1"]},
    )
    body = res.json()
    source_types = {s["source_type"] for s in body["sources"]}
    assert source_types == {"uploaded_document", "legal_database"}


def test_chat_conversation_id_persists_across_two_turns(client, monkeypatch):
    """Spec section 37: 'Continue conversation' -- a real conversation_id
    round-trips through real SQLite (not faked), confirming sources/turns
    from Phase 14's citation payload survive persistence, not just the
    single in-memory response."""
    import app.api.chat as chat_api
    monkeypatch.setattr(chat_api, "answer_question_improved", lambda **kw: _fake_result([LEGAL_SOURCE]))

    first = client.post("/api/chat", json={"message": "What is Section 66C?", "language": "en"})
    conv_id = first.json()["conversation_id"]
    assert conv_id

    second = client.post(
        "/api/chat",
        json={"message": "What is the punishment?", "language": "en", "conversation_id": conv_id},
    )
    assert second.json()["conversation_id"] == conv_id

    history = client.get(f"/api/conversations/{conv_id}")
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert len(messages) == 4  # 2 user + 2 assistant turns
