"""
Plain dataclasses describing the shape of a row in each table
(conversations, messages, documents, users, email_verification_codes).

Not an ORM model on purpose. These dataclasses are what the
repositories return, so API routes never touch raw SQL row shapes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Conversation:
    id: str
    title: str
    created_at: str
    updated_at: str
    user_id: str | None = None

    @staticmethod
    def from_row(row) -> "Conversation":
        return Conversation(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            user_id=row["user_id"] if "user_id" in row.keys() else None,
        )


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: str
    language: str | None = None
    sources: list[dict] = field(default_factory=list)
    classification: dict | None = None
    ambiguous: bool = False

    @staticmethod
    def from_row(row) -> "Message":
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            language=row["language"],
            sources=json.loads(row["sources_json"]) if row["sources_json"] else [],
            classification=json.loads(row["classification_json"]) if row["classification_json"] else None,
            ambiguous=bool(row["ambiguous"]),
        )


@dataclass
class Document:
    """One uploaded file's processing record -- the actual chunks and
    embeddings live in the vector store tagged with document_id=this id."""
    id: str
    filename: str
    file_type: str
    status: str  # "processing" | "processed" | "failed"
    uploaded_at: str
    language: str | None = None
    error: str | None = None
    chunk_count: int = 0
    conversation_id: str | None = None

    @staticmethod
    def from_row(row) -> "Document":
        return Document(
            id=row["id"],
            filename=row["filename"],
            file_type=row["file_type"],
            status=row["status"],
            uploaded_at=row["uploaded_at"],
            language=row["language"],
            error=row["error"],
            chunk_count=row["chunk_count"],
            conversation_id=row["conversation_id"],
        )


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    created_at: str
    # Shown in the profile menu. Nullable because accounts created
    # before this column existed have no name.
    name: str | None = None

    @staticmethod
    def from_row(row) -> "User":
        return User(
            id=row["id"],
            email=row["email"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            name=row["name"] if "name" in row.keys() else None,
        )


@dataclass
class EmailVerificationCode:
    """One row per outstanding (or just-verified) OTP code. Used by both
    signup email verification and forgot-password, told apart by `purpose`.
    Created at "request code", updated at "verify code" (gets a
    verified_token), deleted once the final step consumes it."""
    id: str
    email: str
    code_hash: str
    purpose: str  # "signup" | "reset"
    verified: bool
    verified_token: str | None
    attempts: int
    expires_at: str
    created_at: str

    @staticmethod
    def from_row(row) -> "EmailVerificationCode":
        return EmailVerificationCode(
            id=row["id"],
            email=row["email"],
            code_hash=row["code_hash"],
            purpose=row["purpose"],
            verified=bool(row["verified"]),
            verified_token=row["verified_token"],
            attempts=row["attempts"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
        )