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
from src.infrastructure.storage.repositories import PluginCallRepository, SessionRepository, TaskRepository

logger = logging.getLogger(__name__)


from src.core_kernel.agent_prompts import IDENTITY


class ChatRunRequest(BaseModel):
    task: StandardTask
    system_prompt: str = IDENTITY


class PluginActionRequest(BaseModel):
    plugin_id: str


class PluginReloadRequest(BaseModel):
    plugin_id: Optional[str] = None


class LoadPluginRequest(BaseModel):
    manifest: Dict[str, Any]


def workspace_meta_from_task(task: StandardTask) -> Dict[str, Any]:
    """Session/task fields the agent runner + tools actually read.

    Must include routing keys (e.g. weknora_kb_id). A whitelist that drops
    them silently breaks Dock KB binding → weknora_search/push/sync.
    """
    md = task.metadata or {}
    return {
        "workspace_kind": md.get("workspace_kind") or "local",
        "ssh_host_id": md.get("ssh_host_id") or "",
        "workspace_id": md.get("workspace_id") or "",
        "workspace_title": md.get("workspace_title") or "",
        "session_id": task.session_id,
        "agent_mode": md.get("agent_mode") or "agent",
        "auto_accept": bool(md.get("auto_accept")),
        "plan_status": md.get("plan_status") or "idle",
        "multitask": bool(md.get("multitask", True)),
        "permission_preset": md.get("permission_preset") or "workspace-write",
        "plan_enforcement": md.get("plan_enforcement") or "hard",
        "experience_tier": md.get("experience_tier") or "balanced",
        "reasoning_effort": md.get("reasoning_effort") or "medium",
        "cwd": md.get("cwd") or "",
        "active_tools": md.get("active_tools"),
        "system_prompt_append": md.get("system_prompt_append") or "",
        "preset_name": md.get("preset_name") or "",
        "weknora_kb_id": str(md.get("weknora_kb_id") or "").strip(),
    }


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
    async def list_providers(configured_only: bool = True):
        gateway: ModelGateway = state["gateway"]
        return RpcEnvelope(ok=True, data=gateway.registry.catalog(configured_only=configured_only))

    @app.get("/rpc/settings/models")
    async def settings_models():
        gateway: ModelGateway = state["gateway"]
        return RpcEnvelope(ok=True, data=gateway.registry.settings_document())

    @app.post("/rpc/settings/models/providers")
    async def upsert_custom_provider(body: Dict[str, Any]):
        gateway: ModelGateway = state["gateway"]
        data = gateway.registry.upsert_custom(body)
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/rpc/settings/models/providers/{provider_id}")
    async def delete_custom_provider(provider_id: str):
        gateway: ModelGateway = state["gateway"]
        gateway.registry.delete_custom(provider_id)
        return RpcEnvelope(ok=True, data={"deleted": provider_id})

    @app.put("/rpc/settings/models/default")
    async def set_default_provider(body: Dict[str, Any]):
        gateway: ModelGateway = state["gateway"]
        provider_id = str(body.get("provider_id") or "").strip()
        data = gateway.registry.set_default_provider(provider_id)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/rpc/settings/models/reload")
    async def reload_providers():
        gateway: ModelGateway = state["gateway"]
        gateway.registry.reload()
        return RpcEnvelope(ok=True, data=gateway.registry.settings_document())

    @app.post("/rpc/settings/models/discover")
    async def discover_models(body: Dict[str, Any]):
        from src.core_kernel.model_gateway.discover import discover_openai_models

        gateway: ModelGateway = state["gateway"]
        base_url = str(body.get("base_url") or "").strip()
        api_key = str(body.get("api_key") or "")
        provider_id = str(body.get("provider_id") or "").strip().lower()
        if provider_id and not api_key:
            custom = gateway.registry.store.providers.get(provider_id)
            if custom:
                api_key = custom.api_key
                if not base_url:
                    base_url = custom.base_url
        data = await discover_openai_models(base_url=base_url, api_key=api_key)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/rpc/settings/models/test")
    async def test_models(body: Dict[str, Any]):
        from src.adapters.channels.probe import test_anthropic_messages, test_openai_compat

        gateway: ModelGateway = state["gateway"]
        base_url = str(body.get("base_url") or "").strip()
        api_key = str(body.get("api_key") or "")
        model = str(body.get("model") or "").strip()
        provider_id = str(body.get("provider_id") or "").strip().lower()
        api_kind = str(body.get("api") or "").strip().lower()
        if provider_id:
            custom = gateway.registry.store.providers.get(provider_id)
            if custom:
                if not api_key:
                    api_key = custom.api_key
                if not base_url:
                    base_url = custom.base_url
                if not model:
                    model = custom.default_model or (custom.models[0] if custom.models else "")
                # Custom providers must keep their own api kind (e.g. anthropic-messages).
                if not api_kind:
                    api_kind = str(getattr(custom, "api", "") or "").strip().lower()
            else:
                meta = gateway.registry._meta.get(provider_id) or {}
                if not base_url:
                    base_url = str(meta.get("base_url") or "")
                if not model:
                    models = meta.get("models") or []
                    model = str(meta.get("default_model") or (models[0] if models else ""))
                prov = gateway.registry._providers.get(provider_id)
                if prov is not None and not api_key:
                    api_key = getattr(prov, "api_key", "") or ""
                if not api_kind:
                    api_kind = str(meta.get("api") or "")
        if api_kind == "anthropic-messages" or provider_id == "anthropic":
            data = await test_anthropic_messages(base_url=base_url, api_key=api_key, model=model)
            return RpcEnvelope(ok=True, data=data)
        data = await test_openai_compat(base_url=base_url, api_key=api_key, model=model)
        return RpcEnvelope(ok=True, data=data)

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

    @app.post("/rpc/plugins/reload")
    async def reload_plugins(body: Optional[PluginReloadRequest] = None):
        plugins: PluginManager = state["plugins"]
        plugin_id = body.plugin_id if body else None
        data = await plugins.reload(plugin_id)
        return RpcEnvelope(ok=True, data=data)

    @app.get("/rpc/plugins/{plugin_id}/config")
    async def get_plugin_config(plugin_id: str):
        plugins: PluginManager = state["plugins"]
        return RpcEnvelope(ok=True, data=plugins.get_plugin_config(plugin_id))

    @app.put("/rpc/plugins/{plugin_id}/config")
    async def put_plugin_config(plugin_id: str, body: Dict[str, Any]):
        plugins: PluginManager = state["plugins"]
        values = body.get("values") if isinstance(body.get("values"), dict) else body
        data = plugins.set_plugin_config(plugin_id, values or {})
        return RpcEnvelope(ok=True, data=data)

    @app.get("/rpc/plugin-calls")
    async def list_plugin_calls(session_id: Optional[str] = None, limit: int = 40):
        session_factory = state["session_factory"]
        async with session_factory() as session:
            repo = PluginCallRepository(session)
            if session_id:
                rows = await repo.list_by_session(session_id, limit=min(limit, 100))
            else:
                rows = await repo.list_recent(limit=min(limit, 100))
            return RpcEnvelope(ok=True, data=[PluginCallRepository.to_dict(r) for r in rows])

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

        messages = await _build_messages_compacted(task, body.system_prompt, gateway=gateway)
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
        plugins: PluginManager = state["plugins"]
        task = body.task
        session_factory = state["session_factory"]
        messages = await _build_messages_compacted(task, body.system_prompt, gateway=gateway)

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

        async def event_gen() -> AsyncIterator[bytes]:
            from src.core_kernel.agent_runner import run_agent_stream

            collected = ""
            reasoning_collected = ""
            error: Optional[str] = None
            saw_done = False
            try:
                async for chunk in run_agent_stream(
                    gateway=gateway,
                    plugins=plugins,
                    messages=messages,
                    provider=task.model_provider,
                    model=task.model_name,
                    tools_enabled=bool(task.tools_enabled),
                    task_id=task.task_id,
                    workspace_cwd=(task.metadata or {}).get("cwd") or None,
                    workspace_meta=workspace_meta_from_task(task),
                    allow_subagents=bool((task.metadata or {}).get("multitask", True)),
                    parent_session_id=task.session_id,
                ):
                    if chunk.get("content"):
                        collected = chunk["content"]
                    elif chunk.get("delta"):
                        collected += chunk["delta"]
                    reasoning_delta = chunk.get("reasoning_delta") or ""
                    if reasoning_delta:
                        reasoning_collected += reasoning_delta
                    if chunk.get("done") and chunk.get("error"):
                        error = chunk["error"]
                    if chunk.get("done"):
                        saw_done = True
                    payload = {
                        "task_id": task.task_id,
                        "session_id": task.session_id,
                        **chunk,
                    }
                    yield b"data: " + orjson.dumps(payload) + b"\n\n"
                if not saw_done:
                    yield b"data: " + orjson.dumps(
                        {
                            "task_id": task.task_id,
                            "session_id": task.session_id,
                            "delta": "",
                            "done": True,
                            "content": collected,
                        }
                    ) + b"\n\n"
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
                        assistant_msg: dict = {"role": "assistant", "content": collected}
                        if reasoning_collected:
                            assistant_msg["metadata"] = {"reasoning": reasoning_collected}
                        await sessions.append_messages(
                            task.session_id,
                            [
                                {"role": "user", "content": task.content},
                                assistant_msg,
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

    @app.post("/rpc/gates/resolve")
    async def gates_resolve(request: Request):
        from src.core_kernel import user_gate

        body = await request.json()
        call_id = str(body.get("call_id") or "").strip()
        if not call_id:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "call_id required"})
        payload = body.get("payload")
        if not isinstance(payload, dict):
            payload = {k: v for k, v in body.items() if k != "call_id"}
        ok = await user_gate.resolve_gate(call_id, payload)
        return RpcEnvelope(ok=True, data={"resolved": ok, "call_id": call_id})

    @app.post("/rpc/gates/deny-session")
    async def gates_deny_session(request: Request):
        from src.core_kernel import user_gate

        body = await request.json()
        session_id = str(body.get("session_id") or "").strip()
        reason = str(body.get("reason") or "cancelled")
        n = await user_gate.deny_session_gates(session_id, reason=reason)
        return RpcEnvelope(ok=True, data={"denied": n, "session_id": session_id})

    from src.core_kernel.knowledge_rpc import register_knowledge_rpc

    register_knowledge_rpc(app, state)

    return app

