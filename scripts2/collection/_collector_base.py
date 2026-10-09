"""
Shared logic for domain data collectors.

Each domain's `collect_<domain>.py` is a thin wrapper around this module —
per Rule 7 ("keep data collection separate from data processing") and
Rule 8 ("keep each legal domain separately organized"), the *logic* is
shared but every domain's *invocation* and *output* stay isolated to its
own folder.

This module deliberately does NOT process, chunk, or embed anything —
that is Phase 3 (scripts/processing/). It only fetches and validates raw
source documents against data_collection/<domain>/manifest.json.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import urllib.request
import urllib.error

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_COLLECTION_DIR = REPO_ROOT / "data_collection"


@dataclass
class SourceEntry:
    source_name: str
    source_url: str
    document_name: str
    domain: str
    document_type: str
    jurisdiction: str
    verified: bool
    verified_date: str


def load_manifest(domain: str) -> list[SourceEntry]:
    manifest_path = DATA_COLLECTION_DIR / domain / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No manifest.json for domain '{domain}' at {manifest_path}. "
            f"Create it first (see data_collection/SOURCE_MANIFEST_SCHEMA.md)."
        )
    raw = json.loads(manifest_path.read_text())
    return [SourceEntry(**item) for item in raw]


def check_url_reachable(url: str, timeout: int = 10) -> tuple[bool, str]:
    """
    Lightweight reachability check (HEAD-ish GET with small timeout).
    Does NOT download the full document — that's a separate, deliberate
    step so a broken/slow source doesn't silently corrupt the manifest.
    """
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "NyayaAI-Collector/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        # Some govt sites reject HEAD/bare GET but are still legitimately reachable
        # for a browser; treat 403 as "reachable but blocks bots" rather than dead.
        return e.code in (200, 403), f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - we want to report *any* failure reason
        return False, str(e)


def run_domain_collection(domain: str) -> None:
    """
    Entry point called by each collect_<domain>.py.
    Validates the manifest and reports status — actual bulk download of
    large PDF/HTML documents is intentionally left as an explicit,
    reviewable step (`--fetch` flag) rather than automatic, since these
    are official government documents that should be fetched deliberately
    and their content spot-checked, not silently bulk-scraped.
    """
    entries = load_manifest(domain)
    print(f"[{domain}] {len(entries)} source(s) in manifest")

    unverified = [e for e in entries if not e.verified]
    if unverified:
        print(f"[{domain}] WARNING: {len(unverified)} unverified source(s) — "
              f"these will NOT be collected until verified=true:")
        for e in unverified:
            print(f"  - {e.document_name} ({e.source_url or 'no URL yet'})")

    verified = [e for e in entries if e.verified]
    for e in verified:
        ok, detail = check_url_reachable(e.source_url)
        status = "OK" if ok else "UNREACHABLE"
        print(f"[{domain}] {status:11s} {e.document_name} -> {e.source_url} ({detail})")

    collected_dir = DATA_COLLECTION_DIR / domain / "collected"
    collected_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{domain}] Manifest check complete. "
          f"Run with document-specific fetch logic to populate {collected_dir}/")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.collection._collector_base <domain>")
        sys.exit(1)
    run_domain_collection(sys.argv[1])
