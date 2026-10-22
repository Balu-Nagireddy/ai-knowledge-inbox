import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory for the backend
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # Gemini API
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.8-flash"
    EMBEDDING_MODEL: str = "gemini-embedding-001"

    # Database
    DATABASE_PATH: str = str(BASE_DIR / "data" / "knowledge_inbox.db")

    # Ingestion & RAG
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100
    TOP_K: int = 4

    # Server & Logging
    PORT: int = 8000
    HOST: str = "127.0.0.1"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
