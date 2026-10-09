# Non-negotiable implementation rules

1. No fake buttons — every UI control calls a real backend endpoint.
2. No hard-coded legal answers.
3. No fabricated legal sources/citations.
4. No fabricated evaluation results — all metrics in evaluation/ come from
   actually running scripts/evaluation/evaluate_retrieval.py.
5. Gemini API key never leaves the backend; never referenced from frontend code.
6. Gemini (or any LLM) calls only happen in backend/app/services/gemini_service.py.
7. data_collection/ (raw sourcing) stays separate from data/ (processed).
8. Each legal domain has its own folder end-to-end: collection, raw, processed.
9. RAG components (retrieval, classification, reranking, generation) stay in
   separate, composable services — not one monolithic function.
10. LLM / embedding / vector-store / STT providers are each behind a small
    abstraction so the provider can be swapped without touching callers.