def _user_text_from_task(task: StandardTask) -> str:
    text = str(getattr(task, "content", "") or "").strip()
    if text:
        return text
    for msg in reversed(list(task.messages or [])):
        role = getattr(msg, "role", None)
        role_s = role.value if hasattr(role, "value") else str(role or "")
        if role_s == "user":
            return str(getattr(msg, "content", "") or "")
    return ""


def _build_messages(task: StandardTask, system_prompt: str) -> list[ChatMessage]:
    from src.core_kernel.agent_prompts import build_system_prompt

    meta = dict(task.metadata or {})
    if not str(meta.get("user_text") or "").strip():
        meta["user_text"] = _user_text_from_task(task)
    prompt = build_system_prompt(base_prompt=system_prompt, metadata=meta)
    messages: list[ChatMessage] = [ChatMessage(role=ChatRole.SYSTEM, content=prompt)]
    if task.messages:
        messages.extend(task.messages)
    else:
        messages.append(ChatMessage(role=ChatRole.USER, content=task.content))
    return messages


async def _build_messages_compacted(
    task: StandardTask,
    system_prompt: str,
    *,
    gateway: Optional[ModelGateway] = None,
) -> list[ChatMessage]:
    from src.core_kernel.compaction_summarizer import compact_messages_async

    messages = _build_messages(task, system_prompt)
    compacted, _info = await compact_messages_async(
        messages,
        model_name=task.model_name,
        gateway=gateway,
        provider=task.model_provider,
        task_id=task.task_id,
        use_llm=True,
    )
    return compacted
