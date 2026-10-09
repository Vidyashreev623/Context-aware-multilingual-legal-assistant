"""
Phase 6 tests: gemini_service.py's LLMProvider abstraction.

Deliberately avoids any real network call to Gemini -- these test the
error-handling/caching/config-reading plumbing around the API, not the
model itself (there's no way to test real Gemini output offline, and
doing so would burn free-tier quota on every CI run anyway).

Run: pytest backend/tests/test_gemini_service.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.gemini_service import (
    GeminiNotConfiguredError,
    GeminiProvider,
    get_llm_provider,
    reset_llm_provider_cache,
)


def test_empty_api_key_raises_not_configured():
    provider = GeminiProvider(api_key="", model_name="gemini-1.5-flash")
    with pytest.raises(GeminiNotConfiguredError):
        provider.generate("system", "hello")


def test_response_cache_hit_avoids_second_call():
    provider = GeminiProvider(api_key="fake-key-not-used", model_name="gemini-1.5-flash")
    key = ("system prompt", "user prompt")
    provider._cache_put(key, "cached answer")
    assert provider._cache_get(key) == "cached answer"


def test_response_cache_miss_returns_none():
    provider = GeminiProvider(api_key="fake-key", model_name="gemini-1.5-flash")
    assert provider._cache_get(("nope", "nope")) is None


def test_response_cache_evicts_oldest_beyond_max_entries():
    provider = GeminiProvider(api_key="fake-key", model_name="gemini-1.5-flash")
    provider.CACHE_MAX_ENTRIES = 3
    for i in range(5):
        provider._cache_put((f"sys{i}", f"user{i}"), f"answer{i}")
    assert len(provider._cache) == 3
    # oldest two (0, 1) should have been evicted
    assert provider._cache_get(("sys0", "user0")) is None
    assert provider._cache_get(("sys1", "user1")) is None
    assert provider._cache_get(("sys4", "user4")) == "answer4"


def test_get_llm_provider_reads_config_and_caches(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")
    from backend.app.config import get_settings
    get_settings.cache_clear()
    reset_llm_provider_cache()

    p1 = get_llm_provider()
    p2 = get_llm_provider()
    assert p1 is p2  # same cached instance
    assert p1.api_key == "test-key-123"
    assert p1.model_name == "gemini-1.5-flash"
