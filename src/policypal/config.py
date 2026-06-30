from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional
from pydantic import Field, SecretStr
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Environment & Logging:

    environment: Literal["development", "productin"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "CRITICAL", "ERROR"] = "INFO"
    log_dir: str = "logs/backend"

    # Database PostgreSQL + pgvector

    database_url: str = Field(...,description="SQLAlchemy Postgres URL for connection.")

    # Embedding

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # HF Token

    hf_api_key: Optional[SecretStr] = None

    # RAG Chunking

    chunk_size: int = 350
    chunk_overlap: int = 0


@lru_cache
def get_settings():
    "Returns a Settings object for this project"

    return Settings()


settings = get_settings()
