"""Structured logging helpers."""

import logging
import sys
from typing import Optional

from src.common.config import get_settings


def setup_logging(service_name: str, level: Optional[str] = None) -> logging.Logger:
    settings = get_settings()
    log_level = (level or settings.log_level).upper()

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt=f"%(asctime)s | {service_name} | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(service_name)
