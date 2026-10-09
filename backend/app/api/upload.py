"""
Document upload endpoint.

Phase 1: stub that validated type/size and stored the file.
Phase 12: real pipeline -- the file is saved, a `documents` row is
created (status="processing"), then document_service.py runs
extraction -> cleaning -> chunking -> embedding -> vector-store
indexing synchronously before responding. Processing a single upload
(a rental agreement, an employment contract) is seconds, not minutes,
so a synchronous response keeps this phase self-contained -- no
polling endpoint or background job queue needed for the "Ready" state
spec section 29 describes.

On failure, the file and its `documents` row are kept with
status="failed" and a user-safe error message (never a stack trace,
spec section 50) rather than being silently deleted, so "Unable to
process document" is something the user (and this endpoint's own
tests) can actually see and reason about.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.config import get_settings
from app.database import repositories as repo
from app.services.document_service import DocumentProcessingError, process_uploaded_document

router = APIRouter()
settings = get_settings()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(settings.ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f} MB). Max {settings.MAX_UPLOAD_MB} MB.",
        )

    document_id = str(uuid.uuid4())
    dest_dir = Path(settings.UPLOADS_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{document_id}{ext}"
    dest_path.write_bytes(contents)

    repo.create_document(document_id, filename=file.filename, file_type=ext.lstrip("."))

    try:
        result = process_uploaded_document(document_id, dest_path, file.filename)
    except DocumentProcessingError as exc:
        repo.mark_document_failed(document_id, str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive: never leak a stack trace
        repo.mark_document_failed(document_id, "Unexpected error while processing the document.")
        raise HTTPException(
            status_code=500, detail="Unable to process document."
        ) from exc

    repo.mark_document_processed(document_id, language=result["language"], chunk_count=result["chunk_count"])

    return {
        "document_id": document_id,
        "filename": file.filename,
        "file_type": ext.lstrip("."),
        "status": "processed",
        "language": result["language"],
        "chunk_count": result["chunk_count"],
    }
