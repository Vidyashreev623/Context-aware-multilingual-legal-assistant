"""
Processor for the 'taxation' legal domain.
Turns data/raw/taxation/** into data/processed/taxation/** (Phase 3).
Run: python scripts/processing/process_taxation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.processing._pipeline_base import run_domain_processing, print_report

if __name__ == "__main__":
    result = run_domain_processing("taxation")
    print_report("taxation", result)
