"""
Repository for email_verification_codes -- the OTP codes behind both
signup email verification and forgot-password. Kept separate from
user_repository.py (Rule 9): a code's lifecycle (request -> verify ->
consume -> delete) is its own concern.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.database.database import get_connection
from app.database.models import EmailVerificationCode

CODE_TTL_MINUTES = 10            # how long the emailed code is valid
VERIFIED_TOKEN_TTL_MINUTES = 15  # window to finish "set password" after verifying
MAX_ATTEMPTS = 5                 # wrong guesses allowed per code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def create_code(email: str, code_hash: str, purpose: str, db_path: str | None = None) -> EmailVerificationCode:
    """Replaces any earlier code for this (email, purpose): only one
    outstanding code per flow, so an old code dies when a new one is sent."""
    delete_codes_for(email, purpose, db_path=db_path)
    record = EmailVerificationCode(
        id=_new_id(),
        email=email.lower().strip(),
        code_hash=code_hash,
        purpose=purpose,
        verified=False,
        verified_token=None,
        attempts=0,
        expires_at=_iso(_now() + timedelta(minutes=CODE_TTL_MINUTES)),
        created_at=_iso(_now()),
    )
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO email_verification_codes
               (id, email, code_hash, purpose, verified, verified_token, attempts, expires_at, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (record.id, record.email, record.code_hash, record.purpose, 0, None, 0,
             record.expires_at, record.created_at),
        )
    return record


def get_pending_code(email: str, purpose: str, db_path: str | None = None) -> EmailVerificationCode | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT * FROM email_verification_codes
               WHERE email = %s AND purpose = %s AND verified = 0
               ORDER BY created_at DESC LIMIT 1""",
            (email.lower().strip(), purpose),
        ).fetchone()
    if not row:
        return None
    record = EmailVerificationCode.from_row(row)
    if record.expires_at < _iso(_now()):
        return None
    return record


def increment_attempts(code_id: str, db_path: str | None = None) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "UPDATE email_verification_codes SET attempts = attempts + 1 WHERE id = %s RETURNING attempts",
            (code_id,),
        ).fetchone()
    return row["attempts"] if row else MAX_ATTEMPTS


def mark_verified(code_id: str, verified_token: str, db_path: str | None = None) -> None:
    new_expiry = _iso(_now() + timedelta(minutes=VERIFIED_TOKEN_TTL_MINUTES))
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE email_verification_codes
               SET verified = 1, verified_token = %s, expires_at = %s
               WHERE id = %s""",
            (verified_token, new_expiry, code_id),
        )


def get_verified_code(
    email: str, purpose: str, verified_token: str, db_path: str | None = None
) -> EmailVerificationCode | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT * FROM email_verification_codes
               WHERE email = %s AND purpose = %s AND verified = 1 AND verified_token = %s
               ORDER BY created_at DESC LIMIT 1""",
            (email.lower().strip(), purpose, verified_token),
        ).fetchone()
    if not row:
        return None
    record = EmailVerificationCode.from_row(row)
    if record.expires_at < _iso(_now()):
        return None
    return record


def delete_codes_for(email: str, purpose: str, db_path: str | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM email_verification_codes WHERE email = %s AND purpose = %s",
            (email.lower().strip(), purpose),
        )


def seconds_since_last_code(email: str, purpose: str, db_path: str | None = None) -> float | None:
    """Backs the resend cooldown. None = no earlier code exists."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT created_at FROM email_verification_codes
               WHERE email = %s AND purpose = %s
               ORDER BY created_at DESC LIMIT 1""",
            (email.lower().strip(), purpose),
        ).fetchone()
    if not row:
        return None
    return (_now() - datetime.fromisoformat(row["created_at"])).total_seconds()
