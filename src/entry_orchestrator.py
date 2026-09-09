"""Orchestrator process entrypoint."""

import uvicorn

from src.agent_orchestrator.app import create_orchestrator_app
from src.common.config import get_settings
from src.common.logging import setup_logging, uvicorn_log_level


def main() -> None:
    settings = get_settings()
    setup_logging("orchestrator", settings.log_level)
    app = create_orchestrator_app()
    uvicorn.run(
        app,
        host=settings.orchestrator_host,
        port=settings.orchestrator_port,
        log_level=uvicorn_log_level(settings.log_level),
        access_log=False,
    )


if __name__ == "__main__":
    main()
