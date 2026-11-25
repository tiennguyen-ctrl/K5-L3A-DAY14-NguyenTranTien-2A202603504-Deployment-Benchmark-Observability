"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Không có giá trị bí mật nào nằm trong code: AGENT_API_KEY mặc định là chuỗi rỗng
(khi đó /ask từ chối mọi request thay vì chấp nhận một key mặc định đoán được).
Danh sách đầy đủ các biến: xem .env.example.
"""
import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    # Bảo mật
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))

    # Redis (rate limit + cost guard dùng chung giữa các worker / instance)
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # Ngân sách LLM (USD)
    daily_budget_usd: float = field(default_factory=lambda: _env_float("DAILY_BUDGET_USD", 1.0))
    monthly_budget_usd: float = field(default_factory=lambda: _env_float("MONTHLY_BUDGET_USD", 10.0))


settings = Settings()
