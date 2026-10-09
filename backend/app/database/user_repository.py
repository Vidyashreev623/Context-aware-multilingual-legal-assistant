from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.database.database import get_connection
from app.database.models import User


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def ensure_auth_schema(db_path: str | None = None) -> None:
    """No-op under Postgres -- users table and conversations.user_id
    are created upfront by database.SCHEMA / init_db(). Kept as a stub
    so main.py's startup hook and the auth routes don't need to
    change."""
    pass


def create_user(email: str, password_hash: str, name: str | None = None, db_path: str | None = None) -> User:
    user = User(
        id=_new_id(),
        email=email.lower().strip(),
        password_hash=password_hash,
        created_at=_now(),
        name=name.strip() if name else None,
    )
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, created_at, name) VALUES (%s, %s, %s, %s, %s)",
            (user.id, user.email, user.password_hash, user.created_at, user.name),
        )
    return user


def get_user_by_email(email: str, db_path: str | None = None) -> User | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = %s", (email.lower().strip(),)
        ).fetchone()
    return User.from_row(row) if row else None


def get_user_by_id(user_id: str, db_path: str | None = None) -> User | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    return User.from_row(row) if row else None


def update_password(user_id: str, new_password_hash: str, db_path: str | None = None) -> None:
    """Used by the forgot-password reset step."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_password_hash, user_id),
        )
