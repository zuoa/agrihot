"""Application settings, loaded from environment / .env file."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # asyncpg DSN; default targets local Homebrew PostgreSQL
    database_url: str = "postgresql+asyncpg://localhost:5432/agrihot"
    # comma-separated list; "*" for dev
    cors_origins: str = "*"
    # ingest rate limit per API key (slowapi format)
    ingest_rate_limit: str = "60/minute"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
