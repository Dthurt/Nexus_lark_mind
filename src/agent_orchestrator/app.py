"""Orchestrator FastAPI app — enqueue API + background dispatcher."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.agent_orchestrator.event_bus_consumer import EventBusConsumer
from src.agent_orchestrator.queue_service import QueueService
from src.agent_orchestrator.schemas import EnqueueRequest, EnqueueResponse
from src.agent_orchestrator.session_context import SessionContext
from src.agent_orchestrator.task_dispatcher import TaskDispatcher
from src.common.config import get_settings
from src.common.errors import NexusError
from src.common.rpc_client import RpcClient
from src.common.schemas import RpcEnvelope
from src.infrastructure.redis_client import create_broker

logger = logging.getLogger(__name__)


def create_orchestrator_app() -> FastAPI:
    settings = get_settings()
    state: Dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        redis_client = create_broker(settings)
        await redis_client.connect()
        kernel = RpcClient(settings.kernel_rpc_url)
        await kernel.start()

        queue = QueueService(redis_client)
        sessions = SessionContext(redis_client)
        dispatcher = TaskDispatcher(queue, sessions, kernel, redis_client)
        bus = EventBusConsumer(redis_client)

        state.update(
            {
                "redis": redis_client,
                "kernel": kernel,
                "queue": queue,
                "sessions": sessions,
                "dispatcher": dispatcher,
                "bus": bus,
            }
        )

        dispatch_task = asyncio.create_task(dispatcher.start_loop(), name="dispatcher")
        bus_task = asyncio.create_task(bus.start(), name="bus-consumer")
        logger.info("Orchestrator started")
        yield
        dispatcher.stop()
        bus.stop()
        dispatch_task.cancel()
        bus_task.cancel()
        await kernel.stop()
        await redis_client.close()

    app = FastAPI(title="Nexus-Lark-Mind Orchestrator", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(NexusError)
    async def on_nexus(_: Request, exc: NexusError):
        return JSONResponse(
            status_code=exc.status_code,
            content=RpcEnvelope(ok=False, error=exc.to_dict()).model_dump(),
        )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "orchestrator"}

    @app.post("/rpc/tasks/enqueue")
    async def enqueue(body: EnqueueRequest):
        queue: QueueService = state["queue"]
        task = await queue.enqueue(body.task)
        return RpcEnvelope(
            ok=True,
            data=EnqueueResponse(task_id=task.task_id, session_id=task.session_id).model_dump(),
        )

    @app.get("/rpc/sessions/{session_id}")
    async def get_session(session_id: str):
        sessions: SessionContext = state["sessions"]
        data = await sessions.redis.get_session(session_id)
        return RpcEnvelope(ok=True, data=data)

    return app
