"""
Phase 13 tests: the /api/voice/transcribe endpoint (api/voice.py) end
to end through a real FastAPI TestClient -- request validation,
temp-file handling, and error-status mapping, with the STT engine
itself swapped for a fake (no model download needed, same rationale
as test_voice_service.py).

This is the first API-layer test file in the project (prior phases'
API code was reviewed by hand + py_compile only, per PHASES.md, since
earlier sandbox runs had no network to install fastapi/httpx). This
sandbox does, so it's exercised for real here via Starlette's
TestClient (bundled with fastapi -- no separate httpx test dependency
needed for a synchronous TestClient).

Run: pytest backend/tests/test_voice_api.py -v
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))  # so `import app...` (as main.py itself uses) resolves
sys.path.insert(0, str(BACKEND_DIR.parent))  # so `import backend.app...` also resolves

import app.api.voice as voice_api  # noqa: E402
from app.main import app  # noqa: E402
from app.services.voice_service import (  # noqa: E402
    STTNotAvailableError,
    STTTranscriptionError,
    STTProvider,
    TranscriptionResult,
)

client = TestClient(app)


class _StubProvider(STTProvider):
    name = "stub"

    def __init__(self, text="What is Section 66C?", language="en", error: Exception | None = None):
        self.text, self.language, self.error = text, language, error

    def transcribe(self, audio_path, language_hint=None):
        if self.error:
            raise self.error
        # Confirms the endpoint actually wrote real bytes to a real
        # temp file before calling us, rather than passing e.g. the
        # raw UploadFile through.
        assert Path(audio_path).exists()
        assert Path(audio_path).stat().st_size > 0
        return TranscriptionResult(text=self.text, language=self.language, raw_language=self.language)


@pytest.fixture(autouse=True)
def _reset_provider(monkeypatch):
    # api/voice.py calls get_stt_provider() by name inside the handler,
    # so patching the module-level symbol it imported is what actually
    # takes effect (patching voice_service.get_stt_provider itself
    # would miss the `from ... import get_stt_provider` binding).
    yield


def _fake_audio_bytes() -> bytes:
    return b"RIFF....WAVEfmt fake-audio-not-real-but-nonzero-bytes"


def test_successful_transcription_returns_text_and_language(monkeypatch):
    monkeypatch.setattr(voice_api, "get_stt_provider", lambda: _StubProvider(text="ಸೆಕ್ಷನ್ 66C ಎಂದರೇನು?", language="kn"))
    res = client.post(
        "/api/voice/transcribe",
        files={"audio": ("recording.webm", io.BytesIO(_fake_audio_bytes()), "audio/webm")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == "ಸೆಕ್ಷನ್ 66C ಎಂದರೇನು?"
    assert body["language"] == "kn"


def test_unsupported_extension_rejected_before_calling_provider(monkeypatch):
    called = {"yes": False}

    def _should_not_be_called():
        called["yes"] = True
        return _StubProvider()

    monkeypatch.setattr(voice_api, "get_stt_provider", _should_not_be_called)
    res = client.post(
        "/api/voice/transcribe",
        files={"audio": ("recording.exe", io.BytesIO(_fake_audio_bytes()), "application/octet-stream")},
    )
    assert res.status_code == 400
    assert "Unsupported audio type" in res.json()["detail"]
    assert called["yes"] is False


def test_empty_recording_rejected():
    res = client.post(
        "/api/voice/transcribe",
        files={"audio": ("recording.webm", io.BytesIO(b""), "audio/webm")},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_engine_not_available_maps_to_503(monkeypatch):
    monkeypatch.setattr(
        voice_api, "get_stt_provider",
        lambda: _StubProvider(error=STTNotAvailableError("faster-whisper is not installed.")),
    )
    res = client.post(
        "/api/voice/transcribe",
        files={"audio": ("recording.webm", io.BytesIO(_fake_audio_bytes()), "audio/webm")},
    )
    assert res.status_code == 503


def test_transcription_failure_maps_to_422_with_safe_message(monkeypatch):
    monkeypatch.setattr(
        voice_api, "get_stt_provider",
        lambda: _StubProvider(error=STTTranscriptionError("No speech was detected in the recording.")),
    )
    res = client.post(
        "/api/voice/transcribe",
        files={"audio": ("recording.webm", io.BytesIO(_fake_audio_bytes()), "audio/webm")},
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert "Voice transcription failed" in detail
    assert "Traceback" not in detail  # spec section 50: never a raw stack trace


def test_unexpected_exception_maps_to_500_without_leaking_details(monkeypatch):
    monkeypatch.setattr(
        voice_api, "get_stt_provider",
        lambda: _StubProvider(error=RuntimeError("some internal ctranslate2 detail nobody should see")),
    )
    res = client.post(
        "/api/voice/transcribe",
        files={"audio": ("recording.webm", io.BytesIO(_fake_audio_bytes()), "audio/webm")},
    )
    assert res.status_code == 500
    assert res.json()["detail"] == "Voice transcription failed."


def test_temp_file_is_cleaned_up_after_request(monkeypatch, tmp_path):
    captured_path = {}

    class _CapturingProvider(STTProvider):
        name = "capturing"

        def transcribe(self, audio_path, language_hint=None):
            captured_path["path"] = Path(audio_path)
            return TranscriptionResult(text="ok", language="en")

    monkeypatch.setattr(voice_api, "get_stt_provider", lambda: _CapturingProvider())
    res = client.post(
        "/api/voice/transcribe",
        files={"audio": ("recording.webm", io.BytesIO(_fake_audio_bytes()), "audio/webm")},
    )
    assert res.status_code == 200
    # spec section 51: temp file + its containing temp dir must both be
    # gone after the request completes, not left behind.
    assert not captured_path["path"].exists()
    assert not captured_path["path"].parent.exists()
