"""Application settings, loaded from environment / .env file."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # asyncpg DSN; default targets local Homebrew PostgreSQL
    database_url: str = "postgresql+asyncpg://localhost:5432/agrihot"
    # comma-separated list; "*" for dev
    cors_origins: str = "*"
    # ingest rate limit per API key (slowapi format)
    ingest_rate_limit: str = "60/minute"
    # DeepSeek scoring for auto 精选; empty key disables scoring entirely
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # full-text backfill via Jina Reader for items pushed without content;
    # api key optional (anonymous tier is rate-limited but works)
    content_fetch_enabled: bool = True
    jina_api_key: str = ""
    jina_reader_base_url: str = "https://r.jina.ai"
    # total score (0-100) at or above which an item becomes 精选
    selection_threshold: int = 75
    # 精选每日名额：当天达阈值条目中按评分取前 N 篇
    daily_top_n: int = 5
    # 每日日报定时生成：每天按 local 时间 daily_generate_time 生成当天日报
    daily_generate_enabled: bool = True
    daily_generate_time: str = "20:00"
    # admin console password; empty disables the admin endpoints entirely
    admin_password: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
