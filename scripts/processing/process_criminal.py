"""
Processor for the 'criminal' legal domain.
Turns data/raw/criminal/** into data/processed/criminal/** (Phase 3).
Run: python scripts/processing/process_criminal.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.processing._pipeline_base import run_domain_processing, print_report

if __name__ == "__main__":
    result = run_domain_processing("criminal")
    print_report("criminal", result)
