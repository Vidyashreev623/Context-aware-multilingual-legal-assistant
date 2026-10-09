"""
Processor for the 'constitutional' legal domain.
Turns data/raw/constitutional/** into data/processed/constitutional/** (Phase 3).
Run: python scripts/processing/process_constitutional.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.processing._pipeline_base import run_domain_processing, print_report

if __name__ == "__main__":
    result = run_domain_processing("constitutional")
    print_report("constitutional", result)
