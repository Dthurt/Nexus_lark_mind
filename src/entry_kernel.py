"""Core Kernel process entrypoint."""

import uvicorn

from src.common.config import get_settings
from src.common.logging import setup_logging, uvicorn_log_level
from src.core_kernel.rpc_server import create_kernel_app


def main() -> None:
    settings = get_settings()
    setup_logging("core-kernel", settings.log_level)
    app = create_kernel_app()
    uvicorn.run(
        app,
        host=settings.kernel_host,
        port=settings.kernel_port,
        log_level=uvicorn_log_level(settings.log_level),
        access_log=False,
    )


if __name__ == "__main__":
    main()
