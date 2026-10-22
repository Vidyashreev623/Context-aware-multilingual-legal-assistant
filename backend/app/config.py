
"""
Central configuration for the backend.

Reads secrets and configuration from environment variables.
No API keys are hard-coded.

Environment variables are loaded from backend/.env.
Settings are initialized inside __init__ so that clearing
get_settings()'s cache reloads the current environment values.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load the backend .env explicitly.
ENV_FILE = BASE_DIR / "backend" / ".env"
load_dotenv(ENV_FILE)


class Settings:
    def __init__(self) -> None:
        # --- App ---
        self.APP_NAME: str = "Context-Aware Multilingual Legal Assistant"
        self.ENV: str = os.getenv("ENV", "development")
        self.DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

        # --- CORS ---
        self.CORS_ORIGINS: list[str] = [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]

        # --- Gemini ---
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL: str = os.getenv(
            "GEMINI_MODEL",
            "gemini-flash-lite-latest",
        )

        # --- xAI Grok ---
        self.XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
        self.XAI_MODEL: str = os.getenv("XAI_MODEL", "")

        # --- Groq ---
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
        self.GROQ_MODEL: str = os.getenv("GROQ_MODEL", "")

        # --- Cerebras ---
        self.CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")
        self.CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "")

        # --- OpenRouter ---
        self.OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
        self.OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "")

        # --- LLM provider configuration ---
        # Order: Grok first, Gemini second by default.
        self.LLM_PROVIDER_ORDER: str = os.getenv(
            "LLM_PROVIDER_ORDER",
            "xai,gemini",
        )

        self.LLM_TIMEOUT_SECONDS: float = float(
            os.getenv("LLM_TIMEOUT_SECONDS", "20")
        )

        self.LLM_MAX_OUTPUT_TOKENS: int = int(
            os.getenv("LLM_MAX_OUTPUT_TOKENS", "1024")
        )

        # --- Database ---
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            f"sqlite:///{BASE_DIR / 'backend' / 'nyaya.db'}",
        )

        # --- Vector store ---
        self.VECTOR_STORE_DIR: str = os.getenv(
            "VECTOR_STORE_DIR",
            str(BASE_DIR / "vector_store"),
        )

        self.VECTOR_STORE_BACKEND: str = os.getenv(
            "VECTOR_STORE_BACKEND",
            "chroma",
        )

        # --- Embeddings ---
        self.EMBEDDING_MODEL: str = os.getenv(
            "EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        )

        self.ALLOW_DEV_EMBEDDING_FALLBACK: bool = (
            os.getenv(
                "ALLOW_DEV_EMBEDDING_FALLBACK",
                "false",
            ).lower()
            == "true"
        )

        # --- Data paths ---
        self.DATA_RAW_DIR: str = str(BASE_DIR / "data" / "raw")
        self.DATA_PROCESSED_DIR: str = str(BASE_DIR / "data" / "processed")
        self.UPLOADS_DIR: str = str(BASE_DIR / "uploads")

        # --- Retrieval ---
        self.TOP_K_CANDIDATES: int = int(
            os.getenv("TOP_K_CANDIDATES", "20")
        )

        self.TOP_K_FINAL: int = int(
            os.getenv("TOP_K_FINAL", "5")
        )

        # --- Conversation limits ---
        self.MAX_HISTORY_TURNS: int = int(
            os.getenv("MAX_HISTORY_TURNS", "6")
        )

        self.MAX_CONTEXT_CHARS: int = int(
            os.getenv("MAX_CONTEXT_CHARS", "8000")
        )

        # --- Speech-to-text ---
        self.STT_PROVIDER: str = os.getenv(
            "STT_PROVIDER",
            "faster-whisper",
        )

        self.STT_MODEL_SIZE: str = os.getenv(
            "STT_MODEL_SIZE",
            "small",
        )

        self.STT_DEVICE: str = os.getenv(
            "STT_DEVICE",
            "cpu",
        )

        self.STT_COMPUTE_TYPE: str = os.getenv(
            "STT_COMPUTE_TYPE",
            "int8",
        )

        # --- Uploads ---
        self.MAX_UPLOAD_MB: int = int(
            os.getenv("MAX_UPLOAD_MB", "20")
        )

        self.ALLOWED_UPLOAD_EXTENSIONS: set[str] = {
            ".pdf",
            ".docx",
            ".txt",
        }

        # --- Voice uploads ---
        self.MAX_VOICE_UPLOAD_MB: int = int(
            os.getenv("MAX_VOICE_UPLOAD_MB", "15")
        )

        self.ALLOWED_VOICE_EXTENSIONS: set[str] = {
            ".webm",
            ".wav",
            ".mp3",
            ".m4a",
            ".ogg",
            ".mp4",
        }

        # --- Text-to-speech ---
        self.TTS_PROVIDER: str = os.getenv(
            "TTS_PROVIDER",
            "gtts",
        )

        # --- Email verification / password recovery ---
        self.EMAIL_PROVIDER: str = os.getenv(
            "EMAIL_PROVIDER",
            "smtp",
        )

        self.SMTP_HOST: str = os.getenv(
            "SMTP_HOST",
            "smtp.gmail.com",
        )

        self.SMTP_PORT: int = int(
            os.getenv("SMTP_PORT", "587")
        )

        self.SMTP_USERNAME: str = os.getenv(
            "SMTP_USERNAME",
            "",
        )

        # Use a Gmail App Password, not the normal account password.
        self.SMTP_PASSWORD: str = os.getenv(
            "SMTP_PASSWORD",
            "",
        )

        self.SMTP_FROM_EMAIL: str = os.getenv(
            "SMTP_FROM_EMAIL",
            self.SMTP_USERNAME,
        )

        self.SMTP_FROM_NAME: str = os.getenv(
            "SMTP_FROM_NAME",
            "Context-Aware Multilingual Legal Assistant",
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
