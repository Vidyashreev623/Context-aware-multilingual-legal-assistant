"""
Shared logic for domain data processors (Phase 3).

Each domain's `process_<domain>.py` (scripts/processing/) is a thin
wrapper around this module, exactly like `collect_<domain>.py` wraps
`_collector_base.py` — per Rule 7 ("keep data collection separate from
data processing") and Rule 8 ("keep each legal domain separately
organized"), this file intentionally does NOT touch other domains'
data and does NOT do collection. It only turns
`data/raw/<domain>/**` into `data/processed/<domain>/**`.

Pipeline per file (spec section 11):
    RAW DOCUMENT -> TEXT EXTRACTION -> TEXT CLEANING -> STRUCTURE
    DETECTION -> SECTION EXTRACTION -> CHUNKING -> METADATA ->
    VALIDATION -> (embedding/index happen later, in Phase 4/5)

Source-of-truth for a raw file's metadata (act name, jurisdiction,
document type, source URL) is, in priority order:
    1. An explicit sidecar file  <raw file>.meta.json
    2. A matching entry in data_collection/<domain>/manifest.json,
       matched by "document_name"
If neither exists, the file is SKIPPED with a warning rather than
processed with guessed/fabricated metadata (Rule 3).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.extraction.extract_any import extract_any, SUPPORTED_EXTENSIONS, UnsupportedFileTypeError
from scripts.extraction.extract_pdf import PdfExtractionError
from scripts.extraction.extract_docx import DocxExtractionError
from scripts.extraction.extract_text import TextExtractionError
from scripts.cleaning.clean_text import clean_text
from scripts.cleaning.normalize_legal_text import normalize_legal_text
from scripts.chunking.create_chunks import chunk_document, DocumentMetadata

DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DATA_COLLECTION_DIR = REPO_ROOT / "data_collection"

RAW_TYPE_FOLDERS = ("acts", "cases", "sections", "rules")

# manifest.json document_type -> processed-output subfolder (spec section 10's
# processed layout only has acts/cases/sections/rules, but the manifest
# schema allows a wider set of document_type values).
DOC_TYPE_TO_FOLDER = {
    "act": "acts", "constitution": "acts", "amendment": "acts",
    "case": "cases",
    "rules": "rules", "regulation": "rules",
}
# manifest/meta document_type -> the value stored on each chunk
# (create_chunks.VALID_DOCUMENT_TYPES).
DOC_TYPE_TO_CHUNK_TYPE = {
    "act": "act", "constitution": "act", "amendment": "act",
    "case": "case",
    "rules": "rule", "regulation": "rule",
}

_LANG_SUFFIX_RE = re.compile(r"\.(en|hi|kn)\.[^.]+$", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


@dataclass
class ProcessResult:
    processed_files: int = 0
    skipped_files: int = 0
    total_chunks: int = 0
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def load_manifest_by_name(domain: str) -> dict[str, dict]:
    manifest_path = DATA_COLLECTION_DIR / domain / "manifest.json"
    if not manifest_path.exists():
        return {}
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {e["document_name"]: e for e in entries if e.get("verified")}


def detect_language_from_filename(path: Path) -> str | None:
    match = _LANG_SUFFIX_RE.search(path.name)
    return match.group(1).lower() if match else None


def extract_year_from_name(name: str) -> int | None:
    match = _YEAR_RE.search(name)
    return int(match.group(1)) if match else None


def _load_sidecar_meta(raw_file: Path) -> dict:
    sidecar = raw_file.with_suffix(raw_file.suffix + ".meta.json")
    if sidecar.exists():
        return json.loads(sidecar.read_text(encoding="utf-8"))
    return {}


def resolve_document_metadata(
    raw_file: Path, domain: str, type_folder: str, manifest: dict[str, dict]
) -> DocumentMetadata | None:
    """Returns None (and the caller should skip+warn) if no verifiable
    metadata is available for this file."""
    meta = _load_sidecar_meta(raw_file)
    document_name = meta.get("document_name") or raw_file.stem

    manifest_entry = manifest.get(document_name)
    if not manifest_entry and not meta:
        return None

    raw_doc_type = (
        meta.get("document_type")
        or (manifest_entry or {}).get("document_type")
        or ("case" if type_folder == "cases" else "act" if type_folder == "acts" else "rules")
    )
    chunk_doc_type = DOC_TYPE_TO_CHUNK_TYPE.get(raw_doc_type, "act")

    act_name = meta.get("act_name") or document_name
    jurisdiction = meta.get("jurisdiction") or (manifest_entry or {}).get("jurisdiction") or "India"

    if meta.get("source"):
        source = meta["source"]
    elif manifest_entry:
        source = f"{manifest_entry.get('source_name', 'Unknown source')} — {manifest_entry.get('source_url', '')}".strip(" —")
    else:
        source = "Unverified — see data_collection sidecar"

    language = meta.get("language") or detect_language_from_filename(raw_file) or "en"
    year = meta.get("year") or extract_year_from_name(act_name)

    return DocumentMetadata(
        domain=domain,
        document_type=chunk_doc_type,
        act_name=act_name,
        jurisdiction=jurisdiction,
        language=language,
        source=source,
        year=year,
    )


def process_file(raw_file: Path, domain: str, type_folder: str, manifest: dict[str, dict]) -> list[dict]:
    meta = resolve_document_metadata(raw_file, domain, type_folder, manifest)
    if meta is None:
        raise ValueError(
            f"No metadata found for '{raw_file.name}' — add a "
            f"'{raw_file.name}.meta.json' sidecar or a matching manifest.json "
            f"entry (document_name='{raw_file.stem}') before processing. "
            f"Refusing to guess (Rule 3: never fabricate sources)."
        )
    raw_text = extract_any(raw_file)
    cleaned = clean_text(raw_text)
    normalized = normalize_legal_text(cleaned)
    return chunk_document(normalized, meta)


def run_domain_processing(domain: str) -> ProcessResult:
    raw_domain_dir = DATA_RAW_DIR / domain
    processed_domain_dir = DATA_PROCESSED_DIR / domain
    result = ProcessResult()

    if not raw_domain_dir.exists():
        result.warnings.append(f"No raw data directory for domain '{domain}' at {raw_domain_dir}")
        return result

    manifest = load_manifest_by_name(domain)
    combined_chunks: list[dict] = []

    for type_folder in RAW_TYPE_FOLDERS:
        src_dir = raw_domain_dir / type_folder
        if not src_dir.exists():
            continue
        out_dir = processed_domain_dir / type_folder
        out_dir.mkdir(parents=True, exist_ok=True)

        for raw_file in sorted(src_dir.iterdir()):
            if raw_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                chunks = process_file(raw_file, domain, type_folder, manifest)
            except (ValueError, UnsupportedFileTypeError, PdfExtractionError,
                    DocxExtractionError, TextExtractionError) as exc:
                result.skipped_files += 1
                result.warnings.append(f"SKIPPED {raw_file}: {exc}")
                continue

            out_file = out_dir / f"{raw_file.stem}.chunks.jsonl"
            with out_file.open("w", encoding="utf-8") as f:
                for c in chunks:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")

            result.processed_files += 1
            result.total_chunks += len(chunks)
            combined_chunks.extend(chunks)

    if combined_chunks:
        processed_domain_dir.mkdir(parents=True, exist_ok=True)
        combined_path = processed_domain_dir / f"{domain}_all_chunks.jsonl"
        with combined_path.open("w", encoding="utf-8") as f:
            for c in combined_chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    return result


def print_report(domain: str, result: ProcessResult) -> None:
    print(f"\n=== Processing report: {domain} ===")
    print(f"  Files processed : {result.processed_files}")
    print(f"  Files skipped   : {result.skipped_files}")
    print(f"  Chunks produced : {result.total_chunks}")
    for w in result.warnings:
        print(f"  [warn] {w}", file=sys.stderr)
