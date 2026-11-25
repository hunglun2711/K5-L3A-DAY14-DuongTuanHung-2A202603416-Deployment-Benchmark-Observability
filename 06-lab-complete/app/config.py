"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_budget() -> float:
    raw = os.getenv("DAILY_BUDGET_USD") or os.getenv("MONTHLY_BUDGET_USD")
    if raw is None or raw == "":
        return 1.0
    return float(raw)


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT") or "development")
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL") or "redis://localhost:6379/0")
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=_env_budget)
    log_level: str = field(default_factory=lambda: (os.getenv("LOG_LEVEL") or "INFO").upper())


settings = Settings()
