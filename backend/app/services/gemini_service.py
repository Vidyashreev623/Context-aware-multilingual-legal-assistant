"""
LLM service (Gemini + optional fallback providers).

Providers supported (all optional except Gemini):
    gemini      Google Gemini via google-genai
    xai         xAI Grok       (OpenAI-compatible)
    groq        Groq           (OpenAI-compatible)
    cerebras    Cerebras       (OpenAI-compatible)
    openrouter  OpenRouter     (OpenAI-compatible)

Order is controlled by LLM_PROVIDER_ORDER in backend/.env, for example:
    LLM_PROVIDER_ORDER=xai,gemini

A provider with no API key (or no model name) is skipped automatically.

What changed vs. the original version
-------------------------------------
1. Retries fail fast. The old backoff (5s, 10s, 20s, 40s = 75s of sleeping)
   caused ~60s responses whenever Gemini returned a 429/503.
   Now: 1 short retry, then move on.
2. Every request has a hard timeout (default 20s).
3. Fallback providers: if one fails or is rate limited, the next answers.
4. A provider that just failed is skipped for a cooldown period so later
   requests do not wait for it again.
5. The response cache lives in the wrapper, so answers from any provider
   are cached, and failures are never cached.

Public names kept for compatibility with the rest of the app:
    get_llm_provider, reset_llm_provider_cache, LLMProvider,
    GeminiProvider, GeminiServiceError, GeminiNotConfiguredError,
    GeminiRateLimitError, GeminiError
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict

from app.config import get_settings

logger = logging.getLogger("llm")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class GeminiServiceError(Exception):
    """Base exception for LLM service errors."""


class GeminiNotConfiguredError(GeminiServiceError):
    """Raised when a provider's API key or model is missing."""


class GeminiRateLimitError(GeminiServiceError):
    """Raised when rate/quota limits remain after retries."""


class GeminiError(GeminiServiceError):
    """Raised for other LLM/API failures."""


