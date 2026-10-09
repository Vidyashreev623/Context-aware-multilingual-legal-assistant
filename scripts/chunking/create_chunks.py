"""
Turns extracted+cleaned text into the final chunk JSON records
(spec section 15's schema), using legal_chunker.py for structure
detection.

    chunk = {
      "chunk_id": "it_act_2000_66c_001",
      "domain": "cyber",
      "document_type": "act",
      "act_name": "Information Technology Act, 2000",
      "section": "66C",
      "chapter": "...",
      "jurisdiction": "India",
      "language": "en",
      "text": "...",
      "source": "...",
      "year": 2000
    }

Also usable as a CLI for testing a single file end-to-end:

    python scripts/chunking/create_chunks.py <file> \\
        --domain cyber --document-type act \\
        --act-name "Information Technology Act, 2000" \\
        --jurisdiction India --language en --year 2000 --source "..."
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.chunking.legal_chunker import (
    parse_legal_structure,
    generic_paragraph_chunks,
    split_long_unit,
)

REQUIRED_FIELDS = (
    "chunk_id", "domain", "document_type", "act_name", "section",
    "chapter", "jurisdiction", "language", "text", "source", "year",
)
VALID_DOCUMENT_TYPES = {"act", "case", "rule", "uploaded_document"}
MAX_CHUNK_CHARS = 1200


@dataclass
class DocumentMetadata:
    """Everything about a source document that a chunk needs to carry.
    Never fabricated — must come from data_collection/<domain>/manifest.json
    or an explicit per-file .meta.json sidecar (see scripts/processing/_pipeline_base.py).
    """
    domain: str
    document_type: str
    act_name: str
    jurisdiction: str
    language: str
    source: str
    year: int | None = None
    doc_id: str | None = None

    def __post_init__(self):
        if self.document_type not in VALID_DOCUMENT_TYPES:
            raise ValueError(
                f"document_type must be one of {sorted(VALID_DOCUMENT_TYPES)}, got '{self.document_type}'"
            )
        if not self.doc_id:
            self.doc_id = slugify(self.act_name)


def slugify(value: str, max_len: int = 40) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    value = re.sub(r"_+", "_", value)
    return value[:max_len] or "doc"


def validate_chunk(chunk: dict) -> list[str]:
    """Returns a list of validation error strings (empty = valid)."""
    errors = []
    for field_name in REQUIRED_FIELDS:
        if field_name not in chunk:
            errors.append(f"missing field '{field_name}'")
    if "text" in chunk and not str(chunk["text"]).strip():
        errors.append("'text' is empty")
    if "document_type" in chunk and chunk["document_type"] not in VALID_DOCUMENT_TYPES:
        errors.append(f"invalid document_type '{chunk['document_type']}'")
    if "chunk_id" in chunk and not chunk["chunk_id"]:
        errors.append("'chunk_id' is empty")
    return errors


def _build_chunk(
    text: str,
    meta: DocumentMetadata,
    section: str | None,
    chapter: str | None,
    running_index: int,
) -> dict:
    section_part = slugify(section) if section else "full"
    chunk_id = f"{meta.doc_id}_{section_part}_{running_index:03d}"
    return {
        "chunk_id": chunk_id,
        "domain": meta.domain,
        "document_type": meta.document_type,
        "act_name": meta.act_name,
        "section": section,
        "chapter": chapter,
        "jurisdiction": meta.jurisdiction,
        "language": meta.language,
        "text": text,
        "source": meta.source,
        "year": meta.year,
    }


def chunk_document(text: str, meta: DocumentMetadata, max_chars: int = MAX_CHUNK_CHARS) -> list[dict]:
    """
    Main entry point: cleaned+normalized text -> list of validated
    chunk dicts. Chooses structured vs. fallback chunking automatically.
    """
    units = parse_legal_structure(text)
    chunks: list[dict] = []
    running_index = 0

    if units:
        for unit in units:
            for sub_unit in split_long_unit(unit, max_chars):
                section_label = sub_unit.section
                if sub_unit.subsection:
                    section_label = f"{sub_unit.section}({sub_unit.subsection})"
                if sub_unit.clause:
                    section_label = f"{section_label}({sub_unit.clause})"
                chunks.append(_build_chunk(
                    text=sub_unit.text,
                    meta=meta,
                    section=section_label,
                    chapter=sub_unit.chapter,
                    running_index=running_index,
                ))
                running_index += 1
    else:
        for piece in generic_paragraph_chunks(text, max_chars=max_chars):
            chunks.append(_build_chunk(
                text=piece,
                meta=meta,
                section=None,
                chapter=None,
                running_index=running_index,
            ))
            running_index += 1

    errors_by_chunk = {c["chunk_id"]: validate_chunk(c) for c in chunks}
    bad = {cid: errs for cid, errs in errors_by_chunk.items() if errs}
    if bad:
        raise ValueError(f"Invalid chunks produced for '{meta.act_name}': {bad}")

    return chunks


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Chunk a single cleaned legal text file (testing/debug tool).")
    parser.add_argument("file", help="Path to a .txt file of already-extracted, cleaned text")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--document-type", required=True, choices=sorted(VALID_DOCUMENT_TYPES))
    parser.add_argument("--act-name", required=True)
    parser.add_argument("--jurisdiction", default="India")
    parser.add_argument("--language", default="en")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", default=None, help="Optional path to write chunks as JSONL")
    args = parser.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    meta = DocumentMetadata(
        domain=args.domain, document_type=args.document_type, act_name=args.act_name,
        jurisdiction=args.jurisdiction, language=args.language, source=args.source, year=args.year,
    )
    chunks = chunk_document(text, meta)
    print(f"Produced {len(chunks)} chunk(s).")
    for c in chunks[:3]:
        print(json.dumps(c, indent=2, ensure_ascii=False)[:600])
        print("...")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"Wrote {len(chunks)} chunks to {out_path}")


if __name__ == "__main__":
    _cli()
