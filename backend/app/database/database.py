"""
Postgres (Supabase) connection pool + schema.
Auth: `users` table and `conversations.user_id` are created directly
by SCHEMA now -- ensure_auth_schema() in user_repository.py is kept as
a no-op only so existing call sites don't need to change.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    language TEXT,
    sources_json TEXT,
    classification_json TEXT,
    ambiguous INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
    ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    language TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    error TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    uploaded_at TEXT NOT NULL
);

-- Signup email verification + forgot-password OTP codes.
CREATE TABLE IF NOT EXISTS email_verification_codes (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    purpose TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    verified_token TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_email_verification_codes_email_purpose
    ON email_verification_codes(email, purpose);
"""

# CREATE TABLE IF NOT EXISTS above does nothing to an *existing* users
# table, so the new `name` column has to be added separately. Safe to
# re-run: ADD COLUMN IF NOT EXISTS is a no-op once the column exists.
MIGRATIONS = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;
"""

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=get_settings().DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    kwargs={"row_factory": dict_row},
                    open=True,
                )
    return _pool


def init_db(db_path: str | None = None) -> None:
    """db_path is accepted (and ignored) for backward compatibility
    with existing callers/tests."""
    with get_connection() as conn:
        conn.execute(SCHEMA)
        conn.execute(MIGRATIONS)


@contextmanager
def get_connection(db_path: str | None = None):
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn
        # psycopg_pool commits on clean exit, rolls back on exception.