# ---------------------------------------------------------------------------
# LLM provider interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, system_instructions: str, user_message: str) -> str:
        """Generate an answer using the configured LLM."""
        ...


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Gemini implementation using the google-genai SDK."""

    name = "gemini"

    # Retry attempts AFTER the first request. Keep small: a slow answer is
    # worse than falling back to another provider.
    MAX_RETRIES = 1

    # Delay (seconds) before each retry.
    RETRY_BACKOFF_SECONDS = (2,)

    def __init__(
        self,
        api_key: str,
        model_name: str,
        timeout_seconds: float = 20.0,
        max_output_tokens: int = 1024,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

        self._client = None
        self._lock = threading.Lock()
        self.CACHE_MAX_ENTRIES = 128
        self._cache: OrderedDict[tuple[str, str], str] = OrderedDict()

    # -- client init -------------------------------------------------------

    def _cache_get(self, key: tuple[str, str]) -> str | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _cache_put(self, key: tuple[str, str], value: str) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self.CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)
    def _ensure_configured(self) -> None:
        if not self.api_key:
            raise GeminiNotConfiguredError(
                "GEMINI_API_KEY is not set. Add it to backend/.env."
            )

        if self._client is not None:
            return

        with self._lock:
            if self._client is not None:
                return

            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:
                raise GeminiError(
                    "google-genai is not installed. "
                    "Run: pip install -r backend/requirements.txt"
                ) from exc

            try:
                # http_options.timeout is in MILLISECONDS.
                self._client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(
                        timeout=int(self.timeout_seconds * 1000)
                    ),
                )
            except Exception as exc:
                raise GeminiError(
                    f"Unable to initialize Gemini client: {exc}"
                ) from exc

    # -- generate ----------------------------------------------------------

    def generate(self, system_instructions: str, user_message: str) -> str:
        self._ensure_configured()

        try:
            from google.genai import errors, types
        except ImportError as exc:
            raise GeminiError(
                "google-genai is not installed correctly. "
                "Run: pip install -r backend/requirements.txt"
            ) from exc

        config = types.GenerateContentConfig(
            system_instruction=system_instructions,
            max_output_tokens=self.max_output_tokens,
        )

        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=user_message,
                    config=config,
                )

                text = (response.text or "").strip()
                if not text:
                    raise GeminiError(
                        "Gemini returned an empty response. "
                        "This can happen when the response is blocked "
                        "by safety filters."
                    )

                logger.info(
                    "[gemini] ok attempt=%d model=%s %.2fs",
                    attempt, self.model_name, time.perf_counter() - started,
                )
                return text

            except errors.ClientError as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "[gemini] attempt=%d ClientError code=%s %.2fs: %s",
                    attempt, exc.code, elapsed, exc,
                )

                if exc.code == 429:
                    last_exc = exc
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_BACKOFF_SECONDS[attempt])
                        continue
                    raise GeminiRateLimitError(
                        "Gemini rate limit/quota exceeded after retries."
                    ) from exc

                # 400 / 403 / 404 etc. -- retrying will not help.
                raise GeminiError(f"Gemini API call failed: {exc}") from exc

            except errors.ServerError as exc:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "[gemini] attempt=%d ServerError %.2fs: %s",
                    attempt, elapsed, exc,
                )
                last_exc = exc
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise GeminiError(
                    f"Gemini API server error after retries: {exc}"
                ) from exc

            except errors.APIError as exc:
                logger.warning("[gemini] attempt=%d APIError: %s", attempt, exc)
                raise GeminiError(f"Gemini API call failed: {exc}") from exc

            except GeminiServiceError:
                raise

            except Exception as exc:  # timeouts, network errors, SDK bugs
                elapsed = time.perf_counter() - started
                logger.warning(
                    "[gemini] attempt=%d unexpected error %.2fs: %s",
                    attempt, elapsed, exc,
                )
                raise GeminiError(f"Unexpected Gemini error: {exc}") from exc

        raise GeminiError(f"Gemini call failed: {last_exc}")


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (xAI Grok, Groq, Cerebras, OpenRouter, ...)
# ---------------------------------------------------------------------------

class OpenAICompatProvider(LLMProvider):
    """
    Any provider that exposes an OpenAI-compatible chat completions API.

    Requires:  pip install openai
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float = 20.0,
        max_output_tokens: int = 1024,
    ):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

        self._client = None
        self._lock = threading.Lock()

    def _ensure_configured(self) -> None:
        if not self.api_key or not self.model_name:
            raise GeminiNotConfiguredError(
                f"{self.name}: API key or model name is not set."
            )

        if self._client is not None:
            return

        with self._lock:
            if self._client is not None:
                return

            try:
                from openai import OpenAI
            except ImportError as exc:
                raise GeminiError(
                    "openai package is not installed. Run: pip install openai"
                ) from exc

            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=0,  # fallback is handled by FallbackProvider
            )

    def generate(self, system_instructions: str, user_message: str) -> str:
        self._ensure_configured()

        started = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=self.max_output_tokens,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            logger.warning("[%s] failed %.2fs: %s", self.name, elapsed, exc)

            status = getattr(exc, "status_code", None)
            if status == 429:
                raise GeminiRateLimitError(
                    f"{self.name} rate limit/quota exceeded."
                ) from exc
            raise GeminiError(f"{self.name} API call failed: {exc}") from exc

        try:
            text = (resp.choices[0].message.content or "").strip()
        except (AttributeError, IndexError):
            text = ""

        if not text:
            raise GeminiError(f"{self.name} returned an empty response.")

        logger.info(
            "[%s] ok model=%s %.2fs",
            self.name, self.model_name, time.perf_counter() - started,
        )
        return text


# ---------------------------------------------------------------------------
# Fallback wrapper (cache + ordered providers + cooldown)
# ---------------------------------------------------------------------------

