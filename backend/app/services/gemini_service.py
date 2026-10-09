"""
Gemini LLM service.

Wraps Gemini behind a small replaceable LLM interface.

The Gemini API key is read from GEMINI_API_KEY through config.py.
No Gemini calls are made from the React frontend.

This version uses the current google-genai SDK.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict

from app.config import get_settings


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class GeminiServiceError(Exception):
    """Base exception for Gemini service errors."""


class GeminiNotConfiguredError(GeminiServiceError):
    """Raised when GEMINI_API_KEY is missing."""

    pass


class GeminiRateLimitError(GeminiServiceError):
    """Raised when Gemini rate/quota limits remain after retries."""

    pass


class GeminiError(GeminiServiceError):
    """Raised for other Gemini/API failures."""

    pass


# ---------------------------------------------------------------------------
# LLM provider interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(
        self,
        system_instructions: str,
        user_message: str,
    ) -> str:
        """
        Generate an answer using the configured LLM.
        """
        ...


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """
    Gemini implementation using the google-genai SDK.
    """

    name = "gemini"

    # Number of retry attempts after the initial request.
    MAX_RETRIES = 4

    # Delay before each retry.
    RETRY_BACKOFF_SECONDS = (
        5,
        10,
        20,
        40,
    )

    # Maximum number of cached responses.
    CACHE_MAX_ENTRIES = 128

    def __init__(
        self,
        api_key: str,
        model_name: str,
    ):
        self.api_key = api_key
        self.model_name = model_name

        # Gemini client is created lazily.
        self._client = None

        # Protect client/cache when multiple requests happen together.
        self._lock = threading.Lock()

        # Simple in-memory cache.
        #
        # Key:
        #     (system_instructions, user_message)
        #
        # Value:
        #     generated response
        self._cache: OrderedDict[
            tuple[str, str],
            str,
        ] = OrderedDict()

    # -----------------------------------------------------------------------
    # Gemini client initialization
    # -----------------------------------------------------------------------

    def _ensure_configured(self) -> None:
        """
        Make sure the API key exists and the Gemini client is initialized.
        """

        if not self.api_key:
            raise GeminiNotConfiguredError(
                "GEMINI_API_KEY is not set. "
                "Add it to backend/.env."
            )

        # Already initialized.
        if self._client is not None:
            return

        with self._lock:

            # Another thread may have initialized it while we waited.
            if self._client is not None:
                return

            try:
                from google import genai
            except ImportError as exc:
                raise GeminiError(
                    "google-genai is not installed. "
                    "Run: pip install -r backend/requirements.txt"
                ) from exc

            try:
                self._client = genai.Client(
                    api_key=self.api_key
                )
            except Exception as exc:
                raise GeminiError(
                    f"Unable to initialize Gemini client: {exc}"
                ) from exc

    # -----------------------------------------------------------------------
    # Cache
    # -----------------------------------------------------------------------

    def _cache_get(
        self,
        key: tuple[str, str],
    ) -> str | None:
        """
        Get a cached response.
        """

        with self._lock:

            if key in self._cache:

                # Move recently used item to the end.
                self._cache.move_to_end(key)

                return self._cache[key]

        return None

    def _cache_put(
        self,
        key: tuple[str, str],
        value: str,
    ) -> None:
        """
        Store a response in the cache.
        """

        with self._lock:

            self._cache[key] = value

            # Mark as recently used.
            self._cache.move_to_end(key)

            # Remove oldest entries if cache is too large.
            while len(self._cache) > self.CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

    # -----------------------------------------------------------------------
    # Generate response
    # -----------------------------------------------------------------------

    def generate(
        self,
        system_instructions: str,
        user_message: str,
    ) -> str:
        """
        Generate a response from Gemini.
        """

        # Make sure Gemini is configured.
        self._ensure_configured()

        # ---------------------------------------------------------------
        # Check cache
        # ---------------------------------------------------------------

        cache_key = (
            system_instructions,
            user_message,
        )

        cached = self._cache_get(cache_key)

        if cached is not None:
            return cached

        # ---------------------------------------------------------------
        # Import current google-genai SDK components
        # ---------------------------------------------------------------

        try:
            from google.genai import errors
            from google.genai import types
        except ImportError as exc:
            raise GeminiError(
                "google-genai is not installed correctly. "
                "Run: pip install -r backend/requirements.txt"
            ) from exc

        # ---------------------------------------------------------------
        # Gemini request configuration
        # ---------------------------------------------------------------
        #
        # IMPORTANT:
        #
        # We intentionally DO NOT use:
        #
        #     ThinkingConfig(...)
        #
        # or:
        #
        #     thinking_level="low"
        #
        # because the installed SDK version rejected that field.
        #
        # The system instructions are passed through the supported
        # GenerateContentConfig class.
        # ---------------------------------------------------------------

        config = types.GenerateContentConfig(
            system_instruction=system_instructions,
        )

        last_exc: Exception | None = None

        # ---------------------------------------------------------------
        # Gemini request + retry logic
        # ---------------------------------------------------------------

        for attempt in range(self.MAX_RETRIES + 1):

            try:

                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=user_message,
                    config=config,
                )

                # -------------------------------------------------------
                # Extract response text
                # -------------------------------------------------------

                text = (response.text or "").strip()

                # Gemini may return an empty response.
                if not text:

                    raise GeminiError(
                        "Gemini returned an empty response. "
                        "This can happen when the response is blocked "
                        "by safety filters."
                    )

                # -------------------------------------------------------
                # Save successful response in cache
                # -------------------------------------------------------

                self._cache_put(
                    cache_key,
                    text,
                )

                return text

            # -----------------------------------------------------------
            # 4xx client errors
            # -----------------------------------------------------------

            except errors.ClientError as exc:

                # 429 = rate limit / quota exceeded.
                if exc.code == 429:

                    last_exc = exc

                    # Retry if attempts remain.
                    if attempt < self.MAX_RETRIES:

                        time.sleep(
                            self.RETRY_BACKOFF_SECONDS[attempt]
                        )

                        continue

                    # Retries exhausted.
                    raise GeminiRateLimitError(
                        "Gemini rate limit/quota exceeded "
                        "after retries."
                    ) from exc

                # Other 4xx errors should not be blindly retried.
                #
                # Examples:
                #   400 = bad request
                #   403 = authentication/permission
                #   404 = model not found
                #
                raise GeminiError(
                    f"Gemini API call failed: {exc}"
                ) from exc

            # -----------------------------------------------------------
            # 5xx server errors
            # -----------------------------------------------------------

            except errors.ServerError as exc:

                last_exc = exc

                # Retry temporary server failures.
                if attempt < self.MAX_RETRIES:

                    time.sleep(
                        self.RETRY_BACKOFF_SECONDS[attempt]
                    )

                    continue

                raise GeminiError(
                    f"Gemini API server error after retries: {exc}"
                ) from exc

            # -----------------------------------------------------------
            # Other Google API errors
            # -----------------------------------------------------------

            except errors.APIError as exc:

                raise GeminiError(
                    f"Gemini API call failed: {exc}"
                ) from exc

            # -----------------------------------------------------------
            # Unexpected Python/SDK errors
            # -----------------------------------------------------------

            except Exception as exc:

                raise GeminiError(
                    f"Unexpected Gemini error: {exc}"
                ) from exc

        # This should normally never be reached.
        raise GeminiError(
            f"Gemini call failed: {last_exc}"
        )


# ---------------------------------------------------------------------------
# Global provider instance
# ---------------------------------------------------------------------------

_provider_lock = threading.Lock()

_provider_instance: LLMProvider | None = None


# ---------------------------------------------------------------------------
# Get provider
# ---------------------------------------------------------------------------

def get_llm_provider() -> LLMProvider:
    """
    Return the application-wide LLM provider.

    The provider is created once and reused for subsequent requests.
    """

    global _provider_instance

    # Fast path.
    if _provider_instance is not None:
        return _provider_instance

    with _provider_lock:

        # Check again after acquiring the lock.
        if _provider_instance is not None:
            return _provider_instance

        settings = get_settings()

        _provider_instance = GeminiProvider(
            api_key=settings.GEMINI_API_KEY,
            model_name=settings.GEMINI_MODEL,
        )

        return _provider_instance


# ---------------------------------------------------------------------------
# Reset provider cache
# ---------------------------------------------------------------------------

def reset_llm_provider_cache() -> None:
    """
    Reset the provider instance.

    Mainly useful for tests or when configuration changes.
    """

    global _provider_instance

    with _provider_lock:
        _provider_instance = None