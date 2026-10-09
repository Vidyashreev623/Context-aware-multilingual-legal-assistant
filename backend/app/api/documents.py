"""
Document listing/deletion endpoints (Phase 12, spec section 39):

    GET    /api/documents
    DELETE /api/documents/{id}

Kept in a separate module from upload.py (which only handles POST
/upload) since these operate on already-processed documents rather
than the upload pipeline itself.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.database import repositories as repo
from app.services.document_service import delete_document

router = APIRouter()


class DocumentOut(BaseModel):
    document_id: str
    filename: str
    file_type: str
    status: str
    language: str | None = None
    chunk_count: int = 0
    error: str | None = None
    uploaded_at: str


@router.get("/documents", response_model=list[DocumentOut])
def list_documents():
    docs = repo.list_documents()
    return [
        DocumentOut(
            document_id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            status=d.status,
            language=d.language,
            chunk_count=d.chunk_count,
            error=d.error,
            uploaded_at=d.uploaded_at,
        )
        for d in docs
    ]


@router.delete("/documents/{document_id}")
def remove_document(document_id: str):
    settings = get_settings()
    deleted = delete_document(document_id, uploads_dir=settings.UPLOADS_DIR)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": document_id}
