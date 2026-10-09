# EVALUATION

Status: Phase 15 — done, against a synthetic fixture corpus (see below
for exactly why, and what to re-run once real data exists).

## Why a fixture, not the real corpus

`data_collection/*/collected/` and `data/raw/*/` are still empty in
this codebase (see `DATASET.md`). Fetching real Acts/judgments needs
network access this sandbox doesn't have, and Rule 3 forbids fabricating
sources to fill the gap. Rule 4 ("no fabricated evaluation results")
does *not* mean the evaluation harness has to wait for that — it means
every number this harness reports has to come from actually running
code, never be typed in by hand. That's what `evaluation/evaluate.py`
does: it imports the REAL `classification_service.py`,
`ambiguity_service.py`, and `retrieval_service.py` (unmodified,
production code) and runs them against `evaluation/fixture_corpus.py`,
a small hand-written set of chunks naming real, well-known Indian Acts
and sections (Indian Contract Act s.10/73, IT Act s.66C/66D/43,
Consumer Protection Act, Hindu Marriage Act, Transfer of Property Act,
Industrial Disputes Act) with original summary text — not copied from
any Act/judgment, and not to be treated as authoritative legal text.

The one other substitution: real retrieval needs a real embedding
model (`sentence-transformers/paraphrase-multilingual-mpnet-base-v2`,
Phase 4), which needs a `pip install` + model download this sandbox's
network can't reach. `evaluation/toy_embedding.py` stands in — a
hashed bag-of-words vector with a small hand-written Hindi/Kannada->
English synonym bridge for the handful of legal terms this fixture's
chunks actually use. Cosine similarity over these vectors is real
arithmetic on real term overlap, not a fabricated score — but it is NOT
semantically meaningful the way a real multilingual embedding model is
for arbitrary text, so absolute metric values below are meaningful only
*for this fixture*, not as a claim about production retrieval quality.

**Before writing up spec section 46's report table for submission**:
run Phase 2's real data collection (network access + manual legal-
source curation, per `data_collection/*/sources.md`), Phase 3-5 for
real (`process_<domain>.py` -> `generate_embeddings.py` ->
`build_index.py` with `sentence-transformers` actually installed), then
`python evaluation/evaluate.py` again — it will pick up whatever real
corpus is in the vector store, no code changes needed to switch from
the fixture (only `build_store()`'s in-memory-for-the-fixture wiring
would be swapped for the real persisted `VectorStore` — everything
downstream of it is unchanged).

## How to run it

```bash
python evaluation/evaluate.py
```

Reads `evaluation/questions.json` + `evaluation/expected_sources.json`,
writes `evaluation/baseline_results.json` +
`evaluation/improved_results.json`, prints the table below.

## Baseline vs improved (last run against the fixture corpus, 21 chunks, 16 scored questions + 2 ambiguity-only questions)

| Metric | Baseline | Improved |
|---|---:|---:|
| Precision@5 | 0.200 | 0.325 |
| Recall@5 | 0.781 | 0.812 |
| MRR | 0.658 | 0.677 |
| Hit Rate@5 | 0.812 | 0.812 |

- **Baseline** (spec section 43): embed -> plain top-5 vector search.
  No classification, no domain filter, no rerank.
- **Improved** (spec section 43): classify_query -> domain-filtered
  candidate retrieval (`retrieve_candidates`) -> `rerank` (semantic +
  domain/jurisdiction/state/section bonuses, spec section 44's stated
  priority order) -> top-5.
- Precision@5 improves the most (+0.125): the fixture corpus
  deliberately includes off-domain distractor chunks (Companies Act,
  Income Tax Act, IPC s.499) specifically so a domain-blind baseline
  search has real irrelevant matches it can pull into its top-5, which
  domain filtering then avoids.
- Recall@5 and Hit Rate@5 are already high for the baseline on this
  small fixture (21 chunks, usually 1-2 truly relevant per question) —
  a bigger, real corpus with many more plausible-but-wrong same-domain
  chunks is expected to widen this gap; the fixture is too small to
  show it.
- MRR improves only slightly — on this fixture the correct chunk was
  usually already near the top of the baseline's raw semantic ranking;
  reranking mostly reorders items *below* the first relevant hit.

## Ambiguity handling (spec section 23, scored separately)

The two worked examples from the spec itself — "What happens if
someone breaks a contract?" (section 4) and "Can I file a case?"
(section 23) — are both correctly flagged `ambiguous=True` by
`ambiguity_service.detect_ambiguity()` and are excluded from the
retrieval metrics above (a real chat turn would short-circuit to a
clarifying question before retrieval ever runs, so scoring them for
retrieval quality would be measuring the wrong thing).

## Multilingual retrieval parity (spec section 47)

For each Hindi/Kannada question with an English counterpart in
`questions.json` (`parity_of`), the script checks whether the improved
pipeline's top-5 for the translation shares at least one chunk with the
English version's top-5:

| Translated question | vs English question | Shared chunks | Parity? |
|---|---|---:|---|
| q_contract_03_hi | q_contract_01 | 5 | Yes |
| q_contract_04_kn | q_contract_01 | 5 | Yes |
| q_cyber_03_hi | q_cyber_02 | 5 | Yes |
| q_cyber_04_kn | q_cyber_02 | 5 | Yes |

All four pairs achieve parity on the fixture. This is expected and
somewhat circular for this fixture specifically: the synonym bridge in
`toy_embedding.py` was hand-written to cover exactly the Hindi/Kannada
terms these fixture questions/chunks use. It demonstrates the
*evaluation harness's parity check itself works correctly* (it would
report `MISS` if the pipeline returned disjoint results — see
`backend/tests/test_evaluation_metrics.py`), not that the real
multilingual embedding model achieves parity on arbitrary Hindi/Kannada
legal questions. Re-running against the real embedding model
(Phase 4) and a real multilingual corpus is the actual test of that.

## Test coverage for the harness itself

`backend/tests/test_evaluation_metrics.py` (15/15 passing, run directly
— no pytest needed): unit tests for `precision_at_k`/`recall_at_k`/
`mrr`/`hit_rate` against known small inputs, plus two sanity checks on
`toy_embedding.py` (lexically-related text scores higher than unrelated
text; the Hindi/English synonym bridge produces nonzero overlap).
