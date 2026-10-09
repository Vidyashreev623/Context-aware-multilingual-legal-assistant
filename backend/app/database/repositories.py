"""
Repository functions over the conversations/messages/documents tables.
Every function takes an optional `db_path` purely for backward
compatibility with test call sites -- under Postgres it's ignored;
point DATABASE_URL at a separate test database/schema instead.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.database.database import get_connection
from app.database.models import Conversation, Document, Message

DEFAULT_TITLE = "New Chat"
_TITLE_MAX_LEN = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _derive_title(first_message: str) -> str:
    text = " ".join(first_message.split())
    if len(text) <= _TITLE_MAX_LEN:
        return text
    return text[:_TITLE_MAX_LEN].rstrip() + "…"


def create_conversation(title: str | None = None, user_id: str | None = None, db_path: str | None = None) -> Conversation:
    conv = Conversation(
        id=_new_id(),
        title=title or DEFAULT_TITLE,
        created_at=_now(),
        updated_at=_now(),
    )
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at, user_id) VALUES (%s, %s, %s, %s, %s)",
            (conv.id, conv.title, conv.created_at, conv.updated_at, user_id),
        )
    return conv


def list_conversations(user_id: str | None = None, db_path: str | None = None) -> list[Conversation]:
    with get_connection(db_path) as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE user_id = %s ORDER BY updated_at DESC", (user_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
    return [Conversation.from_row(r) for r in rows]


def get_or_create_conversation(conversation_id: str | None, user_id: str | None = None, db_path: str | None = None) -> Conversation:
    if conversation_id:
        existing = get_conversation(conversation_id, db_path=db_path)
        if existing and existing.user_id == user_id:
            return existing
    return create_conversation(user_id=user_id, db_path=db_path)


def get_conversation(conversation_id: str, db_path: str | None = None) -> Conversation | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = %s", (conversation_id,)
        ).fetchone()
    return Conversation.from_row(row) if row else None


def rename_conversation(conversation_id: str, title: str, db_path: str | None = None) -> Conversation | None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE conversations SET title = %s, updated_at = %s WHERE id = %s",
            (title, _now(), conversation_id),
        )
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = %s", (conversation_id,)
        ).fetchone()
    return Conversation.from_row(row) if row else None


def delete_conversation(conversation_id: str, db_path: str | None = None) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
        return cur.rowcount > 0


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    language: str | None = None,
    sources: list[dict] | None = None,
    classification: dict | None = None,
    ambiguous: bool = False,
    db_path: str | None = None,
) -> Message:
    msg = Message(
        id=_new_id(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=_now(),
        language=language,
        sources=sources or [],
        classification=classification,
        ambiguous=ambiguous,
    )
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO messages
               (id, conversation_id, role, content, language, sources_json,
                classification_json, ambiguous, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                msg.id, msg.conversation_id, msg.role, msg.content, msg.language,
                json.dumps(msg.sources), json.dumps(msg.classification) if msg.classification else None,
                int(msg.ambiguous), msg.created_at,
            ),
        )
        conv_row = conn.execute(
            "SELECT title FROM conversations WHERE id = %s", (conversation_id,)
        ).fetchone()
        if conv_row is not None:
            new_title = conv_row["title"]
            if role == "user" and new_title == DEFAULT_TITLE:
                new_title = _derive_title(content)
            conn.execute(
                "UPDATE conversations SET updated_at = %s, title = %s WHERE id = %s",
                (_now(), new_title, conversation_id),
            )
    return msg


def get_messages(conversation_id: str, db_path: str | None = None) -> list[Message]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
    return [Message.from_row(r) for r in rows]


def get_recent_history(conversation_id: str, max_turns: int, db_path: str | None = None) -> list[dict]:
    messages = get_messages(conversation_id, db_path=db_path)
    recent = messages[-max_turns:] if max_turns > 0 else []
    return [{"role": m.role, "content": m.content} for m in recent]


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def create_document(
    document_id: str,
    filename: str,
    file_type: str,
    conversation_id: str | None = None,
    db_path: str | None = None,
) -> Document:
    doc = Document(
        id=document_id,
        filename=filename,
        file_type=file_type,
        status="processing",
        uploaded_at=_now(),
        conversation_id=conversation_id,
    )
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO documents
               (id, filename, file_type, language, status, error,
                chunk_count, conversation_id, uploaded_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (doc.id, doc.filename, doc.file_type, doc.language, doc.status,
             doc.error, doc.chunk_count, doc.conversation_id, doc.uploaded_at),
        )
    return doc


def mark_document_processed(
    document_id: str, language: str, chunk_count: int, db_path: str | None = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE documents SET status = 'processed', language = %s, chunk_count = %s WHERE id = %s",
            (language, chunk_count, document_id),
        )


def mark_document_failed(document_id: str, error: str, db_path: str | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE documents SET status = 'failed', error = %s WHERE id = %s",
            (error, document_id),
        )


def get_document(document_id: str, db_path: str | None = None) -> Document | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = %s", (document_id,)).fetchone()
    return Document.from_row(row) if row else None


def list_documents(db_path: str | None = None) -> list[Document]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    return [Document.from_row(r) for r in rows]


def delete_document_record(document_id: str, db_path: str | None = None) -> bool:
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        return cur.rowcount > 0


def attach_document_to_conversation(document_id: str, conversation_id: str, db_path: str | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE documents SET conversation_id = %s WHERE id = %s AND conversation_id IS NULL",
            (conversation_id, document_id),
        )