"""
Document upload / document-scoped RAG service (Phase 12, spec sections
29-31).

Reuses the exact Phase 3-5 pipeline the legal knowledge base itself is
built with (Rule 9: "keep RAG components modular" -- an uploaded PDF
and an Act PDF go through the same extract -> clean -> normalize ->
chunk -> embed -> index steps, just with different DocumentMetadata):

    Upload
     |
     v
    extract_any()            (scripts/extraction, Phase 3)
     |
     v
    clean_text()              (scripts/cleaning, Phase 3)
     |
     v
    normalize_legal_text()    (scripts/cleaning, Phase 3)
     |
     v
    detect_language()         (language_service.py, Phase 7)
     |
     v
    chunk_document()          (scripts/chunking, Phase 3 -- falls back
     |                         to generic_paragraph_chunks() for
     |                         uploaded documents, since a rental
     |                         agreement has no Act/Section structure)
     v
    embed_batch()              (embedding_service.py, Phase 4)
     |
     v
    VectorStore.add()          (vector_store_service.py, Phase 5,
                                 tagged with document_id metadata)

Every uploaded-document chunk is stored in the SAME vector index as
the legal knowledge base (spec section 42 already chose "one index
with metadata filters" over 13+ separate collections) -- a
`document_id` metadata field is what makes retrieval scoped to "only
this document" rather than mixed in with everything else. Domain is
set to the fixed value "uploaded_documents" (not one of the 13 legal
domains) so an uploaded file can never accidentally match a
domain-filtered legal-knowledge-base query (Phase 7's
build_metadata_filter), and vice versa.

This module intentionally does NOT call Gemini -- that merge (spec
section 31: "Uploaded Document + Indian Legal Database -> Gemini")
happens in rag_service.py, which is the one place that already owns
the LLM call and context-budget logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.extraction.extract_any import (
    extract_any,
    UnsupportedFileTypeError,
)
from scripts.extraction.extract_pdf import PdfExtractionError
from scripts.extraction.extract_docx import DocxExtractionError
from scripts.extraction.extract_text import TextExtractionError
from scripts.cleaning.clean_text import clean_text
from scripts.cleaning.normalize_legal_text import normalize_legal_text
from scripts.chunking.create_chunks import chunk_document, DocumentMetadata

from app.database import repositories as repo
from app.services.embedding_service import EmbeddingProvider, get_embedding_provider
from app.services.language_service import detect_language
from app.services.vector_store_service import (
    SearchResult,
    VectorRecord,
    VectorStore,
    get_vector_store,
)

UPLOADED_DOMAIN = "uploaded_documents"
UPLOADED_DOCUMENT_TYPE = "uploaded_document"

# Extraction-layer failures a corrupt/unreadable/empty upload can raise.
# Caught here (not in the API route) so upload.py only has to know
# "processing failed", not every extractor's exception type.
EXTRACTION_ERRORS = (
    UnsupportedFileTypeError,
    PdfExtractionError,
    DocxExtractionError,
    TextExtractionError,
)


class DocumentProcessingError(RuntimeError):
    """Raised when extraction/chunking/embedding fails for an uploaded
    file that already passed upload.py's type/size validation (e.g. a
    scanned/image-only PDF with no extractable text, or a corrupt
    file). Carries a message safe to show directly to the user (spec
    section 50: never a raw stack trace)."""


def process_uploaded_document(
    document_id: str,
    file_path: str | Path,
    filename: str,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
) -> dict:
    """
    Runs the full spec section 29 pipeline for one uploaded file and
    indexes its chunks. Returns
        {"chunk_count": int, "language": str}
    on success. Raises DocumentProcessingError on failure -- callers
    should catch this and call repo.mark_document_failed(...).

    Does NOT touch the `documents` SQLite row itself (repo.
    create_document / mark_document_processed) -- that's the caller's
    job (api/upload.py), so this function stays testable without a
    database.
    """
    embedder = embedding_provider or get_embedding_provider()
    store = vector_store or get_vector_store()

    try:
        raw_text = extract_any(file_path)
    except EXTRACTION_ERRORS as exc:
        raise DocumentProcessingError(
            f"Unable to process document '{filename}': {exc}"
        ) from exc

    if not raw_text or not raw_text.strip():
        raise DocumentProcessingError(
            f"'{filename}' contains no extractable text (it may be a scanned "
            "image with no text layer, or empty)."
        )

    cleaned = clean_text(raw_text)
    normalized = normalize_legal_text(cleaned)
    language = detect_language(normalized[:2000])  # a prefix is enough to tell en/hi/kn apart

    meta = DocumentMetadata(
        domain=UPLOADED_DOMAIN,
        document_type=UPLOADED_DOCUMENT_TYPE,
        act_name=filename,
        jurisdiction="N/A",
        language=language,
        source=f"User-uploaded document: {filename}",
        year=None,
        doc_id=document_id,  # keeps chunk_ids stable/unique per upload, not per filename
    )

    try:
        chunks = chunk_document(normalized, meta)
    except ValueError as exc:
        raise DocumentProcessingError(f"Unable to process document '{filename}': {exc}") from exc

    if not chunks:
        raise DocumentProcessingError(f"'{filename}' produced no usable text chunks.")

    texts = [c["text"] for c in chunks]
    vectors = embedder.embed_batch(texts)

    records = [
        VectorRecord(
            chunk_id=c["chunk_id"],
            text=c["text"],
            embedding=vector,
            domain=c["domain"],
            document_type=c["document_type"],
            act_name=c["act_name"],
            section=c["section"],
            chapter=c["chapter"],
            jurisdiction=c["jurisdiction"],
            language=c["language"],
            source=c["source"],
            year=c["year"],
            document_id=document_id,
        )
        for c, vector in zip(chunks, vectors)
    ]
    store.add(records)
    store.persist()

    return {"chunk_count": len(records), "language": language}


def retrieve_document_context(
    document_ids: list[str],
    query_embedding: list[float],
    top_k: int,
    vector_store: VectorStore | None = None,
) -> list[SearchResult]:
    """
    Spec section 31: retrieves the most relevant chunks from the given
    uploaded document(s) for one query.

    Queries one document_id at a time (rather than a single `where`
    with an $in-style operator) because VectorStore.filter/search's
    `where` contract across BOTH backends (Chroma and the FAISS
    fallback) is documented and implemented as flat exact-match
    equality (see FAISSVectorStore._matches) -- adding multi-value
    matching would mean diverging that contract per-backend. Uploaded
    documents are typically one-to-a-few per conversation, so N small
    searches merged in Python costs nothing meaningful in practice.
    """
    if not document_ids:
        return []
    store = vector_store or get_vector_store()
    merged: list[SearchResult] = []
    for doc_id in document_ids:
        merged.extend(store.search(query_embedding, top_k=top_k, where={"document_id": doc_id}))
    merged.sort(key=lambda r: r.score, reverse=True)
    return merged[:top_k]


def delete_document(
    document_id: str,
    uploads_dir: str | Path,
    vector_store: VectorStore | None = None,
    db_path: str | None = None,
) -> bool:
    """
    Spec section 39's DELETE /api/documents/{id}: removes the
    document's chunks from the vector store, its stored file from
    disk, and its `documents` row. Returns False if the document
    didn't exist. `db_path` is test-only (see repositories.py) --
    production callers (api/documents.py) never pass it.
    """
    doc = repo.get_document(document_id, db_path=db_path)
    if doc is None:
        return False

    store = vector_store or get_vector_store()
    matches = store.filter({"document_id": document_id})
    if matches:
        store.delete([m["chunk_id"] for m in matches])
        store.persist()

    for existing in Path(uploads_dir).glob(f"{document_id}.*"):
        existing.unlink(missing_ok=True)

    repo.delete_document_record(document_id, db_path=db_path)
    return True
