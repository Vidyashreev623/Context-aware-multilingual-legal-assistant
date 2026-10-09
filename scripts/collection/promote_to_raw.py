"""
Promotes fetched, spot-checked documents from
data_collection/<domain>/collected/ into data/raw/<domain>/<type_folder>/
so scripts/processing/process_<domain>.py (Phase 3) can pick them up.

This is deliberately a separate, explicit step from fetch_document() in
_collector_base.py: fetching populates collected/, a human spot-checks
what actually landed there (governments sites sometimes serve a login
wall, a captcha page, or an unrelated HTML shell instead of the real
document — same idea as the README's Rule 3, never process unverified
content), and only then does this script copy things into data/raw/.

Usage:
    python scripts/collection/promote_to_raw.py --domain cyber
    python scripts/collection/promote_to_raw.py --all
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.processing._pipeline_base import DOC_TYPE_TO_FOLDER  # noqa: E402

DATA_COLLECTION_DIR = REPO_ROOT / "data_collection"
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"

ALL_DOMAINS = (
    "consumer", "contract", "cyber", "family", "property", "employment",
    "criminal", "constitutional", "corporate", "intellectual_property",
    "taxation", "environmental", "banking",
)


def promote_domain(domain: str) -> int:
    collected_dir = DATA_COLLECTION_DIR / domain / "collected"
    if not collected_dir.exists():
        print(f"[{domain}] no collected/ directory")
        return 0

    promoted = 0
    for f in sorted(collected_dir.iterdir()):
        if f.name == ".gitkeep" or f.name.endswith(".meta.json"):
            continue

        meta_path = collected_dir / f"{f.name}.meta.json"
        if not meta_path.exists():
            print(f"[{domain}] SKIP {f.name}: no '.meta.json' sidecar "
                  f"(only files written by fetch_document() have one)")
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        doc_type = meta.get("document_type", "act")
        type_folder = DOC_TYPE_TO_FOLDER.get(doc_type, "acts")

        out_dir = DATA_RAW_DIR / domain / type_folder
        out_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(f, out_dir / f.name)
        shutil.copy2(meta_path, out_dir / f"{f.name}.meta.json")
        print(f"[{domain}] PROMOTED {f.name} -> data/raw/{domain}/{type_folder}/{f.name}")
        promoted += 1

    if promoted:
        print(f"[{domain}] Promoted {promoted} file(s). Next: "
              f"'python scripts/processing/process_{domain}.py'.")
    else:
        print(f"[{domain}] Nothing new to promote.")
    return promoted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--domain", choices=ALL_DOMAINS, help="Promote a single domain")
    group.add_argument("--all", action="store_true", help="Promote every domain")
    args = parser.parse_args()

    domains = ALL_DOMAINS if args.all else [args.domain]
    total = sum(promote_domain(d) for d in domains)
    print(f"\nTotal promoted across all domains: {total}")


if __name__ == "__main__":
    main()
