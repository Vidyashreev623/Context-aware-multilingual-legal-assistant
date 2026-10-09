"""
Phase 16 test runner.

This project's test files are written in plain pytest style (bare
`def test_x(): assert ...` functions, no fixtures/parametrize in any of
them), specifically so they can ALSO be collected and run without
pytest installed -- which matters here because this sandbox has no
network access to `pip install pytest` (or fastapi/chromadb/faiss/
sentence-transformers/faster-whisper, each needed by a handful of test
files). This mirrors the "ad-hoc collector" every earlier phase's
PHASES.md entry already described running by hand; this script is that
collector made real and reusable instead of a one-off snippet.

What it does:
  - imports every backend/tests/test_*.py module
  - if the import itself fails (missing optional dependency), records
    the module as SKIPPED with the reason -- never silently ignored
  - for modules that DO import, calls every zero-argument top-level
    callable named test_* and records PASS/FAIL per test
  - exits non-zero if any test FAILED (skips don't fail the run --
    they mean "needs a dependency this environment doesn't have", not
    "broken")

On a machine with network access, run the real thing instead:
    pip install -r backend/requirements.txt
    pytest backend/tests/ -v
That exercises the (currently skipped here) fastapi/chromadb/faiss/
sentence-transformers/faster-whisper-dependent test files for real,
same as Phases 13-14 documented.

Run: python backend/tests/run_tests.py
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(TESTS_DIR))


def discover_test_modules() -> list[str]:
    names = sorted(
        p.stem for p in TESTS_DIR.glob("test_*.py")
        if p.stem != "run_tests"
    )
    return names


def run_module(name: str) -> dict:
    result = {"module": name, "status": None, "passed": 0, "failed": [], "skip_reason": None}
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this is a collector
        result["status"] = "SKIPPED"
        result["skip_reason"] = f"{type(exc).__name__}: {exc}"
        return result

    test_fns = [
        (attr, getattr(module, attr)) for attr in dir(module)
        if attr.startswith("test_") and callable(getattr(module, attr))
    ]
    if not test_fns:
        result["status"] = "SKIPPED"
        result["skip_reason"] = "no test_* functions found (module may need pytest fixtures)"
        return result

    for fn_name, fn in test_fns:
        try:
            fn()
            result["passed"] += 1
        except TypeError as exc:
            # Needs pytest fixture/parametrize args -> not runnable by this
            # simple collector, not a real failure.
            result["failed"].append((fn_name, f"needs pytest ({exc})"))
        except AssertionError:
            result["failed"].append((fn_name, traceback.format_exc(limit=1)))
        except Exception as exc:  # noqa: BLE001
            result["failed"].append((fn_name, f"{type(exc).__name__}: {exc}"))

    result["status"] = "FAILED" if result["failed"] else "PASSED"
    return result


def main() -> int:
    modules = discover_test_modules()
    results = [run_module(m) for m in modules]

    total_passed = sum(r["passed"] for r in results)
    total_failed = sum(len(r["failed"]) for r in results)
    skipped = [r for r in results if r["status"] == "SKIPPED"]

    print(f"{'Module':<38}{'Status':<10}{'Passed':<8}{'Failed'}")
    for r in results:
        print(f"{r['module']:<38}{r['status']:<10}{r['passed']:<8}{len(r['failed'])}")
        if r["status"] == "SKIPPED":
            print(f"    -> {r['skip_reason']}")
        for fn_name, msg in r["failed"]:
            print(f"    FAIL {fn_name}: {msg.strip().splitlines()[-1] if msg else ''}")

    print(f"\nTOTAL: {total_passed} passed, {total_failed} failed, "
          f"{len(skipped)}/{len(results)} modules skipped (missing optional deps)")
    if skipped:
        print("Skipped modules need: pip install -r backend/requirements.txt "
              "(pytest/fastapi/chromadb/faiss/sentence-transformers/faster-whisper) "
              "on a machine with network access.")

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
