"""Application settings, loaded from environment / .env file."""
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # asyncpg DSN; default targets local Homebrew PostgreSQL
    database_url: str = "postgresql+asyncpg://localhost:5432/agrihot"
    # comma-separated list; "*" for dev
    cors_origins: str = "*"
    # ingest rate limit per API key (slowapi format)
    ingest_rate_limit: str = "60/minute"
    agent_rate_limit: str = "60/minute"
    # Agent semantic retrieval: independent of the editorial scoring model.
    embedding_api_key: str = ""
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 1024
    embedding_timeout: float = 15
    embedding_min_interval: float = Field(default=1, ge=0, allow_inf_nan=False)
    embedding_rate_limit_cooldown: float = Field(default=60, ge=1, le=3600)
    search_index_enabled: bool = True
    # DeepSeek scoring for auto 精选; empty key disables scoring entirely
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # Full-text strategies prefer direct HTML / publisher XML / PDF; Jina is a fallback.
    # The Reader API key is optional (anonymous access may be rate-limited).
    content_fetch_enabled: bool = True
    content_fetch_timeout: float = Field(default=60, ge=5, le=180, allow_inf_nan=False)
    content_max_chars: int = Field(default=100000, ge=200, le=1000000)
    jina_api_key: str = ""
    jina_reader_base_url: str = "https://r.jina.ai"
    # total score (0-100) at or above which an item becomes 精选
    selection_threshold: int = 75
    # 精选每日名额：当天达阈值条目中按评分取前 N 篇
    daily_top_n: int = 5
    # 每日日报定时生成：每天按 daily_timezone 时区的 daily_generate_time 生成当天日报
    daily_generate_enabled: bool = True
    daily_generate_time: str = "20:00"
    # 日报归集使用的业务时区：「收录日期」按此时区的日历日切分，
    # 与容器/服务器系统时区解耦（生产容器默认 UTC，不能用它切日界）
    daily_timezone: str = "Asia/Shanghai"
    # admin console password; empty disables the admin endpoints entirely
    admin_password: str = ""
    # OpenAlex 文献雷达：免费学术元数据，不爬期刊官网 / WoS
    openalex_api_key: str = ""
    openalex_mailto: str = "ijedyu@gmail.com"
    literature_fetch_enabled: bool = True
    literature_fetch_time: str = "07:30"
    # 增量窗口重叠天数（OpenAlex 索引延迟）
    literature_lookback_days: int = 2
    # 从未跑过时的回看天数；避免首次把几千篇灌进公共站
    literature_bootstrap_days: int = 7
    # 单次运行最多新建条目（控制评分 / 卡片 token）
    literature_max_new_per_run: int = 80
    # 空则使用包内 app/watchlist.yaml
    watchlist_path: str = ""
    # public site origin for canonical / sitemap / Open Graph
    site_url: str = "https://agrihot.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
