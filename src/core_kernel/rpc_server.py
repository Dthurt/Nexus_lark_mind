"""Core Kernel HTTP RPC server — sole owner of SQLite + model/plugin execution."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import orjson

from src.common.config import get_settings
from src.common.errors import NexusError
from src.common.schemas import (
    ChatMessage,
    ChatRole,
    ModelRequest,
    PluginInvokeRequest,
    RpcEnvelope,
    StandardTask,
)
from src.core_kernel.model_gateway.gateway import ModelGateway
from src.core_kernel.plugin_runtime.manager import PluginManager
from src.infrastructure.storage.database import close_database, get_session_factory, init_database
from src.infrastructure.storage.repositories import SessionRepository, TaskRepository

logger = logging.getLogger(__name__)


class ChatRunRequest(BaseModel):
    task: StandardTask
    system_prompt: str = (
        "You are Nexus-Lark-Mind, a helpful personal AI agent. "
        "Be concise, accurate, and tool-aware."
    )


class PluginActionRequest(BaseModel):
    plugin_id: str


class LoadPluginRequest(BaseModel):
    manifest: Dict[str, Any]


def create_kernel_app() -> FastAPI:
    settings = get_settings()
    state: Dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        session_factory = await init_database(settings)
        gateway = ModelGateway(settings, session_factory)
        plugins = PluginManager(settings, session_factory)
        await plugins.bootstrap()
        state["gateway"] = gateway
        state["plugins"] = plugins
        state["session_factory"] = session_factory
        logger.info("Core Kernel ready — providers=%s plugins=%s", gateway.registry.list_providers(), len(plugins.plugins))
        yield
        for plugin_id in list(plugins.plugins.keys()):
            await plugins.unload(plugin_id)
        await close_database()

    app = FastAPI(title="Nexus-Lark-Mind Core Kernel", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(NexusError)
    async def nexus_error_handler(_: Request, exc: NexusError):
        return JSONResponse(
            status_code=exc.status_code,
            content=RpcEnvelope(ok=False, error=exc.to_dict()).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled kernel error")
        return JSONResponse(
            status_code=500,
            content=RpcEnvelope(
                ok=False,
                error={"code": "INTERNAL", "message": str(exc)},
            ).model_dump(),
        )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "core-kernel"}

    @app.get("/rpc/providers")
    async def list_providers():
        gateway: ModelGateway = state["gateway"]
        return RpcEnvelope(ok=True, data=gateway.registry.list_providers())

    @app.get("/rpc/plugins")
    async def list_plugins():
        plugins: PluginManager = state["plugins"]
        return RpcEnvelope(ok=True, data=plugins.list_plugins())

    @app.get("/rpc/tools")
    async def list_tools():
        plugins: PluginManager = state["plugins"]
        return RpcEnvelope(ok=True, data=plugins.list_tools())

    @app.post("/rpc/plugins/load")
    async def load_plugin(body: LoadPluginRequest):
        from src.core_kernel.plugin_runtime.lifecycle import PluginManifest

        plugins: PluginManager = state["plugins"]
        manifest = PluginManifest.model_validate(body.manifest)
        loaded = await plugins.load(manifest)
        return RpcEnvelope(ok=True, data=loaded.model_dump())

    @app.post("/rpc/plugins/unload")
    async def unload_plugin(body: PluginActionRequest):
        plugins: PluginManager = state["plugins"]
        await plugins.unload(body.plugin_id)
        return RpcEnvelope(ok=True, data={"unloaded": body.plugin_id})

    @app.post("/rpc/plugins/enable")
    async def enable_plugin(body: PluginActionRequest):
        plugins: PluginManager = state["plugins"]
        await plugins.enable(body.plugin_id)
        return RpcEnvelope(ok=True, data={"enabled": body.plugin_id})

    @app.post("/rpc/plugins/disable")
    async def disable_plugin(body: PluginActionRequest):
        plugins: PluginManager = state["plugins"]
        await plugins.disable(body.plugin_id)
        return RpcEnvelope(ok=True, data={"disabled": body.plugin_id})

    @app.post("/rpc/plugins/invoke")
    async def invoke_plugin(body: PluginInvokeRequest):
        plugins: PluginManager = state["plugins"]
        result = await plugins.invoke(body)
        return RpcEnvelope(ok=True, data=result.model_dump())

    @app.post("/rpc/model/complete")
    async def model_complete(body: ModelRequest):
        gateway: ModelGateway = state["gateway"]
        result = await gateway.complete(body)
        return RpcEnvelope(ok=True, data=result.model_dump())

    @app.post("/rpc/model/stream")
    async def model_stream(body: ModelRequest):
        gateway: ModelGateway = state["gateway"]

        async def event_gen() -> AsyncIterator[bytes]:
            async for chunk in gateway.stream(body):
                yield b"data: " + orjson.dumps(chunk.model_dump(mode="json")) + b"\n\n"
            yield b"data: [DONE]\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.post("/rpc/chat/run")
    async def chat_run(body: ChatRunRequest):
        """Non-streaming agent turn with persistence."""
        gateway: ModelGateway = state["gateway"]
        task = body.task
        session_factory = state["session_factory"]

        messages = _build_messages(task, body.system_prompt)
        async with session_factory() as session:
            tasks = TaskRepository(session)
            sessions = SessionRepository(session)
            await sessions.get_or_create(task.session_id, channel=task.channel.value, user_id=task.user_id)
            await tasks.upsert_task(
                task_id=task.task_id,
                session_id=task.session_id,
                channel=task.channel.value,
                user_id=task.user_id,
                content=task.content,
                status="running",
                model_provider=task.model_provider,
                model_name=task.model_name,
                metadata=task.metadata,
            )
            await session.commit()

        req = ModelRequest(
            provider=task.model_provider,
            model=task.model_name,
            messages=messages,
            stream=False,
        )
        result = await gateway.complete(req, task_id=task.task_id)

        async with session_factory() as session:
            tasks = TaskRepository(session)
            sessions = SessionRepository(session)
            await sessions.append_messages(
                task.session_id,
                [
                    {"role": "user", "content": task.content},
                    {"role": "assistant", "content": result.content},
                ],
            )
            await tasks.upsert_task(
                task_id=task.task_id,
                session_id=task.session_id,
                channel=task.channel.value,
                user_id=task.user_id,
                content=task.content,
                status="completed",
                model_provider=result.provider,
                model_name=result.model,
                result_text=result.content,
                metadata=task.metadata,
            )
            await session.commit()

        return RpcEnvelope(
            ok=True,
            data={
                "task_id": task.task_id,
                "session_id": task.session_id,
                "content": result.content,
                "provider": result.provider,
                "model": result.model,
            },
        )

    @app.post("/rpc/chat/stream")
    async def chat_stream(body: ChatRunRequest):
        gateway: ModelGateway = state["gateway"]
        task = body.task
        session_factory = state["session_factory"]
        messages = _build_messages(task, body.system_prompt)

        async with session_factory() as session:
            tasks = TaskRepository(session)
            sessions = SessionRepository(session)
            await sessions.get_or_create(task.session_id, channel=task.channel.value, user_id=task.user_id)
            await tasks.upsert_task(
                task_id=task.task_id,
                session_id=task.session_id,
                channel=task.channel.value,
                user_id=task.user_id,
                content=task.content,
                status="streaming",
                model_provider=task.model_provider,
                model_name=task.model_name,
                metadata=task.metadata,
            )
            await session.commit()

        req = ModelRequest(
            provider=task.model_provider,
            model=task.model_name,
            messages=messages,
            stream=True,
        )

        async def event_gen() -> AsyncIterator[bytes]:
            collected = ""
            error: Optional[str] = None
            try:
                async for chunk in gateway.stream(req, task_id=task.task_id):
                    if chunk.notice:
                        payload = {
                            "task_id": task.task_id,
                            "session_id": task.session_id,
                            "delta": "",
                            "done": False,
                            "notice": chunk.notice,
                            "retry_attempt": chunk.retry_attempt,
                            "retry_wait_seconds": chunk.retry_wait_seconds,
                        }
                        yield b"data: " + orjson.dumps(payload) + b"\n\n"
                        continue
                    collected += chunk.content or ""
                    payload = {
                        "task_id": task.task_id,
                        "session_id": task.session_id,
                        "delta": chunk.content or "",
                        "done": False,
                        "finish_reason": chunk.finish_reason,
                    }
                    yield b"data: " + orjson.dumps(payload) + b"\n\n"
                done_payload = {
                    "task_id": task.task_id,
                    "session_id": task.session_id,
                    "delta": "",
                    "done": True,
                    "content": collected,
                }
                yield b"data: " + orjson.dumps(done_payload) + b"\n\n"
                yield b"data: [DONE]\n\n"
            except Exception as exc:
                from src.common.errors import RateLimitError
                from src.core_kernel.model_gateway.retry import format_rate_limit_exhausted, is_rate_limit_message

                if isinstance(exc, RateLimitError) or is_rate_limit_message(str(exc)):
                    error = format_rate_limit_exhausted(get_settings().model_max_retries)
                else:
                    error = str(exc)
                err_payload = {
                    "task_id": task.task_id,
                    "session_id": task.session_id,
                    "delta": "",
                    "done": True,
                    "error": error,
                }
                yield b"data: " + orjson.dumps(err_payload) + b"\n\n"
                yield b"data: [DONE]\n\n"
            finally:
                async with session_factory() as session:
                    tasks = TaskRepository(session)
                    sessions = SessionRepository(session)
                    if error is None:
                        await sessions.append_messages(
                            task.session_id,
                            [
                                {"role": "user", "content": task.content},
                                {"role": "assistant", "content": collected},
                            ],
                        )
                    await tasks.upsert_task(
                        task_id=task.task_id,
                        session_id=task.session_id,
                        channel=task.channel.value,
                        user_id=task.user_id,
                        content=task.content,
                        status="failed" if error else "completed",
                        result_text=collected if not error else None,
                        error=error,
                        metadata=task.metadata,
                    )
                    await session.commit()

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.get("/rpc/tasks/{task_id}")
    async def get_task(task_id: str):
        session_factory = state["session_factory"]
        async with session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.get(task_id)
            if row is None:
                return RpcEnvelope(ok=False, error={"code": "NOT_FOUND", "message": task_id})
            return RpcEnvelope(
                ok=True,
                data={
                    "task_id": row.task_id,
                    "session_id": row.session_id,
                    "status": row.status,
                    "content": row.content,
                    "result_text": row.result_text,
                    "error": row.error,
                },
            )

    return app


def _build_messages(task: StandardTask, system_prompt: str) -> list[ChatMessage]:
    messages: list[ChatMessage] = [ChatMessage(role=ChatRole.SYSTEM, content=system_prompt)]
    if task.messages:
        messages.extend(task.messages)
    else:
        messages.append(ChatMessage(role=ChatRole.USER, content=task.content))
    return messages
