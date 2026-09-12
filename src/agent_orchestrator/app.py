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

    @app.post("/rpc/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str, request: Request):
        dispatcher: TaskDispatcher = state["dispatcher"]
        body: Dict[str, Any] = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        keep_inbox = True if body.get("keep_inbox") is None else bool(body.get("keep_inbox"))
        active = dispatcher.request_cancel(task_id)
        return RpcEnvelope(
            ok=True,
            data={
                "task_id": task_id,
                "cancel_requested": True,
                "was_active": active,
                "keep_inbox": keep_inbox,
            },
        )

    @app.post("/rpc/sessions/{session_id}/cancel")
    async def cancel_session(session_id: str, request: Request):
        dispatcher: TaskDispatcher = state["dispatcher"]
        sessions: SessionContext = state["sessions"]
        body: Dict[str, Any] = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        keep_inbox = True if body.get("keep_inbox") is None else bool(body.get("keep_inbox"))
        task_id = dispatcher.cancel_session(session_id)
        cleared: list = []
        if not keep_inbox:
            try:
                cleared = await sessions.clear_inbox_items(session_id)
            except Exception:
                logger.exception("clear inbox on cancel failed for %s", session_id)
        kernel: RpcClient = state["kernel"]
        try:
            await kernel.call("POST", "/rpc/gates/deny-session", json={"session_id": session_id})
        except Exception:
            logger.exception("deny-session gates failed for %s", session_id)
        return RpcEnvelope(
            ok=True,
            data={
                "session_id": session_id,
                "task_id": task_id,
                "cancel_requested": bool(task_id),
                "keep_inbox": keep_inbox,
                "cleared_inbox": cleared,
            },
        )

    @app.get("/rpc/sessions/{session_id}/inbox")
    async def get_inbox(session_id: str):
        sessions: SessionContext = state["sessions"]
        items = await sessions.get_inbox(session_id)
        return RpcEnvelope(ok=True, data={"session_id": session_id, "items": items})

    @app.post("/rpc/sessions/{session_id}/inbox")
    async def post_inbox(session_id: str, request: Request):
        from src.common.errors import NotFoundError, ValidationAppError
        from src.common.schemas import BusEvent, ChannelType, EventType

        body = await request.json()
        sessions: SessionContext = state["sessions"]
        redis_client = state["redis"]
        await sessions.ensure(
            session_id,
            user_id=str(body.get("user_id") or "web-user"),
            channel=str(body.get("channel") or "web"),
        )
        kind = str(body.get("kind") or "queue").strip().lower()
        content = str(body.get("content") or "")
        try:
            item = await sessions.push_inbox_item(
                session_id,
                kind=kind,
                content=content,
                source=str(body.get("source") or "user"),
            )
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        except KeyError as exc:
            raise NotFoundError(session_id) from exc
        items = await sessions.get_inbox(session_id)
        await redis_client.publish_event(
            BusEvent(
                event_type=EventType.TASK_INBOX,
                task_id="",
                session_id=session_id,
                channel=ChannelType.WEB,
                payload={"action": "pushed", "item": item, "items": items},
            )
        )
        return RpcEnvelope(ok=True, data={"item": item, "items": items})

    @app.delete("/rpc/sessions/{session_id}/inbox/{item_id}")
    async def delete_inbox_item(session_id: str, item_id: str):
        from src.common.errors import NotFoundError
        from src.common.schemas import BusEvent, ChannelType, EventType

        sessions: SessionContext = state["sessions"]
        redis_client = state["redis"]
        try:
            removed = await sessions.remove_inbox_item(session_id, item_id)
        except KeyError as exc:
            raise NotFoundError(session_id) from exc
        items = await sessions.get_inbox(session_id)
        await redis_client.publish_event(
            BusEvent(
                event_type=EventType.TASK_INBOX,
                task_id="",
                session_id=session_id,
                channel=ChannelType.WEB,
                payload={"action": "removed", "item": removed, "items": items},
            )
        )
        return RpcEnvelope(ok=True, data={"removed": removed, "items": items})

    @app.post("/rpc/sessions/{session_id}/files")
    async def append_session_file(session_id: str, request: Request):
        body = await request.json()
        sessions: SessionContext = state["sessions"]
        from src.common.schemas import ChatMessage, ChatRole

        name = str(body.get("name") or body.get("filename") or "file").strip() or "file"
        content = body.get("content")
        content_s = "" if content is None else str(content)
        path = str(body.get("path") or "").strip()
        mime = str(body.get("mime") or body.get("mime_type") or "text/plain").strip()
        url = str(body.get("url") or "").strip()
        size = body.get("size")
        preview = content_s[:400] if content_s else f"[file] {name}"
        msg = ChatMessage(
            role=ChatRole.ASSISTANT,
            content=preview,
            metadata={
                "kind": "file",
                "file": {
                    "name": name,
                    "path": path,
                    "content": content_s,
                    "mime": mime,
                    "url": url,
                    "size": size,
                },
            },
        )
        await sessions.ensure(session_id, user_id="web-user", channel="web")
        await sessions.append(session_id, msg)
        file_meta = (msg.metadata or {}).get("file")
        return RpcEnvelope(ok=True, data={"session_id": session_id, "file": file_meta})

    @app.get("/rpc/sessions/{session_id}")
    async def get_session(session_id: str):
        sessions: SessionContext = state["sessions"]
        data = await sessions.redis.get_session(session_id)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/rpc/sessions")
    async def create_or_ensure_session(request: Request):
        body = await request.json()
        sessions: SessionContext = state["sessions"]
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            from src.common.schemas import new_id

            session_id = new_id("web_")
        data = await sessions.ensure(
            session_id,
            user_id=str(body.get("user_id") or "web-user"),
            channel=str(body.get("channel") or "web"),
            cwd=str(body.get("cwd") or "").strip() or None,
            workspace_id=str(body.get("workspace_id") or "").strip() or None,
            workspace_title=str(body.get("workspace_title") or "").strip() or None,
            workspace_kind=str(body.get("workspace_kind") or "").strip() or None,
            ssh_host_id=str(body.get("ssh_host_id") or "").strip() or None,
        )
        return RpcEnvelope(ok=True, data=data)

    @app.patch("/rpc/sessions/{session_id}/workspace")
    async def bind_session_workspace(session_id: str, request: Request):
        body = await request.json()
        sessions: SessionContext = state["sessions"]
        cwd = str(body.get("cwd") or "").strip()
        if not cwd:
            from src.common.errors import ValidationAppError

            raise ValidationAppError("cwd required")
        # ensure session exists first
        await sessions.ensure(
            session_id,
            user_id=str(body.get("user_id") or "web-user"),
            channel=str(body.get("channel") or "web"),
        )
        try:
            data = await sessions.bind_workspace(
                session_id,
                cwd=cwd,
                workspace_id=str(body.get("workspace_id") or ""),
                workspace_title=str(body.get("workspace_title") or ""),
                workspace_kind=str(body.get("workspace_kind") or "local"),
                ssh_host_id=str(body.get("ssh_host_id") or ""),
                force=bool(body.get("force")),
            )
        except ValueError as exc:
            from src.common.errors import ValidationAppError

            raise ValidationAppError(str(exc)) from exc
        except KeyError as exc:
            from src.common.errors import NotFoundError

            raise NotFoundError(session_id) from exc
        return RpcEnvelope(ok=True, data=data)

    @app.patch("/rpc/sessions/{session_id}/interaction")
    async def patch_session_interaction(session_id: str, request: Request):
        body = await request.json()
        sessions: SessionContext = state["sessions"]
        await sessions.ensure(
            session_id,
            user_id=str(body.get("user_id") or "web-user"),
            channel=str(body.get("channel") or "web"),
        )
        try:
            data = await sessions.set_interaction(
                session_id,
                agent_mode=body.get("agent_mode"),
                auto_accept=body.get("auto_accept"),
                plan_status=body.get("plan_status"),
                permission_preset=body.get("permission_preset"),
                plan_enforcement=body.get("plan_enforcement"),
                experience_tier=body.get("experience_tier"),
                reasoning_effort=body.get("reasoning_effort"),
            )
        except ValueError as exc:
            from src.common.errors import ValidationAppError

            raise ValidationAppError(str(exc)) from exc
        except KeyError as exc:
            from src.common.errors import NotFoundError

            raise NotFoundError(session_id) from exc
        return RpcEnvelope(ok=True, data=data)

    @app.get("/rpc/sessions")
    async def list_sessions():
        sessions: SessionContext = state["sessions"]
        data = await sessions.list_summaries()
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/rpc/sessions/{session_id}")
    async def delete_session(session_id: str):
        sessions: SessionContext = state["sessions"]
        await sessions.clear(session_id)
        return RpcEnvelope(ok=True, data={"deleted": session_id})

    return app
