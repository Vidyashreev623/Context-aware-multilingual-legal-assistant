"""
PDF text extraction (Phase 3).

Extracts raw text from PDF files, page by page, using pypdf.
Deliberately does NOT clean or normalize text — that is
scripts/cleaning/*.py's job. This module's only responsibility is
getting text (and basic per-page structure) out of a PDF.

Usage:
    python scripts/extraction/extract_pdf.py path/to/file.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path


class PdfExtractionError(RuntimeError):
    pass


def extract_pdf_pages(path: str | Path) -> list[str]:
    """
    Returns a list of raw text strings, one per page.
    Raises PdfExtractionError if the file can't be read or pypdf
    isn't installed.
    """
    path = Path(path)
    if not path.exists():
        raise PdfExtractionError(f"File not found: {path}")

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfExtractionError(
            "pypdf is not installed. Run: pip install -r backend/requirements.txt"
        ) from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pragma: no cover - depends on malformed input
        raise PdfExtractionError(f"Could not open PDF '{path}': {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise PdfExtractionError(
                f"PDF '{path}' is encrypted and could not be decrypted with an empty password."
            ) from exc

    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover
            text = ""
            print(f"  [warn] page {i + 1} of {path.name} failed to extract: {exc}", file=sys.stderr)
        pages.append(text)

    if not any(p.strip() for p in pages):
        raise PdfExtractionError(
            f"No extractable text found in '{path}'. It may be a scanned/image PDF "
            f"that needs OCR (not yet implemented — see spec section 29 'optionally support images/OCR later')."
        )

    return pages


def extract_pdf_text(path: str | Path, page_separator: str = "\n\n") -> str:
    """Convenience wrapper: whole document as one string, pages joined."""
    return page_separator.join(extract_pdf_pages(path))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python extract_pdf.py <file.pdf>", file=sys.stderr)
        sys.exit(1)
    try:
        pages = extract_pdf_pages(sys.argv[1])
    except PdfExtractionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Extracted {len(pages)} page(s), {sum(len(p) for p in pages)} chars total.")
    print("--- first 500 chars ---")
    print("\n\n".join(pages)[:500])
