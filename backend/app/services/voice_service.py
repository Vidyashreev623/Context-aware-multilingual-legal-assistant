"""
Speech-to-text service (Phase 13, spec sections 32-33).

Wraps whichever STT engine NyayaAI uses behind one small interface:

    STTProvider
        └── transcribe(audio_path, language_hint=None) -> TranscriptionResult

Rule 10 ("keep speech-to-text providers replaceable"): everything in
this module goes through the STTProvider interface. Swapping engines
(e.g. a hosted API instead of a local model) means writing one new
STTProvider subclass and pointing STT_PROVIDER at it -- api/voice.py
and the rest of the RAG pipeline never import faster-whisper directly.

Unlike embedding_service.py's DeterministicDevFallbackProvider, there
is no meaningful non-network dev fallback here: a hash of audio bytes
cannot stand in for a transcript the way a hash-based pseudo-vector
can stand in for an embedding, because the whole point of this module
is to produce real text for a real RAG query. Offline pipeline tests
therefore construct a FakeSTTProvider directly (see
tests/test_voice_service.py) rather than routing through
get_stt_provider() with a fallback flag.

faster-whisper (a CTranslate2 reimplementation of OpenAI's Whisper) is
multilingual out of the box -- English, Hindi and Kannada are all
supported by the same model, so one provider instance handles spec
section 33's three languages without per-language models or config.
The model is downloaded once on first use (network required then;
fully offline after that, same trade-off as
embedding_service.py's SentenceTransformerProvider).
"""
from __future__ import annotations

import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


from app.config import get_settings
from app.services.language_service import SUPPORTED_LANGUAGES, detect_language


class STTServiceError(Exception):
    """Base for all errors this module raises. api/voice.py catches
    these -- never a raw faster-whisper/ctranslate2/av exception --
    so a library upgrade that renames an internal exception class
    can't silently break error handling one layer up."""


class STTNotAvailableError(STTServiceError):
    """Raised when the STT engine/model isn't installed or couldn't be
    loaded. Distinct from STTTranscriptionError so callers can show
    "voice input isn't set up on this server" rather than "try a
    clearer recording"."""


class STTTranscriptionError(STTServiceError):
    """Raised when a specific recording fails to transcribe (corrupt/
    empty/silent audio, unsupported codec, decoder failure, etc)."""


@dataclass
class TranscriptionResult:
    text: str
    # One of language_service.SUPPORTED_LANGUAGES ("en"/"hi"/"kn") --
    # what the rest of the pipeline (chat.py, rag_service.py) actually
    # consumes.
    language: str
    # The STT engine's own raw language guess, kept only for
    # diagnostics/logging (e.g. it may report a language outside our
    # three supported ones for code-switched or noisy audio).
    raw_language: str | None = None


class STTProvider(ABC):
    name: str = "base"

    @abstractmethod
    def transcribe(self, audio_path: str | Path, language_hint: str | None = None) -> TranscriptionResult:
        """
        Transcribes the audio file at audio_path.

        language_hint: optional ISO 639-1 code ("en"/"hi"/"kn") from
        the user's explicit language selection (spec section 36). When
        given, the engine is told to decode in that language instead
        of auto-detecting -- more reliable for short/noisy clips.
        When None, the engine auto-detects.
        """
        ...


class FasterWhisperProvider(STTProvider):
    """Real provider, backed by faster-whisper. Model is lazy-loaded
    (and cached process-wide) on first use so importing this module,
    or even constructing this class, never triggers a slow model load
    or a network call on its own -- the same lazy pattern
    embedding_service.SentenceTransformerProvider uses."""
    name = "faster-whisper"

    def __init__(self, model_size: str, device: str, compute_type: str):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._lock = threading.Lock()

    def _ensure_loaded(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise STTNotAvailableError(
                    "faster-whisper is not installed. "
                    "Run: pip install -r backend/requirements.txt"
                ) from exc
            try:
                self._model = WhisperModel(
                    self.model_size, device=self.device, compute_type=self.compute_type
                )
            except Exception as exc:  # model download/load failure (e.g. no network on first run)
                raise STTNotAvailableError(
                    f"Unable to load the speech-to-text model ({self.model_size}): {exc}"
                ) from exc

    def transcribe(self, audio_path: str | Path, language_hint: str | None = None) -> TranscriptionResult:
        self._ensure_loaded()

        try:
            segments, info = self._model.transcribe(
                str(audio_path),
                language=language_hint,
                vad_filter=True,  # trims leading/trailing silence, spec section 32's "Recording... Stop" clips
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as exc:
            raise STTTranscriptionError(f"Unable to transcribe audio: {exc}") from exc

        if not text:
            raise STTTranscriptionError(
                "No speech was detected in the recording. Please try again closer to the microphone."
            )

        raw_language = getattr(info, "language", None)
        # detect_language() is script-based and only knows en/hi/kn
        # (language_service.py, Phase 7) -- it's a more reliable final
        # label for THIS project than trusting Whisper's guess among
        # its full ~99-language vocabulary, so the transcribed text
        # (not the raw engine guess) is the source of truth for the
        # language tag the rest of the pipeline sees. An explicit
        # language_hint always wins outright.
        language = language_hint if language_hint in SUPPORTED_LANGUAGES else detect_language(text)

        return TranscriptionResult(text=text, language=language, raw_language=raw_language)


_provider_lock = threading.Lock()
_provider_instance: STTProvider | None = None


def get_stt_provider() -> STTProvider:
    """Single place the rest of the app calls to get an STT provider.
    Reads config: STT_PROVIDER, STT_MODEL_SIZE, STT_DEVICE, STT_COMPUTE_TYPE.

    Cached process-wide so the (large, slow-to-load) Whisper model is
    loaded once per process, not once per request."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance
    with _provider_lock:
        if _provider_instance is not None:
            return _provider_instance
        settings = get_settings()
        if settings.STT_PROVIDER != "faster-whisper":
            raise STTNotAvailableError(
                f"Unknown STT_PROVIDER '{settings.STT_PROVIDER}'. "
                "Only 'faster-whisper' is implemented -- add a new STTProvider "
                "subclass and register it here to support another engine (Rule 10)."
            )
        _provider_instance = FasterWhisperProvider(
            settings.STT_MODEL_SIZE, settings.STT_DEVICE, settings.STT_COMPUTE_TYPE
        )
        return _provider_instance


def reset_stt_provider_cache() -> None:
    """Test-only helper: forces the next get_stt_provider() call to
    build a fresh instance (e.g. after changing STT_PROVIDER/
    STT_MODEL_SIZE in a test)."""
    global _provider_instance
    with _provider_lock:
        _provider_instance = None
