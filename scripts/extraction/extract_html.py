"""
HTML text extraction (Phase 3).

Many government legal sources (India Code, MeitY, ministry portals) serve
the Act/Rule text as an HTML page rather than a PDF. Strips markup and
returns visible text only, dropping script/style/nav/footer noise. Like
extract_pdf.py / extract_docx.py, this does not clean or normalize the
legal text itself — that is scripts/cleaning/*.py's job.

Usage:
    python scripts/extraction/extract_html.py path/to/file.html
"""
from __future__ import annotations

import sys
from pathlib import Path

NOISE_TAGS = ("script", "style", "nav", "header", "footer", "noscript")
BLOCK_TAGS = ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6",
              "td", "th", "blockquote", "pre", "dd", "dt")


class HtmlExtractionError(RuntimeError):
    pass


def extract_html_text(path: str | Path) -> str:
    path = Path(path)
    if not path.exists():
        raise HtmlExtractionError(f"File not found: {path}")

    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise HtmlExtractionError(
            "beautifulsoup4 is not installed. Run: pip install -r backend/requirements.txt"
        ) from exc

    raw = path.read_bytes()
    if not raw.strip():
        raise HtmlExtractionError(f"File '{path}' is empty.")

    try:
        soup = BeautifulSoup(raw, "html.parser")
    except Exception as exc:  # pragma: no cover - depends on malformed input
        raise HtmlExtractionError(f"Could not parse HTML '{path}': {exc}") from exc

    for tag in soup(NOISE_TAGS):
        tag.decompose()

    # Extract per block-level element and join with a blank line between
    # them — scripts/chunking/legal_chunker.py splits on "\n\n" to find
    # paragraph/section boundaries, so collapsing everything to single
    # newlines here would silently destroy that structure and every
    # document would fall back to one unstructured chunk.
    blocks = soup.find_all(BLOCK_TAGS)
    if blocks:
        paragraphs = [b.get_text(separator=" ", strip=True) for b in blocks]
        text = "\n\n".join(p for p in paragraphs if p)
    else:
        lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
        text = "\n\n".join(line for line in lines if line)

    if not text.strip():
        raise HtmlExtractionError(
            f"No extractable text found in '{path}'. It may be a JS-rendered "
            f"page (text loaded client-side) rather than server-rendered HTML — "
            f"spot-check the raw file before re-fetching."
        )
    return text


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python extract_html.py <file.html>", file=sys.stderr)
        sys.exit(1)
    try:
        text = extract_html_text(sys.argv[1])
    except HtmlExtractionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Extracted {len(text)} chars.")
    print("--- first 500 chars ---")
    print(text[:500])
