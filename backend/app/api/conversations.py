"""
Conversation history endpoints.
Phase 10: backed by real SQLite persistence.
Auth: every route now requires a logged-in user and is scoped to
their own conversations only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user_id
from app.database import repositories as repo

router = APIRouter()


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    language: str | None = None
    sources: list[dict] = []
    classification: dict | None = None
    ambiguous: bool = False
    timestamp: str


class ConversationDetail(BaseModel):
    conversation_id: str
    title: str
    messages: list[MessageOut]


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(user_id: str = Depends(get_current_user_id)):
    return [
        ConversationSummary(conversation_id=c.id, title=c.title, updated_at=c.updated_at)
        for c in repo.list_conversations(user_id=user_id)
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, user_id: str = Depends(get_current_user_id)):
    conv = repo.get_conversation(conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = repo.get_messages(conversation_id)
    return ConversationDetail(
        conversation_id=conv.id,
        title=conv.title,
        messages=[
            MessageOut(
                id=m.id, role=m.role, content=m.content, language=m.language,
                sources=m.sources, classification=m.classification,
                ambiguous=m.ambiguous, timestamp=m.created_at,
            )
            for m in messages
        ],
    )


@router.post("/conversations", response_model=ConversationSummary)
def create_conversation(user_id: str = Depends(get_current_user_id)):
    conv = repo.create_conversation(user_id=user_id)
    return ConversationSummary(conversation_id=conv.id, title=conv.title, updated_at=conv.updated_at)


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(conversation_id: str, body: RenameRequest, user_id: str = Depends(get_current_user_id)):
    conv = repo.get_conversation(conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    updated = repo.rename_conversation(conversation_id, body.title)
    return ConversationSummary(conversation_id=updated.id, title=updated.title, updated_at=updated.updated_at)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user_id: str = Depends(get_current_user_id)):
    conv = repo.get_conversation(conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    repo.delete_conversation(conversation_id)
    return {"deleted": conversation_id}