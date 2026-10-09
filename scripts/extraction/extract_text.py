"""
Plain .txt extraction (Phase 3).

Handles encoding detection fallback (UTF-8 -> UTF-8-BOM -> CP1252 ->
latin-1) since government-sourced .txt files are not reliably UTF-8.

Usage:
    python scripts/extraction/extract_text.py path/to/file.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

ENCODINGS_TO_TRY = ("utf-8", "utf-8-sig", "cp1252", "latin-1")


class TextExtractionError(RuntimeError):
    pass


def extract_text(path: str | Path) -> str:
    path = Path(path)
    if not path.exists():
        raise TextExtractionError(f"File not found: {path}")

    raw = path.read_bytes()
    if not raw.strip():
        raise TextExtractionError(f"File '{path}' is empty.")

    last_error: Exception | None = None
    for encoding in ENCODINGS_TO_TRY:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
            continue

    raise TextExtractionError(
        f"Could not decode '{path}' with any of {ENCODINGS_TO_TRY}: {last_error}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python extract_text.py <file.txt>", file=sys.stderr)
        sys.exit(1)
    try:
        text = extract_text(sys.argv[1])
    except TextExtractionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Extracted {len(text)} chars.")
    print("--- first 500 chars ---")
    print(text[:500])
