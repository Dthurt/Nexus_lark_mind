"""Adapters process entrypoint."""

import uvicorn

from src.common.config import get_settings
from src.common.logging import setup_logging, uvicorn_log_level
from src.adapters.app import create_adapters_app


def main() -> None:
    settings = get_settings()
    setup_logging("adapters", settings.log_level)
    app = create_adapters_app()
    uvicorn.run(
        app,
        host=settings.adapters_host,
        port=settings.adapters_port,
        log_level=uvicorn_log_level(settings.log_level),
        access_log=False,
    )


if __name__ == "__main__":
    main()
