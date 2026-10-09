"""
Chat endpoint.

Phase 1: stubbed so the frontend has a real contract to build against.
Phase 6: wired to the basic RAG pipeline (rag_service.answer_question).
Phase 8: wired to the Phase 7 improved pipeline
(rag_service.answer_question_improved) -- language/domain/jurisdiction/
ambiguity detection, query reformulation, metadata filtering, reranking.
Phase 10: conversation_id is now real (created/reused via
app.database.repositories), both turns of every exchange are persisted,
and prior turns are loaded and passed into
`answer_question_improved(history=...)` so follow-up questions ("What
is the punishment?") get resolved against real conversation history
instead of the Phase 6-9 no-op passthrough.

Phase 12: `document_ids` is now wired into
`answer_question_improved(document_ids=...)` -- if the message names
uploaded documents, their content is retrieved alongside (or instead
of, if the knowledge base has nothing relevant) the legal knowledge
base. Each referenced document is opportunistically linked to this
conversation (display purposes only -- retrieval itself is scoped by
document_id, not conversation_id).

Auth: requires a logged-in user; conversations are now scoped to
req.conversation_id, owned by user_id from the JWT.

Phase 15: guard against a conversation being deleted (e.g. from the
sidebar) while a request is still generating a reply -- the RAG call
can take several seconds (longer under LLM retries), so the
conversation row may no longer exist by the time we try to persist
the assistant's turn. In that case we still return the generated
answer to the caller, just without a conversation_id, instead of
letting the foreign-key failure surface as a 500.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import get_current_user_id
from app.config import get_settings
from app.database import repositories as repo
from app.services.rag_service import answer_question_improved

router = APIRouter()


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(..., min_length=1)
    language: str = "auto"  # "auto" | "en" | "kn" | "hi"
    document_ids: list[str] = []


class SourceItem(BaseModel):
    title: str
    section: str | None = None
    domain: str | None = None
    source_type: str | None = None
    # Phase 14 (spec sections 27-28): "act" | "case" | "rule" | "uploaded_document"
    # -- lets the frontend cite a case as "Case name — Year" instead of
    # showing it like a section-less Act (see rag_service._build_sources).
    document_type: str | None = None
    year: int | None = None


class ClassificationInfo(BaseModel):
    language: str
    domain: str | None = None
    jurisdiction: str
    state: str | None = None
    court: str | None = None
    query_type: str
    ambiguity: bool
    confidence: float


class ChatResponse(BaseModel):
    answer: str
    language: str
    sources: list[SourceItem] = []
    conversation_id: str | None = None
    classification: ClassificationInfo | None = None
    ambiguous: bool = False


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user_id: str = Depends(get_current_user_id)):
    settings = get_settings()

    conversation = repo.get_or_create_conversation(req.conversation_id, user_id=user_id)

    # Prior turns only -- the current message is saved separately right
    # after, so it's never duplicated into its own reformulation context.
    history = repo.get_recent_history(conversation.id, settings.MAX_HISTORY_TURNS)

    repo.add_message(conversation.id, role="user", content=req.message)

    for doc_id in req.document_ids:
        repo.attach_document_to_conversation(doc_id, conversation.id)

    result = answer_question_improved(
        message=req.message, language=req.language, history=history, document_ids=req.document_ids,
    )

    # Phase 15: the conversation may have been deleted (e.g. from the
    # sidebar) while answer_question_improved was still running --
    # check before persisting the assistant's turn so a stale
    # conversation_id can't trip the messages.conversation_id foreign
    # key and turn a normal delete into a 500.
    still_exists = repo.get_conversation(conversation.id) is not None

    if still_exists:
        repo.add_message(
            conversation.id,
            role="assistant",
            content=result["answer"],
            language=result["language"],
            sources=result["sources"],
            classification=result.get("classification"),
            ambiguous=result.get("ambiguous", False),
        )

    return ChatResponse(
        answer=result["answer"],
        language=result["language"],
        sources=[SourceItem(**s) for s in result["sources"]],
        conversation_id=conversation.id if still_exists else None,
        classification=ClassificationInfo(**result["classification"]) if result.get("classification") else None,
        ambiguous=result.get("ambiguous", False),
    )