"""
Processor for the 'property' legal domain.
Turns data/raw/property/** into data/processed/property/** (Phase 3).
Run: python scripts/processing/process_property.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.processing._pipeline_base import run_domain_processing, print_report

if __name__ == "__main__":
    result = run_domain_processing("property")
    print_report("property", result)
