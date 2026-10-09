"""
Central configuration for the backend.
Reads all secrets/config from environment variables -- nothing is hard-coded.

NOTE: env vars are read inside __init__, not as class-body attribute
defaults. Class-body defaults are evaluated exactly once, at import time,
which would silently defeat get_settings.cache_clear() in tests.
"""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root

# Explicit path: don't rely on python-dotenv's upward directory search,
# which depends on where uvicorn is launched from and can silently find
# the wrong .env (or none at all).
load_dotenv(BASE_DIR / "backend" / ".env")


class Settings:
    def __init__(self) -> None:
        # --- App ---
        self.APP_NAME: str = "Context-Aware Multilingual Legal Assistant"
        self.ENV: str = os.getenv("ENV", "development")
        self.DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

        # --- CORS ---
        self.CORS_ORIGINS: list[str] = os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")

        # --- Gemini ---
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        # --- Database ---
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL", f"sqlite:///{BASE_DIR}/backend/nyaya.db"
        )

        # --- Vector store ---
        self.VECTOR_STORE_DIR: str = os.getenv(
            "VECTOR_STORE_DIR", str(BASE_DIR / "vector_store")
        )
        self.VECTOR_STORE_BACKEND: str = os.getenv("VECTOR_STORE_BACKEND", "chroma")  # or "faiss"

        # --- Embeddings ---
        self.EMBEDDING_MODEL: str = os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        )
        # Dev/CI only: fall back to a non-semantic deterministic embedder when
        # sentence-transformers isn't installed. Never enable in production.
        self.ALLOW_DEV_EMBEDDING_FALLBACK: bool = (
            os.getenv("ALLOW_DEV_EMBEDDING_FALLBACK", "false").lower() == "true"
        )

        # --- Data paths ---
        self.DATA_RAW_DIR: str = str(BASE_DIR / "data" / "raw")
        self.DATA_PROCESSED_DIR: str = str(BASE_DIR / "data" / "processed")
        self.UPLOADS_DIR: str = str(BASE_DIR / "uploads")

        # --- Retrieval ---
        self.TOP_K_CANDIDATES: int = int(os.getenv("TOP_K_CANDIDATES", "20"))
        self.TOP_K_FINAL: int = int(os.getenv("TOP_K_FINAL", "5"))

        # --- Conversation limits (keep Gemini free-tier usage economical) ---
        self.MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "6"))
        self.MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "8000"))

        # --- Speech-to-text provider (swappable) ---
        self.STT_PROVIDER: str = os.getenv("STT_PROVIDER", "faster-whisper")
        # faster-whisper model size: tiny/base/small/medium/large-v3.
        # "small" is the practical default for a laptop CPU (en/hi/kn supported).
        self.STT_MODEL_SIZE: str = os.getenv("STT_MODEL_SIZE", "small")
        self.STT_DEVICE: str = os.getenv("STT_DEVICE", "cpu")
        # int8 keeps CPU inference fast; use "float16" if STT_DEVICE=cuda.
        self.STT_COMPUTE_TYPE: str = os.getenv("STT_COMPUTE_TYPE", "int8")

        # --- Uploads ---
        self.MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.ALLOWED_UPLOAD_EXTENSIONS: set[str] = {".pdf", ".docx", ".txt"}

        # --- Voice uploads (MediaRecorder audio) ---
        self.MAX_VOICE_UPLOAD_MB: int = int(os.getenv("MAX_VOICE_UPLOAD_MB", "15"))
        self.ALLOWED_VOICE_EXTENSIONS: set[str] = {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4"}

        # --- Text-to-speech provider (swappable) ---
        self.TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "gtts")

        # --- Email (signup verification code + forgot-password code) ---
        self.EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "smtp")
        self.SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
        # A Gmail *App Password* (16 characters, no spaces) -- NOT your normal
        # Gmail password. Create one at https://myaccount.google.com/apppasswords
        # (2-Step Verification must be turned on first).
        self.SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
        self.SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", self.SMTP_USERNAME)
        self.SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Context-Aware Multilingual Legal Assistant")


@lru_cache
def get_settings() -> Settings:
    return Settings()