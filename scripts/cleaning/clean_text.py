"""
General-purpose text cleaning (Phase 3).

Removes the noise that PDF/DOCX extraction typically introduces:
repeated headers/footers, page-number lines, hyphenated line-wrap
breaks, stray control characters, and excess whitespace.

Deliberately generic — legal-specific normalization (§ symbols,
"Provided that", ordinal section numbering, etc.) lives in
normalize_legal_text.py so the two concerns stay separable and
independently testable.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

# Matches common page-number-only lines: "12", "- 12 -", "Page 12", "Page 12 of 40"
_PAGE_NUMBER_LINE = re.compile(
    r"^\s*(?:-{0,2}\s*)?(?:page\s+)?\d{1,4}(?:\s+of\s+\d{1,4})?\s*(?:-{0,2})?\s*$",
    re.IGNORECASE,
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")
_HYPHEN_LINEBREAK = re.compile(r"(\w)-\n(\w)")  # "contrac-\ntual" -> "contractual"
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def strip_control_characters(text: str) -> str:
    return _CONTROL_CHARS.sub("", text)


def dehyphenate_linebreaks(text: str) -> str:
    """Rejoins words that were hyphen-broken across a line wrap in the source PDF."""
    return _HYPHEN_LINEBREAK.sub(r"\1\2", text)


def remove_page_number_lines(text: str) -> str:
    lines = text.split("\n")
    kept = [ln for ln in lines if not _PAGE_NUMBER_LINE.match(ln)]
    return "\n".join(kept)


def detect_repeated_lines(text: str, min_occurrences: int = 3, max_line_len: int = 90) -> set[str]:
    """
    Finds short lines (typically running headers/footers, e.g. an Act's
    title repeated on every page) that occur suspiciously often.
    Only considers non-trivial lines to avoid flagging blank lines or
    single punctuation marks.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    candidates = [ln for ln in lines if 3 <= len(ln) <= max_line_len]
    counts = Counter(candidates)
    return {line for line, n in counts.items() if n >= min_occurrences}


def remove_repeated_headers_footers(text: str) -> str:
    repeated = detect_repeated_lines(text)
    if not repeated:
        return text
    lines = text.split("\n")
    return "\n".join(ln for ln in lines if ln.strip() not in repeated)


def normalize_whitespace(text: str) -> str:
    text = _TRAILING_SPACES.sub("\n", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def clean_text(text: str, remove_headers_footers: bool = True) -> str:
    """Full cleaning pipeline, in the order that matters."""
    text = strip_control_characters(text)
    text = dehyphenate_linebreaks(text)
    text = remove_page_number_lines(text)
    if remove_headers_footers:
        text = remove_repeated_headers_footers(text)
    text = normalize_whitespace(text)
    return text


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clean_text.py <file.txt>", file=sys.stderr)
        sys.exit(1)
    raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    cleaned = clean_text(raw)
    print(f"Before: {len(raw)} chars -> After: {len(cleaned)} chars")
    print("--- first 500 chars ---")
    print(cleaned[:500])
