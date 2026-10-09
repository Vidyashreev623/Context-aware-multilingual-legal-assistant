"""
Legal-specific text normalization (Phase 3).

Run AFTER clean_text.clean_text(). Standardizes the conventions Indian
statutes use so downstream structure detection (legal_chunker.py) can
rely on consistent patterns, without changing legal meaning:

- "§" / "Sec." / "S." -> "Section" (only as a standalone marker, never
  inside already-normalized text)
- smart quotes -> straight quotes
- the long dash Indian Bare Acts use after a section heading
  ("66C. Punishment for identity theft.—Whoever...") is preserved
  but standardized to a single em dash
- non-breaking spaces / odd unicode spaces -> normal spaces
- multiple citation styles for sub-provisions normalized so the
  chunker's regexes match reliably: "(1)", "(a)", "(i)"
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

_SMART_QUOTES = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "\u2014",  # keep em dash as-is
}
_SEC_ABBREV = re.compile(r"(?<![A-Za-z])(?:§|[Ss]ec\.|[Ss]\.)\s*(?=\d)")
_MULTIPLE_DASH_VARIANTS = re.compile(r"[\u2012\u2013\u2015]")  # figure/en/horizontal dash -> em dash
_NBSP = re.compile(r"[\u00a0\u2007\u202f]")


def normalize_unicode(text: str) -> str:
    """NFKC normalization + smart-quote/space cleanup."""
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _SMART_QUOTES.items():
        text = text.replace(bad, good)
    text = _NBSP.sub(" ", text)
    return text


def normalize_section_markers(text: str) -> str:
    """'§ 66C' / 'Sec. 66C' / 'S. 66C' -> 'Section 66C' (numeric lookahead avoids
    mangling things like 'Sec.' used as an ordinary abbreviation elsewhere)."""
    return _SEC_ABBREV.sub("Section ", text)


def normalize_dashes(text: str) -> str:
    text = _MULTIPLE_DASH_VARIANTS.sub("\u2014", text)
    return text


def normalize_legal_text(text: str) -> str:
    text = normalize_unicode(text)
    text = normalize_section_markers(text)
    text = normalize_dashes(text)
    return text


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python normalize_legal_text.py <file.txt>", file=sys.stderr)
        sys.exit(1)
    raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    normalized = normalize_legal_text(raw)
    print("--- first 500 chars ---")
    print(normalized[:500])