class FallbackProvider(LLMProvider):
    """
    Tries providers in order. A provider that fails is skipped for
    `cooldown_seconds`, so later requests do not wait for it again.
    Successful answers are cached in memory.
    """

    name = "fallback"

    CACHE_MAX_ENTRIES = 128

    def __init__(
        self,
        providers: list[LLMProvider],
        cooldown_seconds: float = 60.0,
    ):
        if not providers:
            raise GeminiNotConfiguredError("No LLM providers configured.")

        self.providers = providers
        self.cooldown_seconds = cooldown_seconds

        self._lock = threading.Lock()
        self._cooldown_until: dict[str, float] = {}
        self._cache: OrderedDict[tuple[str, str], str] = OrderedDict()

    # -- cache -------------------------------------------------------------

            # -- cache -------------------------------------------------------------

    def _cache_get(self, key: tuple[str, str]) -> str | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def _cache_put(self, key: tuple[str, str], value: str) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)

    # -- cooldown ----------------------------------------------------------

    def _in_cooldown(self, name: str) -> bool:
        with self._lock:
            return self._cooldown_until.get(name, 0.0) > time.monotonic()

    def _start_cooldown(self, name: str) -> None:
        with self._lock:
            self._cooldown_until[name] = time.monotonic() + self.cooldown_seconds

    # -- generate ----------------------------------------------------------

    def generate(self, system_instructions: str, user_message: str) -> str:
        cache_key = (system_instructions, user_message)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        # Prefer providers that are not cooling down; if every provider is
        # cooling down, try them all anyway rather than failing outright.
        available = [p for p in self.providers if not self._in_cooldown(p.name)]
        candidates = available or self.providers

        last_exc: Exception | None = None
        rate_limited = False

        for provider in candidates:
            try:
                text = provider.generate(system_instructions, user_message)
                self._cache_put(cache_key, text)
                return text

            except GeminiNotConfiguredError as exc:
                # Misconfiguration: skip, no cooldown needed.
                logger.warning("[llm] %s not configured: %s", provider.name, exc)
                last_exc = exc

            except GeminiRateLimitError as exc:
                rate_limited = True
                last_exc = exc
                self._start_cooldown(provider.name)
                logger.warning("[llm] %s rate limited, trying next", provider.name)

            except GeminiServiceError as exc:
                last_exc = exc
                self._start_cooldown(provider.name)
                logger.warning("[llm] %s failed: %s, trying next", provider.name, exc)

        if rate_limited:
            raise GeminiRateLimitError(
                f"All LLM providers failed (rate limited): {last_exc}"
            ) from last_exc
        raise GeminiError(f"All LLM providers failed: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------

_provider_lock = threading.Lock()
_provider_instance: LLMProvider | None = None

# OpenAI-compatible providers: name -> (base_url, SETTINGS_KEY_PREFIX)
_OPENAI_COMPAT = {
    "xai": ("https://api.x.ai/v1", "XAI"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ"),
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER"),
}


def _build_providers() -> list[LLMProvider]:
    """
    Build providers from settings, ordered by LLM_PROVIDER_ORDER
    (default: "gemini,xai,groq,cerebras,openrouter").

    Optional providers with no API key / model are skipped. Gemini is
    always built so a missing key gives a clear error message.
    """
    s = get_settings()

    timeout = float(getattr(s, "LLM_TIMEOUT_SECONDS", 20.0))
    max_tokens = int(getattr(s, "LLM_MAX_OUTPUT_TOKENS", 1024))
    order_raw = getattr(s, "LLM_PROVIDER_ORDER", "gemini,xai,groq,cerebras,openrouter")
    order = [x.strip().lower() for x in order_raw.split(",") if x.strip()]

    providers: list[LLMProvider] = []

    for name in order:
        if name == "gemini":
            providers.append(
                GeminiProvider(
                    api_key=getattr(s, "GEMINI_API_KEY", ""),
                    model_name=getattr(s, "GEMINI_MODEL", ""),
                    timeout_seconds=timeout,
                    max_output_tokens=max_tokens,
                )
            )

        elif name in _OPENAI_COMPAT:
            base_url, prefix = _OPENAI_COMPAT[name]
            api_key = getattr(s, f"{prefix}_API_KEY", "") or ""
            model = getattr(s, f"{prefix}_MODEL", "") or ""

            if not api_key or not model:
                logger.info("[llm] %s skipped (missing key or model)", name)
                continue

            providers.append(
                OpenAICompatProvider(
                    name=name,
                    base_url=base_url,
                    api_key=api_key,
                    model_name=model,
                    timeout_seconds=timeout,
                    max_output_tokens=max_tokens,
                )
            )

        else:
            logger.warning("[llm] unknown provider '%s' in LLM_PROVIDER_ORDER", name)

    if not providers:
        providers.append(
            GeminiProvider(
                api_key=getattr(s, "GEMINI_API_KEY", ""),
                model_name=getattr(s, "GEMINI_MODEL", ""),
                timeout_seconds=timeout,
                max_output_tokens=max_tokens,
            )
        )

    return providers


def get_llm_provider() -> LLMProvider:
    """
    Return the application-wide LLM provider (created once, then reused).
    """
    global _provider_instance

    if _provider_instance is not None:
        return _provider_instance

    with _provider_lock:
        if _provider_instance is not None:
            return _provider_instance

        providers = _build_providers()
        print(f"[LLM] provider order: {[p.name for p in providers]}")
        _provider_instance = FallbackProvider(providers)
        return _provider_instance


def reset_llm_provider_cache() -> None:
    """Reset the provider instance (tests, or when configuration changes)."""
    global _provider_instance

    with _provider_lock:
        _provider_instance = None
