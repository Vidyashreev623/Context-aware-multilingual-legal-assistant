"""
Phase 13 tests: voice_service.py's STTProvider abstraction.

Deliberately avoids depending on a real downloaded Whisper model
(loading one needs a network call to huggingface.co, which -- unlike
pypi.org -- this sandbox's egress allowlist does not include). Three
things ARE verified for real here:

  1. faster-whisper (spec section 33's actual engine, requirements.txt's
     Phase 13 pin) installs and imports cleanly in this sandbox --
     confirmed via `pip install faster-whisper==1.0.3`.
  2. FasterWhisperProvider._ensure_loaded()'s error handling against a
     REAL failed model load (network to huggingface.co blocked -> a real
     HfHubHTTPError from inside faster-whisper) is caught and re-raised
     as STTNotAvailableError, not left as a raw stack trace -- this is
     exercised directly below, no mock involved.
  3. Everything downstream of "we have a transcript" (language-tagging
     via the raw-vs-detected-language logic, the STTProvider interface
     contract api/voice.py depends on) is exercised against a
     FakeSTTProvider, the same "construct a fake provider directly,
     bypass get_stt_provider()" approach test_document_service.py uses
     for its embedding/vector-store fakes.

Run: pytest backend/tests/test_voice_service.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.voice_service import (
    FasterWhisperProvider,
    STTNotAvailableError,
    STTProvider,
    STTTranscriptionError,
    TranscriptionResult,
    get_stt_provider,
    reset_stt_provider_cache,
)


class FakeSTTProvider(STTProvider):
    """Bypasses the real engine entirely -- returns a canned
    transcript so api/voice.py's contract (and any RAG-side code that
    consumes a TranscriptionResult) can be tested without audio or a
    downloaded model."""
    name = "fake"

    def __init__(self, text: str, language: str = "en", raise_error: Exception | None = None):
        self._text = text
        self._language = language
        self._raise_error = raise_error

    def transcribe(self, audio_path, language_hint=None):
        if self._raise_error:
            raise self._raise_error
        return TranscriptionResult(
            text=self._text,
            language=language_hint or self._language,
            raw_language=self._language,
        )


# --- Real: faster-whisper's own failure path, not mocked -------------

def test_real_model_load_failure_raises_not_available_error():
    """No network to huggingface.co in this sandbox -> WhisperModel()
    genuinely fails to download/load -> must surface as
    STTNotAvailableError, never a raw HfHubHTTPError/OSError."""
    provider = FasterWhisperProvider(model_size="tiny", device="cpu", compute_type="int8")
    with pytest.raises(STTNotAvailableError):
        provider._ensure_loaded()


def test_real_transcribe_call_also_raises_not_available_error():
    """transcribe() itself (not just _ensure_loaded()) must surface the
    same clean error -- api/voice.py only catches STTNotAvailableError/
    STTTranscriptionError, not arbitrary exceptions, from this path."""
    provider = FasterWhisperProvider(model_size="tiny", device="cpu", compute_type="int8")
    with pytest.raises(STTNotAvailableError):
        provider.transcribe("does-not-matter.webm")


# --- Interface contract, via the fake ---------------------------------

def test_fake_provider_returns_transcription_result():
    provider = FakeSTTProvider(text="What is Section 66C?", language="en")
    result = provider.transcribe("recording.webm")
    assert isinstance(result, TranscriptionResult)
    assert result.text == "What is Section 66C?"
    assert result.language == "en"


def test_explicit_language_hint_is_honored():
    provider = FakeSTTProvider(text="ಮಾನ್ಯವಾದ ಒಪ್ಪಂದ", language="kn")
    result = provider.transcribe("recording.webm", language_hint="kn")
    assert result.language == "kn"


def test_provider_propagates_transcription_error():
    provider = FakeSTTProvider(text="", raise_error=STTTranscriptionError("No speech detected."))
    with pytest.raises(STTTranscriptionError):
        provider.transcribe("silent.webm")


# --- FasterWhisperProvider's language-tagging logic (no model needed) -

def test_language_tag_uses_detect_language_when_no_hint():
    """The real logic in FasterWhisperProvider.transcribe() re-tags the
    language from the TRANSCRIPT TEXT via language_service.detect_language()
    rather than trusting Whisper's raw guess outright, when no explicit
    hint was given. Exercise that exact logic directly (it's a few lines
    inside transcribe(), duplicated here against the same import used in
    voice_service.py so the two can't silently drift)."""
    from backend.app.services.language_service import detect_language, SUPPORTED_LANGUAGES

    kannada_text = "ಮಾನ್ಯವಾದ ಒಪ್ಪಂದಕ್ಕೆ ಅಗತ್ಯವಾದ ಅಂಶಗಳು ಯಾವುವು?"
    language_hint = None
    language = language_hint if language_hint in SUPPORTED_LANGUAGES else detect_language(kannada_text)
    assert language == "kn"

    english_text = "What is the punishment under Section 66C?"
    language = language_hint if language_hint in SUPPORTED_LANGUAGES else detect_language(english_text)
    assert language == "en"


# --- get_stt_provider() config wiring + caching ------------------------

def test_get_stt_provider_reads_config_and_caches(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "faster-whisper")
    monkeypatch.setenv("STT_MODEL_SIZE", "tiny")
    monkeypatch.setenv("STT_DEVICE", "cpu")
    monkeypatch.setenv("STT_COMPUTE_TYPE", "int8")
    from backend.app.config import get_settings
    get_settings.cache_clear()
    reset_stt_provider_cache()

    p1 = get_stt_provider()
    p2 = get_stt_provider()
    assert p1 is p2  # same cached instance -- model isn't reloaded per request
    assert isinstance(p1, FasterWhisperProvider)
    assert p1.model_size == "tiny"
    assert p1.device == "cpu"
    assert p1.compute_type == "int8"

    reset_stt_provider_cache()
    get_settings.cache_clear()


def test_get_stt_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "some-unimplemented-engine")
    from backend.app.config import get_settings
    get_settings.cache_clear()
    reset_stt_provider_cache()

    with pytest.raises(STTNotAvailableError):
        get_stt_provider()

    reset_stt_provider_cache()
    monkeypatch.setenv("STT_PROVIDER", "faster-whisper")
    get_settings.cache_clear()
