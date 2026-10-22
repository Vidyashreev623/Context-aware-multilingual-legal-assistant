
"""
SQLite/PostgreSQL database connection and schema management.
SQLite is used when an explicit db_path is supplied (tests).
PostgreSQL/Supabase remains the default for application runtime.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from app.config import get_settings

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    name TEXT
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

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    name TEXT
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


def _sqlite_path(db_path: str) -> str:
    # Accept either a plain filesystem path or a SQLite URL.
    if db_path.startswith("sqlite:///"):
        return db_path[len("sqlite:///"):]
    return db_path



@contextmanager
def get_connection(db_path: str | None = None):
    database_url = db_path or get_settings().DATABASE_URL

    if database_url.startswith("sqlite:///"):
        conn = sqlite3.connect(_sqlite_path(database_url))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield _SQLiteConnection(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    elif db_path is not None:
        # An explicit plain filesystem path means SQLite.
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield _SQLiteConnection(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        pool = _get_pool()
        with pool.connection() as conn:
            yield conn


class _SQLiteConnection:
    """Small compatibility wrapper for repository SQL written for psycopg."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql.replace("%s", "?"), params)

    def executescript(self, sql: str):
        return self._conn.executescript(sql)



def init_db(db_path: str | None = None) -> None:
    database_url = db_path or get_settings().DATABASE_URL

    if database_url.startswith("sqlite:///") or db_path is not None:
        with get_connection(db_path or database_url) as conn:
            conn.executescript(SCHEMA_SQLITE)
        return

    with get_connection() as conn:
        conn.execute(SCHEMA_POSTGRES)
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")
