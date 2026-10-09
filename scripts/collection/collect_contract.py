"""
Collector for the 'contract' legal domain.
Validates data_collection/contract/manifest.json and reports source status.
Run: python scripts/collection/collect_contract.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.collection._collector_base import run_domain_collection

if __name__ == "__main__":
    run_domain_collection("contract")
