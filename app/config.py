from __future__ import annotations

import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    request_timeout: float = float(os.getenv("MYNTRA_REQUEST_TIMEOUT", "20"))
    retry_count: int = int(os.getenv("MYNTRA_RETRY_COUNT", "2"))
    concurrency: int = int(os.getenv("MYNTRA_CONCURRENCY", "4"))
    request_delay: float = float(os.getenv("MYNTRA_REQUEST_DELAY", "0.1"))
    jitter: float = float(os.getenv("MYNTRA_JITTER", "0.2"))
    batch_timeout: float = float(os.getenv("MYNTRA_BATCH_TIMEOUT", "90"))
    headless: bool = _bool_env("MYNTRA_HEADLESS", True)
    log_level: str = os.getenv("MYNTRA_LOG_LEVEL", "INFO")
    user_agent: str = os.getenv(
        "MYNTRA_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )
    include_delivery: bool = _bool_env("MYNTRA_INCLUDE_DELIVERY", False)


settings = Settings()
