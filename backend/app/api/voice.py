"""
Voice transcription endpoint (Phase 13, spec sections 32-33).

Flow (spec section 32):
    Audio (MediaRecorder blob, e.g. audio/webm)
     |
     v
    validate type/size (mirrors api/upload.py's pattern, spec section 51)
     |
     v
    save to a private temp file (never the permanent uploads/ dir --
    a voice question isn't a document the user asked to keep)
     |
     v
    voice_service.get_stt_provider().transcribe()
     |
     v
    delete the temp file/dir (try/finally -- always cleaned up, spec
    section 51's "Temporary storage / Cleanup")
     |
     v
    {"text": ..., "language": ...}   <- exactly what the frontend
                                          (services/api.ts's
                                          transcribeVoice, already
                                          written since Phase 1) expects

The transcript is returned to the frontend rather than fed straight
into the RAG pipeline server-side, because VoiceRecorder.tsx drops it
into the same chat text box a typed question would go through (spec
section 32: "You said: ... followed by the answer") -- so it goes
through the exact same /api/chat path, history, and document
attachments a typed message would, with no separate voice-only code
path to keep in sync (Rule 9: keep RAG components modular).
"""
import tempfile
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.voice_service import (
    STTNotAvailableError,
    STTTranscriptionError,
    get_stt_provider,
)
from app.services.tts_service import (
    TTSNotAvailableError,
    TTSSynthesisError,
    get_tts_provider,
)

router = APIRouter()
settings = get_settings()


@router.post("/voice/transcribe")
async def transcribe_voice(audio: UploadFile = File(...)):
    ext = Path(audio.filename or "").suffix.lower() or ".webm"
    if ext not in settings.ALLOWED_VOICE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio type '{ext}'. Allowed: {sorted(settings.ALLOWED_VOICE_EXTENSIONS)}",
        )

    contents = await audio.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb == 0:
        raise HTTPException(status_code=400, detail="Received an empty audio recording.")
    if size_mb > settings.MAX_VOICE_UPLOAD_MB:
        raise HTTPException(
            status_code=400,
            detail=f"Audio file too large ({size_mb:.1f} MB). Max {settings.MAX_VOICE_UPLOAD_MB} MB.",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="nyaya_voice_"))
    tmp_path = tmp_dir / f"recording{ext}"
    tmp_path.write_bytes(contents)

    try:
        provider = get_stt_provider()
        result = provider.transcribe(tmp_path)
    except STTNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except STTTranscriptionError as exc:
        raise HTTPException(status_code=422, detail="Voice transcription failed. " + str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive: never leak a stack trace
        raise HTTPException(status_code=500, detail="Voice transcription failed.") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {"text": result.text, "language": result.language}


# Max characters sent to the TTS engine per request. An assistant
# answer is a paragraph or two, not a document -- this catches a
# runaway/misused request rather than reflecting any real engine
# limit, mirroring the defensive size checks /voice/transcribe and
# api/upload.py already do on their own inputs.
MAX_SYNTHESIZE_CHARS = 4000


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_SYNTHESIZE_CHARS)
    # One of language_service.SUPPORTED_LANGUAGES ("en"/"hi"/"kn").
    # Matches the language the answer was actually generated in
    # (ChatMessage.language on the frontend) so the reading matches
    # what's on screen, not the UI's separate input-language selector.
    language: str = "en"


@router.post("/voice/synthesize")
async def synthesize_voice(req: SynthesizeRequest):
    """
    Reads an assistant answer aloud (spec: voice *output*, the
    counterpart to /voice/transcribe's voice *input*). Built for users
    who can't read or write -- the whole point is that nothing here
    requires them to read anything to use it.

    Returns raw MP3 bytes directly (audio/mpeg), not JSON, since the
    frontend just wants an <audio> source, not a data structure.
    """
    try:
        provider = get_tts_provider()
        audio_bytes = provider.synthesize(req.text, req.language)
    except TTSNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TTSSynthesisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive: never leak a stack trace
        raise HTTPException(status_code=500, detail="Text-to-speech failed.") from exc

    return Response(content=audio_bytes, media_type="audio/mpeg")
