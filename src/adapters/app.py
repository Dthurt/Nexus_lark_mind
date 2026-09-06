"""Adapters FastAPI application — Feishu webhook + Web SSE UI."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.adapters.feishu.adapter import FeishuAdapter
from src.adapters.feishu.events import parse_url_verification
from src.adapters.feishu.long_connection import FeishuLongConnection
from src.adapters.web.adapter import WebAdapter
from src.common.config import get_settings
from src.common.errors import NexusError
from src.common.rpc_client import RpcClient
from src.common.schemas import BusEvent, RpcEnvelope
from src.infrastructure.redis_client import create_broker

logger = logging.getLogger(__name__)


class WebChatRequest(BaseModel):
    content: str
    session_id: Optional[str] = None
    user_id: str = "web-user"
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    stream: bool = True


def create_adapters_app() -> FastAPI:
    settings = get_settings()
    state: Dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        redis_client = create_broker(settings)
        await redis_client.connect()
        orchestrator = RpcClient(settings.orchestrator_rpc_url)
        await orchestrator.start()

        feishu = FeishuAdapter(orchestrator, redis_client, settings)
        web = WebAdapter(orchestrator, redis_client, settings)

        stop_event = asyncio.Event()

        async def bus_handler(event: BusEvent) -> None:
            await feishu.on_bus_event(event)
            await web.on_bus_event(event)

        bus_task = asyncio.create_task(
            redis_client.subscribe_events(bus_handler, stop_event=stop_event),
            name="adapters-bus",
        )

        long_conn = FeishuLongConnection(on_event=feishu.handle_inbound, settings=settings)
        await long_conn.start()

        state.update(
            {
                "redis": redis_client,
                "orchestrator": orchestrator,
                "feishu": feishu,
                "web": web,
                "stop_event": stop_event,
                "bus_task": bus_task,
                "long_conn": long_conn,
            }
        )
        logger.info("Adapters service started")
        yield
        stop_event.set()
        await long_conn.stop()
        bus_task.cancel()
        await orchestrator.stop()
        await redis_client.close()

    app = FastAPI(title="Nexus-Lark-Mind Adapters", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NexusError)
    async def on_nexus(_: Request, exc: NexusError):
        return JSONResponse(
            status_code=exc.status_code,
            content=RpcEnvelope(ok=False, error=exc.to_dict()).model_dump(),
        )

    @app.get("/health")
    async def health():
        long_conn: FeishuLongConnection = state.get("long_conn")
        return {
            "status": "ok",
            "service": "adapters",
            "feishu_ws": bool(long_conn and long_conn.connected),
            "feishu_app_id": (settings.feishu_app_id[:8] + "…") if settings.feishu_app_id else None,
        }

    # ----- Feishu -----

    @app.post("/feishu/webhook")
    async def feishu_webhook(request: Request):
        feishu: FeishuAdapter = state["feishu"]
        body_bytes = await request.body()
        body_text = body_bytes.decode("utf-8")
        payload = await request.json()
        try:
            feishu.verify(payload, headers={k.lower(): v for k, v in request.headers.items()}, body=body_text)
        except NexusError:
            # Allow challenge without signature in some setups
            challenge = parse_url_verification(payload)
            if challenge is not None:
                return {"challenge": challenge}
            raise

        decoded = feishu.decode_payload(payload)
        challenge = parse_url_verification(decoded)
        if challenge is not None:
            return {"challenge": challenge}

        task = await feishu.handle_inbound(decoded)
        return {"ok": True, "task_id": task.task_id if task else None}

    # ----- Web chat -----

    @app.post("/api/chat")
    async def web_chat(body: WebChatRequest):
        web: WebAdapter = state["web"]
        task = await web.handle_inbound(body.model_dump())
        if task is None:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "content required"})
        return RpcEnvelope(
            ok=True,
            data={
                "task_id": task.task_id,
                "session_id": task.session_id,
                "status": "queued",
            },
        )

    @app.get("/api/chat/stream")
    async def web_sse(session_id: str):
        web: WebAdapter = state["web"]
        return StreamingResponse(
            web.sse_stream(session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    static_dir = Path(settings.web_static_dir)
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
