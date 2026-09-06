"""Local all-in-one entry: kernel + orchestrator + adapters (no Docker / Redis)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import uvicorn

# Ensure project root is on sys.path when launched as script
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

from src.adapters.app import create_adapters_app
from src.agent_orchestrator.app import create_orchestrator_app
from src.common.config import get_settings
from src.common.logging import setup_logging
from src.core_kernel.rpc_server import create_kernel_app

logger = logging.getLogger("local")


async def _serve(app, host: str, port: int, name: str) -> None:
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=get_settings().log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("Starting %s on http://%s:%s", name, host, port)
    await server.serve()


async def run() -> None:
    settings = get_settings()
    setup_logging("local", settings.log_level)

    # Local defaults if still pointing at compose hostnames
    if "core-kernel" in settings.kernel_rpc_url or settings.redis_url.startswith("redis://redis"):
        logger.warning(
            "Detected Docker-style URLs. Prefer REDIS_URL=memory://local and "
            "KERNEL_RPC_URL=http://127.0.0.1:8001 for script mode."
        )

    kernel_app = create_kernel_app()
    orch_app = create_orchestrator_app()
    adapters_app = create_adapters_app()

    await asyncio.gather(
        _serve(kernel_app, settings.kernel_host, settings.kernel_port, "core-kernel"),
        _serve(orch_app, settings.orchestrator_host, settings.orchestrator_port, "orchestrator"),
        _serve(adapters_app, settings.adapters_host, settings.adapters_port, "adapters"),
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
