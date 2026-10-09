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
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import urllib.request
import urllib.error

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_COLLECTION_DIR = REPO_ROOT / "data_collection"

# A real browser UA — many .gov.in hosts 403 on bare urllib/requests UAs
# even though the same URL loads fine in an actual browser.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
}


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


def slugify_filename(value: str, max_len: int = 60) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    value = re.sub(r"_+", "_", value)
    return value[:max_len] or "document"


def fetch_document(entry: SourceEntry, out_dir: Path, timeout: int = 30) -> Path | None:
    """
    Downloads a single verified source into out_dir (data_collection/<domain>/collected/).
    Writes the raw bytes plus a '<file>.meta.json' sidecar carrying the
    manifest's document_name/document_type/jurisdiction/source, so later
    steps never have to guess metadata (Rule 3: never fabricate sources).
    Returns the path written, or None on failure.
    """
    req = urllib.request.Request(entry.source_url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            data = resp.read()
    except urllib.error.HTTPError as e:
        print(f"  [fetch] FAILED {entry.document_name}: HTTP {e.code}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  [fetch] FAILED {entry.document_name}: {e}")
        return None

    if not data:
        print(f"  [fetch] FAILED {entry.document_name}: empty response body")
        return None

    if "pdf" in content_type or entry.source_url.lower().endswith(".pdf"):
        ext = ".pdf"
    elif "html" in content_type or "xml" in content_type:
        ext = ".html"
    else:
        ext = ".bin"
        print(f"  [fetch] WARNING {entry.document_name}: unrecognized content-type "
              f"'{content_type}', saving as .bin — inspect before promoting to data/raw/")

    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify_filename(entry.document_name)
    out_path = out_dir / f"{slug}{ext}"
    out_path.write_bytes(data)

    meta_path = out_dir / f"{out_path.name}.meta.json"
    meta_path.write_text(json.dumps({
        "document_name": entry.document_name,
        "document_type": entry.document_type,
        "jurisdiction": entry.jurisdiction,
        "source": f"{entry.source_name} — {entry.source_url}",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  [fetch] OK {entry.document_name} -> {out_path.name} "
          f"({len(data):,} bytes, {content_type or 'unknown type'})")
    return out_path


def run_domain_collection(domain: str, fetch: bool | None = None) -> None:
    """
    Entry point called by each collect_<domain>.py.
    Always validates the manifest and reports source reachability.
    Pass fetch=True (or run with `--fetch` on the command line) to also
    download every verified, reachable source into
    data_collection/<domain>/collected/ — this is the explicit, reviewable
    step described below, not automatic, since these are official
    government documents whose content should be spot-checked before
    they're promoted into data/raw/ (see promote_to_raw.py).
    """
    if fetch is None:
        fetch = "--fetch" in sys.argv

    entries = load_manifest(domain)
    print(f"[{domain}] {len(entries)} source(s) in manifest")

    unverified = [e for e in entries if not e.verified]
    if unverified:
        print(f"[{domain}] WARNING: {len(unverified)} unverified source(s) — "
              f"these will NOT be collected until verified=true:")
        for e in unverified:
            print(f"  - {e.document_name} ({e.source_url or 'no URL yet'})")

    collected_dir = DATA_COLLECTION_DIR / domain / "collected"
    collected_dir.mkdir(parents=True, exist_ok=True)

    verified = [e for e in entries if e.verified]
    fetched = 0
    for e in verified:
        ok, detail = check_url_reachable(e.source_url)
        status = "OK" if ok else "UNREACHABLE"
        print(f"[{domain}] {status:11s} {e.document_name} -> {e.source_url} ({detail})")
        if fetch and ok:
            if fetch_document(e, collected_dir) is not None:
                fetched += 1

    if fetch:
        print(f"[{domain}] Fetched {fetched}/{len(verified)} verified source(s) into {collected_dir}/")
        print(f"[{domain}] Next: spot-check the files in {collected_dir}/, then run "
              f"'python scripts/collection/promote_to_raw.py --domain {domain}'.")
    else:
        print(f"[{domain}] Manifest check complete (no download — pass --fetch to download "
              f"verified sources into {collected_dir}/).")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--fetch"]
    if len(args) != 1:
        print("Usage: python -m scripts.collection._collector_base <domain> [--fetch]")
        sys.exit(1)
    run_domain_collection(args[0])
