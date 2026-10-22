from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.8-flash"
    EMBEDDING_MODEL: str = "gemini-embedding-001"

    DATABASE_PATH: str = str(BASE_DIR / "data" / "knowledge_inbox.db")

    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100
    TOP_K: int = 4
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    MAX_BATCH_FILES: int = 10
    MAX_URL_BYTES: int = 2 * 1024 * 1024

    PORT: int = 8000
    HOST: str = "127.0.0.1"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
