"""
Phase 15 tests: evaluation/evaluate.py's metric functions in isolation
(Precision@K, Recall@K, MRR, Hit Rate), plus a smoke test that the
in-memory eval store's cosine search actually ranks a lexically-close
chunk above an unrelated one.

Run directly: python backend/tests/test_evaluation_metrics.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

from evaluate import hit_rate, mrr, precision_at_k, recall_at_k  # noqa: E402
from toy_embedding import cosine, embed  # noqa: E402


def test_precision_at_k_all_relevant():
    assert precision_at_k(["a", "b"], {"a", "b"}, 5) == 1.0


def test_precision_at_k_none_relevant():
    assert precision_at_k(["x", "y"], {"a"}, 5) == 0.0


def test_precision_at_k_partial():
    assert precision_at_k(["a", "x", "b", "y"], {"a", "b"}, 4) == 0.5


def test_precision_at_k_empty_retrieved():
    assert precision_at_k([], {"a"}, 5) == 0.0


def test_recall_at_k_finds_all():
    assert recall_at_k(["a", "b", "c"], {"a", "b"}, 5) == 1.0


def test_recall_at_k_finds_none():
    assert recall_at_k(["x"], {"a", "b"}, 5) == 0.0


def test_recall_at_k_respects_k_cutoff():
    # relevant item is retrieved but outside the top-1 cutoff
    assert recall_at_k(["x", "a"], {"a"}, 1) == 0.0
    assert recall_at_k(["x", "a"], {"a"}, 2) == 1.0


def test_recall_at_k_empty_relevant_set():
    assert recall_at_k(["a"], set(), 5) == 0.0


def test_mrr_first_position():
    assert mrr(["a", "b"], {"a"}) == 1.0


def test_mrr_third_position():
    assert mrr(["x", "y", "a"], {"a"}) == 1 / 3


def test_mrr_not_found():
    assert mrr(["x", "y"], {"a"}) == 0.0


def test_hit_rate_true_within_k():
    assert hit_rate(["x", "a", "y"], {"a"}, 5) == 1.0


def test_hit_rate_false_outside_k():
    assert hit_rate(["x", "y", "a"], {"a"}, 2) == 0.0


def test_toy_embedding_ranks_lexical_match_higher():
    query = embed("identity theft electronic signature password")
    same_topic = embed("fraudulent use of an electronic password is identity theft")
    unrelated = embed("a lease of immovable property for agricultural purposes")
    assert cosine(query, same_topic) > cosine(query, unrelated)


def test_toy_embedding_hindi_english_bridge_has_nonzero_overlap():
    # Sanity check for the synonym bridge multilingual parity depends on.
    en = embed("identity theft electronic password")
    hi = embed("पहचान की चोरी इलेक्ट्रॉनिक पासवर्ड")
    assert cosine(en, hi) > 0.0


def _run_all():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    passed, failed = 0, []
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((name, str(exc)))
    print(f"{passed}/{len(tests)} passed")
    for name, msg in failed:
        print(f"  FAIL {name}: {msg}")
    return len(failed) == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
