"""
Collector for the 'criminal' legal domain.
Validates data_collection/criminal/manifest.json and reports source status.
Run: python scripts/collection/collect_criminal.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.collection._collector_base import run_domain_collection

if __name__ == "__main__":
    run_domain_collection("criminal")
