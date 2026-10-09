"""
Embedding service (Phase 4, spec section 17).

Provides one multilingual embedding space so an English query can
retrieve English legal content, and a Kannada/Hindi query can retrieve
the SAME English legal content (the KB stays in its authoritative
source language; only the query gets translated into the shared
embedding space, not the documents).

Rule 10 ("keep embedding providers replaceable"): everything in this
module goes through the EmbeddingProvider interface. Swapping models
means writing one new provider class, not touching the RAG pipeline.

Two providers ship here:
  - SentenceTransformerProvider: the real one
    (paraphrase-multilingual-mpnet-base-v2 by default — supports
    English/Hindi/Kannada). Requires `pip install sentence-transformers`
    and a one-time model download, so it needs network access on
    first run.
  - DeterministicDevFallbackProvider: a hash-based, NOT semantically
    meaningful embedder used ONLY so the surrounding pipeline
    (chunking -> embedding -> storage -> retrieval wiring) can be
    exercised offline/in CI without the real model. It must never be
    used to serve real answers — see the guard in get_embedding_provider().
"""
from __future__ import annotations

import hashlib
import struct
import sys
import threading
from abc import ABC, abstractmethod

from app.config import get_settings


class EmbeddingProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]


class SentenceTransformerProvider(EmbeddingProvider):
    """
    Real multilingual embedding provider. Model is lazy-loaded (and
    cached process-wide) on first use so importing this module never
    triggers a slow model load or a network call on its own.

    IMPORTANT: this class is only cheap to *use* repeatedly if the same
    instance is reused across requests -- the actual SentenceTransformer
    model load in _ensure_loaded() is the expensive part (reading a
    ~1GB multilingual model off disk into memory). Callers must go
    through get_embedding_provider() below, which caches one instance
    process-wide, rather than constructing this class directly per
    request.
    """
    name = "sentence-transformers"

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._dim: int | None = None
        self._lock = threading.Lock()

    def _ensure_loaded(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Run: pip install -r backend/requirements.txt"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
            self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        self._ensure_loaded()
        return self._dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        if not texts:
            return []
        vectors = self._model.encode(
            texts, batch_size=32, show_progress_bar=False,
            normalize_embeddings=True,  # cosine similarity via dot product downstream
        )
        return [v.tolist() for v in vectors]


class DeterministicDevFallbackProvider(EmbeddingProvider):
    """
    NOT a real embedding model. Produces a deterministic pseudo-vector
    from a text hash so pipeline code (batching, storage shape,
    top-K search plumbing) can be tested without downloading anything.

    Similarity scores from this provider are meaningless for legal
    retrieval quality — it does not understand language at all, let
    alone multiple languages. get_embedding_provider() only returns
    this when explicitly allowed via ALLOW_DEV_EMBEDDING_FALLBACK, and
    every call logs a loud warning so it can never be mistaken for the
    real thing in a demo or report.
    """
    name = "deterministic-dev-fallback"

    def __init__(self, dimension: int = 384):
        self._dim = dimension
        self._warned = False

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._warned:
            print(
                "  [WARNING] Using DeterministicDevFallbackProvider — this is NOT a real "
                "embedding model. Retrieval quality/results are meaningless. Install "
                "sentence-transformers and remove ALLOW_DEV_EMBEDDING_FALLBACK before "
                "generating anything you intend to evaluate or demo.",
                file=sys.stderr,
            )
            self._warned = True
        return [self._hash_embed(t) for t in texts]

    def _hash_embed(self, text: str) -> list[float]:
        # Repeated SHA-256 over an incrementing counter gives us enough
        # deterministic bytes to fill the vector; scaled to roughly [-1, 1].
        raw = b""
        counter = 0
        while len(raw) < self._dim * 4:
            raw += hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
            counter += 1
        floats = []
        for i in range(self._dim):
            (val,) = struct.unpack_from("I", raw, i * 4)
            floats.append((val / 0xFFFFFFFF) * 2 - 1)
        return floats


# ---------------------------------------------------------------------------
# Process-wide singleton cache.
#
# THIS WAS THE MAIN CAUSE OF SLOW RESPONSES: get_embedding_provider() used
# to construct a brand-new SentenceTransformerProvider() on every call, with
# no caching -- unlike get_llm_provider() (gemini_service.py) and
# get_vector_store() (vector_store_service.py), which were already both
# singletons. Since SentenceTransformerProvider lazy-loads its model on
# first embed_batch() call, a fresh instance every request meant the
# multilingual transformer model was being read off disk and initialized
# from scratch on EVERY chat message -- easily several seconds of pure
# overhead before retrieval or the Gemini call even started. Caching one
# instance process-wide (same lock-protected double-checked pattern as the
# other two services) means the model loads once at first use and every
# request after that reuses the already-loaded model in memory.
# ---------------------------------------------------------------------------
_provider_lock = threading.Lock()
_provider_instance: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """
    Single place the rest of the app calls to get an embedding provider.
    Reads config (backend/app/config.py):
        EMBEDDING_MODEL                (default: paraphrase-multilingual-mpnet-base-v2)
        ALLOW_DEV_EMBEDDING_FALLBACK   (default: false)

    Cached process-wide (like get_llm_provider() / get_vector_store())
    so the underlying SentenceTransformer model is loaded from disk once
    per process, not once per request.
    """
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance
    with _provider_lock:
        if _provider_instance is not None:
            return _provider_instance

        settings = get_settings()
        allow_fallback = getattr(settings, "ALLOW_DEV_EMBEDDING_FALLBACK", False)

        if allow_fallback:
            try:
                import sentence_transformers  # noqa: F401
                _provider_instance = SentenceTransformerProvider(settings.EMBEDDING_MODEL)
            except ImportError:
                _provider_instance = DeterministicDevFallbackProvider()
        else:
            _provider_instance = SentenceTransformerProvider(settings.EMBEDDING_MODEL)

        return _provider_instance


def reset_embedding_provider_cache() -> None:
    """Test-only helper: forces the next get_embedding_provider() call to
    build a fresh instance (e.g. after changing EMBEDDING_MODEL in a
    test, or to force a reload)."""
    global _provider_instance
    with _provider_lock:
        _provider_instance = None