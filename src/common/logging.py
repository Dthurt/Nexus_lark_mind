"""Structured logging helpers."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from src.common.config import get_settings

# Always quiet — these flood the console under DEBUG / SQL echo.
_NOISY_LOGGERS = (
    "uvicorn.access",
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "hpack",
    "urllib3",
    "asyncio",
    "aiosqlite",
    "sqlalchemy",
    "sqlalchemy.engine",
    "sqlalchemy.engine.Engine",
    "sqlalchemy.pool",
    "websockets",
    "websockets.client",
    "websockets.server",
    "openai",
    "multipart",
    "watchfiles",
)


def setup_logging(service_name: str, level: Optional[str] = None) -> logging.Logger:
    settings = get_settings()
    log_level = (level or settings.log_level).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = "INFO"

    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt=f"%(asctime)s | {service_name} | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    # DEBUG only for our code; keep root/third-party calmer.
    if log_level == "DEBUG":
        root.setLevel(logging.INFO)
        logging.getLogger("src").setLevel(logging.DEBUG)
        logging.getLogger("local").setLevel(logging.DEBUG)
    else:
        root.setLevel(log_level)
        logging.getLogger("src").setLevel(log_level)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Lark SDK: keep connection status, drop frame noise
    logging.getLogger("lark").setLevel(logging.INFO)
    logging.getLogger("lark_oapi").setLevel(logging.WARNING)

    return logging.getLogger(service_name)


def uvicorn_log_level(level: Optional[str] = None) -> str:
    """Uvicorn itself should stay at info unless explicitly ERROR+."""
    raw = (level or get_settings().log_level).lower()
    if raw in {"warning", "error", "critical"}:
        return raw
    return "info"
