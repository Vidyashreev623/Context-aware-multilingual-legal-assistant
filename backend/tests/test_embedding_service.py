"""
Phase 4 tests: embedding provider abstraction.

Only tests DeterministicDevFallbackProvider directly (no network/model
download available in CI/sandbox). SentenceTransformerProvider's
_ensure_loaded()/embed_batch() are exercised structurally (raises a
clear RuntimeError when the package isn't installed) but not against
real weights — verify that on a machine with network access.

Run: pytest backend/tests/test_embedding_service.py -v
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.embedding_service import (
    DeterministicDevFallbackProvider,
    SentenceTransformerProvider,
    get_embedding_provider,
)


def test_fallback_provider_is_deterministic():
    provider = DeterministicDevFallbackProvider(dimension=64)
    v1 = provider.embed_text("What is Section 66C?")
    v2 = provider.embed_text("What is Section 66C?")
    assert v1 == v2, "same text must always produce the same vector"


def test_fallback_provider_differs_across_texts():
    provider = DeterministicDevFallbackProvider(dimension=64)
    v1 = provider.embed_text("cyber law")
    v2 = provider.embed_text("property law")
    assert v1 != v2


def test_fallback_provider_dimension_matches_config():
    provider = DeterministicDevFallbackProvider(dimension=128)
    assert provider.dimension == 128
    vec = provider.embed_text("test")
    assert len(vec) == 128


def test_fallback_provider_batches_correctly():
    provider = DeterministicDevFallbackProvider(dimension=32)
    texts = ["a", "b", "c"]
    vectors = provider.embed_batch(texts)
    assert len(vectors) == 3
    assert vectors[0] != vectors[1] != vectors[2]


def test_empty_batch_returns_empty():
    provider = DeterministicDevFallbackProvider(dimension=32)
    assert provider.embed_batch([]) == []


def test_real_provider_raises_clear_error_when_uninstalled():
    """Guards against silently returning garbage if sentence-transformers
    is missing — must fail loudly, not fall back silently, unless the
    caller explicitly opted into the dev fallback."""
    provider = SentenceTransformerProvider("some-model-name")
    try:
        import sentence_transformers  # noqa: F401
        return  # actually installed in this environment — nothing to assert here
    except ImportError:
        pass
    try:
        provider.embed_text("hello")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "sentence-transformers is not installed" in str(exc)


def test_default_provider_selection_respects_flag():
    """Without ALLOW_DEV_EMBEDDING_FALLBACK, get_embedding_provider()
    must return the real provider class even if the package is missing
    (it should fail at embed-time, not silently substitute a fake)."""
    os.environ.pop("ALLOW_DEV_EMBEDDING_FALLBACK", None)
    from backend.app.config import get_settings
    get_settings.cache_clear()
    provider = get_embedding_provider()
    assert isinstance(provider, SentenceTransformerProvider)
