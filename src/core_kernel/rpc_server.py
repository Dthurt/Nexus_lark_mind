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

    # ----- Knowledge base (SQLite owned by kernel) -----

    def _kb_store():
        from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore

        return KnowledgeStore(state["session_factory"])

    @app.get("/rpc/knowledge/docs")
    async def kb_list_docs(workspace_id: str = "", limit: int = 50):
        store = _kb_store()
        await store.ensure_schema()
        docs = await store.list_docs(workspace_id=workspace_id or "", limit=min(max(limit, 1), 200))
        return RpcEnvelope(ok=True, data={"docs": docs})

    @app.get("/rpc/knowledge/search")
    async def kb_search(query: str = "", workspace_id: str = "", limit: int = 8):
        from src.core_kernel.plugin_runtime.knowledge_store import citations_markdown

        store = _kb_store()
        await store.ensure_schema()
        q = (query or "").strip()
        if not q:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "query required"})
        hits = await store.search(q, workspace_id=workspace_id or "", limit=min(max(limit, 1), 40))
        return RpcEnvelope(
            ok=True,
            data={
                "query": q,
                "results": hits,
                "citations_md": citations_markdown(hits),
            },
        )

    @app.get("/rpc/knowledge/stats")
    async def kb_stats(workspace_id: str = ""):
        store = _kb_store()
        await store.ensure_schema()
        data = await store.stats(workspace_id=workspace_id or "")
        return RpcEnvelope(ok=True, data=data)

    @app.get("/rpc/knowledge/docs/{doc_id}")
    async def kb_get_doc(doc_id: str, include_chunks: bool = False):
        store = _kb_store()
        await store.ensure_schema()
        row = await store.get(doc_id, include_chunks=include_chunks)
        if not row:
            return RpcEnvelope(ok=False, error={"code": "NOT_FOUND", "message": f"doc not found: {doc_id}"})
        return RpcEnvelope(ok=True, data=row)

    @app.get("/rpc/knowledge/docs/{doc_id}/read")
    async def kb_read_doc(
        doc_id: str,
        offset: int = 0,
        limit: int = 4000,
        chunk_index: Optional[int] = None,
        neighbors: int = 1,
    ):
        from src.core_kernel.plugin_runtime.knowledge_store import format_citation

        store = _kb_store()
        await store.ensure_schema()
        row = await store.read(
            doc_id,
            offset=offset,
            limit=limit,
            chunk_index=chunk_index,
            neighbors=neighbors,
        )
        if not row:
            return RpcEnvelope(ok=False, error={"code": "NOT_FOUND", "message": f"doc not found: {doc_id}"})
        row["citation"] = format_citation(
            title=str(row.get("title") or ""),
            source=str(row.get("source") or ""),
            source_uri=str(row.get("source_uri") or ""),
            doc_id=doc_id,
            chunk_index=row.get("chunk_index") if chunk_index is not None else None,
        )
        return RpcEnvelope(ok=True, data=row)

    @app.post("/rpc/knowledge/docs")
    async def kb_add_doc(request: Request):
        from uuid import uuid4

        from src.core_kernel.plugin_runtime.knowledge_ingest import (
            default_tags_for_path,
            read_file_as_text,
        )
        from src.core_kernel.plugin_runtime.knowledge_store import content_hash
        from src.core_kernel.plugin_runtime.knowledge_sync import stable_doc_id_for_path

        store = _kb_store()
        await store.ensure_schema()
        body = await request.json()
        if not isinstance(body, dict):
            return RpcEnvelope(ok=False, error={"code": "BAD", "message": "JSON object required"})
        path_arg = str(body.get("path") or "").strip()
        title = str(body.get("title") or "").strip()
        content = str(body.get("content") or "")
        tags = str(body.get("tags") or "")
        source = str(body.get("source") or "")
        source_uri = str(body.get("source_uri") or "")
        workspace_id = str(body.get("workspace_id") or "")
        doc_id = str(body.get("doc_id") or "").strip()
        cwd = str(body.get("cwd") or "").strip()
        ingest_note = ""

        if path_arg:
            from pathlib import Path

            if not cwd:
                return RpcEnvelope(
                    ok=False,
                    error={"code": "NO_CWD", "message": "path requires cwd"},
                )
            root = Path(cwd).resolve()
            target = (root / path_arg).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                return RpcEnvelope(
                    ok=False,
                    error={"code": "PATH", "message": "path escapes workspace"},
                )
            if not target.is_file():
                return RpcEnvelope(
                    ok=False,
                    error={"code": "NOT_FOUND", "message": f"file not found: {path_arg}"},
                )
            try:
                content, ingest_note = read_file_as_text(target)
            except ValueError as exc:
                return RpcEnvelope(
                    ok=False,
                    error={"code": "INGEST", "message": str(exc)},
                )
            rel = target.relative_to(root).as_posix()
            if not title:
                title = target.stem
            source = f"file:{rel}"
            source_uri = rel
            if not doc_id:
                doc_id = stable_doc_id_for_path(rel)
            if not tags:
                tags = default_tags_for_path(target)

        if not content and not path_arg:
            return RpcEnvelope(
                ok=False,
                error={"code": "EMPTY", "message": "content or path required"},
            )
        if not title:
            title = doc_id or "untitled"
        if not doc_id:
            doc_id = f"kb_{uuid4().hex[:12]}"

        row = await store.upsert(
            doc_id=doc_id,
            title=title,
            content=content,
            tags=tags,
            source=source,
            source_uri=source_uri,
            workspace_id=workspace_id,
            content_hash_value=content_hash(content),
        )
        if ingest_note:
            row = {**row, "ingest_note": ingest_note}
        return RpcEnvelope(ok=True, data=row)

    @app.patch("/rpc/knowledge/docs/{doc_id}")
    async def kb_patch_doc(doc_id: str, request: Request):
        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        row = await store.patch(
            doc_id,
            title=body.get("title") if "title" in body else None,
            content=body.get("content") if "content" in body else None,
            tags=body.get("tags") if "tags" in body else None,
            source=body.get("source") if "source" in body else None,
            source_uri=body.get("source_uri") if "source_uri" in body else None,
        )
        if not row:
            return RpcEnvelope(ok=False, error={"code": "NOT_FOUND", "message": f"doc not found: {doc_id}"})
        return RpcEnvelope(ok=True, data=row)

    @app.delete("/rpc/knowledge/docs/{doc_id}")
    async def kb_delete_doc(doc_id: str):
        store = _kb_store()
        await store.ensure_schema()
        ok = await store.delete(doc_id)
        return RpcEnvelope(ok=True, data={"ok": ok, "doc_id": doc_id})

    @app.post("/rpc/knowledge/reindex")
    async def kb_reindex(request: Request):
        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        data = await store.reindex_embeddings(
            workspace_id=str(body.get("workspace_id") or ""),
            limit=int(body.get("limit") or 200),
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/rpc/knowledge/sync/docs")
    async def kb_sync_workspace_docs(request: Request):
        from src.core_kernel.plugin_runtime.knowledge_sync import sync_workspace_docs

        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        cwd = str(body.get("cwd") or "").strip()
        if not cwd:
            return RpcEnvelope(ok=False, error={"code": "NO_CWD", "message": "cwd required"})
        workspace_id = str(body.get("workspace_id") or "")
        max_files = int(body.get("max_files") or 400)
        data = await sync_workspace_docs(
            store,
            cwd,
            workspace_id=workspace_id,
            max_files=max(1, min(max_files, 2000)),
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/rpc/knowledge/sync/feishu")
    async def kb_sync_feishu(request: Request):
        from src.core_kernel.plugin_runtime.knowledge_sync import FeishuWikiConnector

        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        connector = FeishuWikiConnector(
            space_id=str(body.get("space_id") or ""),
            enabled=bool(body.get("enabled")),
        )
        data = await connector.sync_into(
            store, workspace_id=str(body.get("workspace_id") or "")
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/rpc/knowledge/sync/log")
    async def kb_sync_log(workspace_id: str = "", limit: int = 40):
        store = _kb_store()
        await store.ensure_schema()
        rows = await store.list_sync_log(
            workspace_id=workspace_id or "", limit=min(max(limit, 1), 100)
        )
        return RpcEnvelope(ok=True, data={"entries": rows})

    # ----- WeKnora bridge -----

    @app.get("/rpc/knowledge/weknora/health")
    async def weknora_health_rpc():
        from src.core_kernel.plugin_runtime.weknora_client import weknora_health

        return RpcEnvelope(ok=True, data=await weknora_health())

    @app.get("/rpc/knowledge/weknora/kbs")
    async def weknora_list_kbs_rpc(limit: int = 50):
        from src.core_kernel.plugin_runtime.weknora_client import weknora_list_knowledge_bases

        return RpcEnvelope(ok=True, data=await weknora_list_knowledge_bases(limit=limit))

    @app.post("/rpc/knowledge/weknora/search")
    async def weknora_search_rpc(request: Request):
        from src.core_kernel.plugin_runtime.weknora_client import weknora_search

        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        q = str(body.get("query") or "").strip()
        if not q:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "query required"})
        data = await weknora_search(
            q,
            limit=int(body.get("limit") or 5),
            kb_id=str(body.get("kb_id") or ""),
            kb_ids=body.get("kb_ids") if isinstance(body.get("kb_ids"), list) else None,
            workspace_id=str(body.get("workspace_id") or ""),
            session_kb_id=str(body.get("weknora_kb_id") or ""),
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/rpc/knowledge/weknora/push")
    async def weknora_push_rpc(request: Request):
        from src.core_kernel.plugin_runtime.weknora_client import weknora_push_document
        from src.core_kernel.plugin_runtime.knowledge_store import content_hash

        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        store = _kb_store()
        await store.ensure_schema()
        doc_id = str(body.get("doc_id") or "").strip()
        title = str(body.get("title") or "").strip()
        content = str(body.get("content") or "")
        kb_id = str(body.get("kb_id") or "").strip()
        workspace_id = str(body.get("workspace_id") or "")
        if doc_id:
            row = await store.get(doc_id)
            if not row:
                return RpcEnvelope(
                    ok=False, error={"code": "NOT_FOUND", "message": f"doc not found: {doc_id}"}
                )
            title = title or str(row.get("title") or doc_id)
            content = content or str(row.get("content") or "")
        if not content.strip():
            return RpcEnvelope(
                ok=False, error={"code": "EMPTY", "message": "content or doc_id required"}
            )
        data = await weknora_push_document(
            title=title or "untitled",
            content=content,
            kb_id=kb_id,
            workspace_id=workspace_id,
            metadata={"nlm_doc_id": doc_id} if doc_id else None,
        )
        if data.get("ok") and data.get("pushed") and doc_id:
            from src.core_kernel.plugin_runtime.knowledge_sync import record_weknora_push_identity

            await record_weknora_push_identity(
                store,
                kb_id=str(data.get("kb_id") or kb_id),
                local_doc_id=doc_id,
                remote_id=str(data.get("knowledge_id") or ""),
                digest=content_hash(content),
                workspace_id=workspace_id,
                message=f"pushed knowledge_id={data.get('knowledge_id') or ''}",
            )
        return RpcEnvelope(ok=bool(data.get("ok")), data=data)

    @app.get("/rpc/knowledge/weknora/knowledge")
    async def weknora_list_knowledge_rpc(
        kb_id: str = "",
        page: int = 1,
        page_size: int = 40,
    ):
        from src.core_kernel.plugin_runtime.weknora_client import weknora_list_knowledge

        data = await weknora_list_knowledge(
            kb_id,
            page=max(1, page),
            page_size=max(1, min(page_size, 100)),
        )
        return RpcEnvelope(ok=bool(data.get("ok") or data.get("skipped")), data=data)

    @app.post("/rpc/knowledge/weknora/sync")
    async def weknora_sync_rpc(request: Request):
        from src.core_kernel.plugin_runtime.knowledge_sync import sync_weknora_bidirectional

        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        doc_ids = body.get("doc_ids")
        data = await sync_weknora_bidirectional(
            store,
            workspace_id=str(body.get("workspace_id") or ""),
            kb_id=str(body.get("kb_id") or ""),
            direction=str(body.get("direction") or "both"),
            limit=int(body.get("limit") or 40),
            doc_ids=[str(x) for x in doc_ids] if isinstance(doc_ids, list) else None,
        )
        return RpcEnvelope(ok=bool(data.get("ok")), data=data)

    return app


def _build_messages(task: StandardTask, system_prompt: str) -> list[ChatMessage]:
    from src.core_kernel.agent_prompts import build_system_prompt

    prompt = build_system_prompt(base_prompt=system_prompt, metadata=task.metadata or {})
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
