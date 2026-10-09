"""
Phase 15 evaluation (spec sections 45-47).

Runs the REAL `retrieval_service.py`/`classification_service.py`/
`ambiguity_service.py` code (imported, not reimplemented) against the
synthetic fixture corpus in `fixture_corpus.py`, using the toy embedder
in `toy_embedding.py` in place of the real sentence-transformers model
(no network in this sandbox — see DATASET.md). Every number below is
computed for real from that run; nothing is hard-coded (Rule 4).

Baseline  = spec section 43's "Baseline": embed -> plain vector search
            (top TOP_K_FINAL, no filter) -> done.
Improved  = spec section 43's "Improved": classify_query -> domain-
            filtered retrieve_candidates -> rerank -> top TOP_K_FINAL.
            (ambiguity-flagged questions are excluded from retrieval
            scoring, same as a real chat turn would short-circuit to a
            clarification question before retrieval ever runs.)

Usage:
    python evaluation/evaluate.py

Writes evaluation/baseline_results.json and
evaluation/improved_results.json, and prints the spec-section-46 table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app.services.ambiguity_service import detect_ambiguity
from backend.app.services.classification_service import classify_query
from backend.app.services.retrieval_service import rerank, retrieve_candidates
from backend.app.services.vector_store_service import SearchResult, VectorRecord, VectorStore

from fixture_corpus import CORPUS
from toy_embedding import cosine, embed

TOP_K_FINAL = 5
TOP_K_CANDIDATES = 20
EVAL_DIR = Path(__file__).resolve().parent


class InMemoryVectorStore(VectorStore):
    """A real (not faked-out) VectorStore implementation — genuine
    cosine-similarity search over in-memory vectors — used only because
    Chroma/FAISS need `pip install` this sandbox can't reach. Swapping
    this for the real backend in `vector_store_service.py` doesn't
    change anything else in this file: that's the whole point of the
    VectorStore abstraction (Rule 10)."""
    name = "in-memory-eval"

    def __init__(self):
        self._records: dict[str, VectorRecord] = {}

    def add(self, records: list[VectorRecord]) -> int:
        for r in records:
            self._records[r.chunk_id] = r
        return len(records)

    def search(self, query_embedding, top_k=10, where=None):
        candidates = self._records.values()
        if where:
            candidates = [
                r for r in candidates
                if all(r.metadata().get(k) == v for k, v in where.items())
            ]
        scored = [
            SearchResult(r.chunk_id, r.text, cosine(query_embedding, r.embedding), r.metadata())
            for r in candidates
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    def delete(self, chunk_ids):
        for cid in chunk_ids:
            self._records.pop(cid, None)
        return len(chunk_ids)

    def filter(self, where, limit=1000):
        return [
            r for r in self._records.values()
            if all(r.metadata().get(k) == v for k, v in where.items())
        ][:limit]

    def count(self) -> int:
        return len(self._records)


def build_store() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    records = [
        VectorRecord(
            chunk_id=c.chunk_id, text=c.text, embedding=embed(c.text),
            domain=c.domain, document_type=c.document_type, act_name=c.act_name,
            section=c.section, jurisdiction=c.jurisdiction, language=c.language,
            year=c.year,
        )
        for c in CORPUS
    ]
    store.add(records)
    return store


# ---- metrics (spec section 45) ----

def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for cid in top if cid in relevant) / len(top)


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    return sum(1 for cid in top if cid in relevant) / len(relevant)


def mrr(retrieved: list[str], relevant: set[str]) -> float:
    for i, cid in enumerate(retrieved, start=1):
        if cid in relevant:
            return 1.0 / i
    return 0.0


def hit_rate(retrieved: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if any(cid in relevant for cid in retrieved[:k]) else 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ---- retrieval runners ----

def run_baseline(store: InMemoryVectorStore, query: str) -> list[str]:
    """Spec section 43 Baseline: embed -> plain top-K search. No
    classification, no filter, no rerank."""
    results = store.search(embed(query), top_k=TOP_K_FINAL)
    return [r.chunk_id for r in results]


def run_improved(store: InMemoryVectorStore, query: str) -> tuple[list[str], bool]:
    """Spec section 43 Improved: classify -> domain-filtered candidate
    retrieval -> rerank -> top-K. Returns (chunk_ids, was_ambiguous)."""
    classification = classify_query(query)
    ambiguity = detect_ambiguity(query, classification)
    if ambiguity.ambiguous:
        return [], True
    candidates = retrieve_candidates(embed(query), store, classification, TOP_K_CANDIDATES)
    final = rerank(candidates, classification, TOP_K_FINAL)
    return [r.chunk_id for r in final], False


def main() -> None:
    store = build_store()
    questions = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))
    expected: dict[str, list[str]] = json.loads(
        (EVAL_DIR / "expected_sources.json").read_text(encoding="utf-8")
    )

    baseline_out, improved_out = [], []
    baseline_metrics, improved_metrics = [], []
    ambiguous_ids = {"q_ambiguous_01", "q_ambiguous_02"}
    parity_pairs: dict[str, list[str]] = {}

    for q in questions:
        qid, query = q["id"], q["query"]

        if qid in ambiguous_ids:
            _, was_ambiguous = run_improved(store, query)
            improved_out.append({
                "id": qid, "query": query,
                "expected_ambiguous": True, "flagged_ambiguous": was_ambiguous,
            })
            continue

        relevant = set(expected.get(qid, []))

        b_retrieved = run_baseline(store, query)
        i_retrieved, was_ambiguous = run_improved(store, query)

        b_row = {
            "id": qid, "query": query, "retrieved": b_retrieved,
            "precision@5": precision_at_k(b_retrieved, relevant, TOP_K_FINAL),
            "recall@5": recall_at_k(b_retrieved, relevant, TOP_K_FINAL),
            "mrr": mrr(b_retrieved, relevant),
            "hit_rate@5": hit_rate(b_retrieved, relevant, TOP_K_FINAL),
        }
        i_row = {
            "id": qid, "query": query, "retrieved": i_retrieved,
            "flagged_ambiguous": was_ambiguous,
            "precision@5": precision_at_k(i_retrieved, relevant, TOP_K_FINAL),
            "recall@5": recall_at_k(i_retrieved, relevant, TOP_K_FINAL),
            "mrr": mrr(i_retrieved, relevant),
            "hit_rate@5": hit_rate(i_retrieved, relevant, TOP_K_FINAL),
        }
        baseline_out.append(b_row)
        improved_out.append(i_row)
        baseline_metrics.append(b_row)
        improved_metrics.append(i_row)

        parity_key = q.get("parity_of")
        if parity_key:
            parity_pairs.setdefault(parity_key, []).append(qid)

    # spec section 47: multilingual parity — does the hi/kn version of a
    # question retrieve (some overlap with) what the English version did?
    parity_report = []
    by_id_improved = {row["id"]: row for row in improved_metrics}
    for en_id, translations in parity_pairs.items():
        en_row = by_id_improved.get(en_id)
        if not en_row:
            continue
        en_set = set(en_row["retrieved"])
        for t_id in translations:
            t_row = by_id_improved.get(t_id)
            if not t_row:
                continue
            t_set = set(t_row["retrieved"])
            overlap = len(en_set & t_set)
            parity_report.append({
                "english_id": en_id, "translated_id": t_id,
                "overlap_count": overlap,
                "parity_achieved": overlap > 0,
            })

    summary = {
        "baseline": {
            "precision@5": _average([r["precision@5"] for r in baseline_metrics]),
            "recall@5": _average([r["recall@5"] for r in baseline_metrics]),
            "mrr": _average([r["mrr"] for r in baseline_metrics]),
            "hit_rate@5": _average([r["hit_rate@5"] for r in baseline_metrics]),
        },
        "improved": {
            "precision@5": _average([r["precision@5"] for r in improved_metrics]),
            "recall@5": _average([r["recall@5"] for r in improved_metrics]),
            "mrr": _average([r["mrr"] for r in improved_metrics]),
            "hit_rate@5": _average([r["hit_rate@5"] for r in improved_metrics]),
        },
        "questions_scored": len(baseline_metrics),
        "questions_ambiguous": len(ambiguous_ids),
        "multilingual_parity": parity_report,
    }

    (EVAL_DIR / "baseline_results.json").write_text(
        json.dumps({"per_question": baseline_out, "summary": summary["baseline"]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (EVAL_DIR / "improved_results.json").write_text(
        json.dumps({
            "per_question": improved_out, "summary": summary["improved"],
            "multilingual_parity": parity_report,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Corpus size: {store.count()} chunks | Questions scored: {summary['questions_scored']} "
          f"| Ambiguous (unscored): {summary['questions_ambiguous']}\n")
    print(f"{'Metric':<14}{'Baseline':>12}{'Improved':>12}")
    for metric in ("precision@5", "recall@5", "mrr", "hit_rate@5"):
        b, i = summary["baseline"][metric], summary["improved"][metric]
        print(f"{metric:<14}{b:>12.3f}{i:>12.3f}")
    print()
    print("Multilingual retrieval parity (spec section 47):")
    for row in parity_report:
        status = "OK" if row["parity_achieved"] else "MISS"
        print(f"  [{status}] {row['translated_id']} vs {row['english_id']} "
              f"(shared chunks: {row['overlap_count']})")


if __name__ == "__main__":
    main()
