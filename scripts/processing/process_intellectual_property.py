"""
Processor for the 'intellectual_property' legal domain.
Turns data/raw/intellectual_property/** into data/processed/intellectual_property/** (Phase 3).
Run: python scripts/processing/process_intellectual_property.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.processing._pipeline_base import run_domain_processing, print_report

if __name__ == "__main__":
    result = run_domain_processing("intellectual_property")
    print_report("intellectual_property", result)
