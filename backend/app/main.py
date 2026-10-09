"""
NyayaAI backend entrypoint.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database.database import init_db
from app.database.user_repository import ensure_auth_schema
from app.api import health, chat, upload, voice, conversations, documents
from app.api.auth import router as auth_router

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="Context-Aware Multilingual Indian Legal Assistant (RAG + Gemini)",
    version="0.1.0",
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    ensure_auth_schema()

    from app.services.embedding_service import get_embedding_provider
    try:
        get_embedding_provider().embed_text("warmup")
        print("[STARTUP] Embedding model warmed up.")
    except Exception as e:
        print(f"[STARTUP] Embedding warmup failed (will retry on first request): {e}")

    from app.services.gemini_service import get_llm_provider
    try:
        get_llm_provider().generate(
            "You are a warmup check. Reply with a single word.", "ping"
        )
        print("[STARTUP] Gemini client warmed up.")
    except Exception as e:
        print(f"[STARTUP] Gemini warmup failed (will retry on first request): {e}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(voice.router, prefix="/api", tags=["voice"])
app.include_router(conversations.router, prefix="/api", tags=["conversations"])


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "status": "running",
        "phase": "1 - project setup",
        "docs": "/docs",
    }