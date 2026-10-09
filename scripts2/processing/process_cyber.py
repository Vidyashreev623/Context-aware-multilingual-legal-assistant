"""
Processor for the 'cyber' legal domain.
Turns data/raw/cyber/** into data/processed/cyber/** (Phase 3).
Run: python scripts/processing/process_cyber.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.processing._pipeline_base import run_domain_processing, print_report

if __name__ == "__main__":
    result = run_domain_processing("cyber")
    print_report("cyber", result)
