"""
Dispatcher: picks the right extractor (extract_pdf / extract_docx /
extract_text) based on file extension. Used by the domain processing
pipeline (scripts/processing/_pipeline_base.py) so it doesn't need to
know about individual extractors.
"""
from __future__ import annotations

from pathlib import Path

from scripts.extraction.extract_pdf import extract_pdf_text, PdfExtractionError
from scripts.extraction.extract_docx import extract_docx_text, DocxExtractionError
from scripts.extraction.extract_text import extract_text, TextExtractionError
from scripts.extraction.extract_html import extract_html_text, HtmlExtractionError

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".html", ".htm"}


class UnsupportedFileTypeError(RuntimeError):
    pass


def extract_any(path: str | Path) -> str:
    """Extract raw text from a .pdf, .docx, .html, or .txt file."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix == ".docx":
        return extract_docx_text(path)
    if suffix in (".html", ".htm"):
        return extract_html_text(path)
    if suffix == ".txt":
        return extract_text(path)

    raise UnsupportedFileTypeError(
        f"Unsupported file type '{suffix}' for '{path}'. "
        f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )
