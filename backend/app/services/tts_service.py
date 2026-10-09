"""
Text-to-speech service (Phase 17, "read the answer aloud").

Most of NyayaAI's target users are in rural areas and may not be able
to read or write -- Phase 13 already covers *asking* a question by
voice (STT); this phase covers the other half: *hearing* the answer
read back, so a fully non-literate user can complete an entire
question-answer turn without reading or typing a single character.

Wraps whichever TTS engine NyayaAI uses behind one small interface,
exactly mirroring voice_service.py's STTProvider pattern:

    TTSProvider
        └── synthesize(text, language) -> bytes (audio/mpeg)

Rule 10 ("keep providers replaceable"): everything in this module goes
through the TTSProvider interface. Swapping engines (e.g. a hosted,
higher-quality voice API) means writing one new TTSProvider subclass
and pointing TTS_PROVIDER at it -- api/voice.py never imports gTTS
directly.

gTTS (Google Translate's TTS endpoint) is used for the same reason
faster-whisper was chosen for STT: it covers all three of this
project's languages (en/hi/kn) with one provider instead of three, and
needs no bundled voice models. Unlike faster-whisper's one-time model
download, gTTS calls out to Google on every request (network required
every time, not just once) -- documented in the class docstring below
so this trade-off is visible to whoever configures a production
deployment.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from io import BytesIO

from app.config import get_settings
from app.services.language_service import SUPPORTED_LANGUAGES


class TTSServiceError(Exception):
    """Base for all errors this module raises. api/voice.py catches
    these -- never a raw gTTS/urllib exception -- so a library upgrade
    that renames an internal exception class can't silently break
    error handling one layer up."""


class TTSNotAvailableError(TTSServiceError):
    """Raised when the TTS engine isn't installed or can't be reached
    (e.g. no network). Distinct from TTSSynthesisError so callers can
    show "voice output isn't available right now" rather than
    "couldn't read that particular answer"."""


class TTSSynthesisError(TTSServiceError):
    """Raised when a specific piece of text fails to synthesize
    (empty text, text too long, engine rejected the language, etc)."""


class TTSProvider(ABC):
    name: str = "base"

    @abstractmethod
    def synthesize(self, text: str, language: str) -> bytes:
        """
        Converts text to speech and returns raw MP3 bytes.

        language: one of language_service.SUPPORTED_LANGUAGES
        ("en"/"hi"/"kn") -- the same three languages spec section 33
        already commits this project to for input, so no new language
        surface is introduced for output.
        """
        ...


class GTTSProvider(TTSProvider):
    """Real provider, backed by gTTS. Unlike
    FasterWhisperProvider's lazy-loaded local model, there is no
    "model" to load here -- each call is a lightweight HTTP request to
    Google Translate's TTS endpoint, made fresh every time, so there
    is nothing to cache process-wide beyond this instance itself."""
    name = "gtts"

    def synthesize(self, text: str, language: str) -> bytes:
        cleaned = text.strip()
        if not cleaned:
            raise TTSSynthesisError("No text was provided to read aloud.")

        lang = language if language in SUPPORTED_LANGUAGES else "en"

        try:
            from gtts import gTTS
        except ImportError as exc:
            raise TTSNotAvailableError(
                "gTTS is not installed. Run: pip install -r backend/requirements.txt"
            ) from exc

        try:
            buffer = BytesIO()
            gTTS(text=cleaned, lang=lang).write_to_fp(buffer)
        except Exception as exc:
            # gTTS raises its own exceptions for both "can't reach
            # Google" (network down) and "Google rejected this
            # input" (e.g. unsupported language) -- from api/voice.py's
            # perspective both mean "voice output isn't available
            # right now", not "this specific answer is unreadable",
            # so both map to TTSNotAvailableError rather than
            # TTSSynthesisError.
            raise TTSNotAvailableError(f"Unable to reach the text-to-speech engine: {exc}") from exc

        audio_bytes = buffer.getvalue()
        if not audio_bytes:
            raise TTSSynthesisError("Text-to-speech produced no audio.")
        return audio_bytes


_provider_lock = threading.Lock()
_provider_instance: TTSProvider | None = None


def get_tts_provider() -> TTSProvider:
    """Single place the rest of the app calls to get a TTS provider.
    Reads config: TTS_PROVIDER."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance
    with _provider_lock:
        if _provider_instance is not None:
            return _provider_instance
        settings = get_settings()
        if settings.TTS_PROVIDER != "gtts":
            raise TTSNotAvailableError(
                f"Unknown TTS_PROVIDER '{settings.TTS_PROVIDER}'. "
                "Only 'gtts' is implemented -- add a new TTSProvider "
                "subclass and register it here to support another engine (Rule 10)."
            )
        _provider_instance = GTTSProvider()
        return _provider_instance


def reset_tts_provider_cache() -> None:
    """Test-only helper: forces the next get_tts_provider() call to
    build a fresh instance (e.g. after changing TTS_PROVIDER in a test)."""
    global _provider_instance
    with _provider_lock:
        _provider_instance = None
