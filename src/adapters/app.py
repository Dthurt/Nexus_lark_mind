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
from src.adapters.channels import get_channel_store, reload_channel_store, resolve_feishu
from src.adapters.channels.probe import test_feishu_app
from src.adapters.workspaces import browse_directory, get_workspace_store
from src.adapters.workspaces.ssh_fs import browse_remote, ensure_remote_dir, test_ssh_host
from src.adapters.workspaces.ssh_store import get_ssh_host_store
from src.common.config import get_settings
from src.common.errors import NexusError, NotFoundError, ValidationAppError
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
    tools_enabled: bool = True
    workspace_id: Optional[str] = None
    cwd: Optional[str] = None
    workspace_kind: Optional[str] = None
    ssh_host_id: Optional[str] = None
    agent_mode: Optional[str] = None
    auto_accept: Optional[bool] = None


class GateResolveRequest(BaseModel):
    call_id: str
    action: str = "allow"
    reason: Optional[str] = None
    answers: Optional[Any] = None
    auto_accept: Optional[bool] = None


class InteractionPatchRequest(BaseModel):
    agent_mode: Optional[str] = None
    auto_accept: Optional[bool] = None
    plan_status: Optional[str] = None


class AcceptPlanRequest(BaseModel):
    content: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    tools_enabled: bool = True
    workspace_id: Optional[str] = None
    cwd: Optional[str] = None
    workspace_kind: Optional[str] = None
    ssh_host_id: Optional[str] = None
    auto_accept: Optional[bool] = None


class MermaidRepairRequest(BaseModel):
    source: str
    error: str = ""
    model_provider: Optional[str] = None
    model_name: Optional[str] = None


_MERMAID_REPAIR_SYSTEM = (
    "You repair invalid Mermaid diagram source. "
    "Return ONLY a single fenced mermaid code block with corrected syntax. "
    "No prose, no explanation. Preserve the author's intent and diagram type. "
    "Use ASCII punctuation. Prefer flowchart/sequenceDiagram/classDiagram/erDiagram/"
    "stateDiagram-v2/gantt/timeline/mindmap/pie when unsure."
)


def create_adapters_app() -> FastAPI:
    settings = get_settings()
    state: Dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        redis_client = create_broker(settings)
        await redis_client.connect()
        orchestrator = RpcClient(settings.orchestrator_rpc_url)
        await orchestrator.start()
        kernel = RpcClient(settings.kernel_rpc_url)
        await kernel.start()

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

        async def restart_feishu_channel() -> Dict[str, Any]:
            old = state.get("long_conn")
            if old is not None:
                await old.stop()
            reload_channel_store()
            feishu_ad: FeishuAdapter = state["feishu"]
            feishu_ad.client.refresh_credentials()
            creds = resolve_feishu(settings)
            new_conn = FeishuLongConnection(
                on_event=feishu_ad.handle_inbound,
                settings=settings,
                app_id=creds.app_id,
                app_secret=creds.app_secret,
                use_long_connection=creds.use_long_connection and creds.enabled,
            )
            await new_conn.start()
            state["long_conn"] = new_conn
            return {
                "source": creds.source,
                "enabled": creds.enabled,
                "configured": creds.configured,
                "use_long_connection": creds.use_long_connection and creds.enabled,
                "app_id": creds.app_id,
                "long_connection_started": bool(creds.configured and creds.use_long_connection),
            }

        state.update(
            {
                "redis": redis_client,
                "orchestrator": orchestrator,
                "kernel": kernel,
                "feishu": feishu,
                "web": web,
                "stop_event": stop_event,
                "bus_task": bus_task,
                "long_conn": long_conn,
                "restart_feishu_channel": restart_feishu_channel,
            }
        )
        logger.info("Adapters service started")
        yield
        stop_event.set()
        await long_conn.stop()
        bus_task.cancel()
        await kernel.stop()
        await orchestrator.stop()
        await redis_client.close()

    app = FastAPI(title="Nexus Lark Mind Adapters", version="1.0.0", lifespan=lifespan)
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

    @app.post("/api/mermaid/repair")
    async def mermaid_repair(body: MermaidRepairRequest):
        """Quiet one-shot model call to regenerate invalid Mermaid in place (not a chat turn)."""
        source = (body.source or "").strip()
        if not source:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "source required"})
        kernel: RpcClient = state["kernel"]
        user = (
            "Fix this Mermaid diagram so it parses in Mermaid v11.\n"
            "Common fixes: use `-.->` not `-. -->`; use `-->` not `->` or `→`; "
            "edge labels as `A -->|label| B` or `A -.->|label| B`; "
            "ASCII punctuation only; keep diagram type on first line.\n\n"
            f"Parse error:\n{body.error or '(unknown)'}\n\n"
            f"Broken source:\n```mermaid\n{source}\n```\n"
        )
        try:
            data = await kernel.call(
                "POST",
                "/rpc/model/complete",
                json={
                    "provider": body.model_provider,
                    "model": body.model_name,
                    "stream": False,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": _MERMAID_REPAIR_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                },
            )
        except Exception as exc:
            logger.exception("mermaid repair RPC failed")
            return RpcEnvelope(
                ok=False,
                error={"code": "REPAIR_RPC", "message": str(exc)},
            )
        content = ""
        if isinstance(data, dict):
            content = str(data.get("content") or "")
        if not content.strip():
            return RpcEnvelope(
                ok=False,
                error={"code": "EMPTY_FIX", "message": "model returned empty repair"},
            )
        return RpcEnvelope(ok=True, data={"source": content, "raw": data})

    @app.post("/api/chat/{task_id}/cancel")
    async def cancel_chat(task_id: str):
        orch: RpcClient = state["orchestrator"]
        data = await orch.call("POST", f"/rpc/tasks/{task_id}/cancel")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/cancel")
    async def cancel_session(session_id: str):
        orch: RpcClient = state["orchestrator"]
        data = await orch.call("POST", f"/rpc/sessions/{session_id}/cancel")
        return RpcEnvelope(ok=True, data=data)

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

    @app.get("/api/sessions")
    async def list_sessions():
        orch: RpcClient = state["orchestrator"]
        data = await orch.call("GET", "/rpc/sessions")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions")
    async def create_session(request: Request):
        orch: RpcClient = state["orchestrator"]
        body = await request.json()
        payload = dict(body) if isinstance(body, dict) else {}
        workspace_id = str(payload.get("workspace_id") or "").strip()
        cwd = str(payload.get("cwd") or "").strip()
        workspace_title = str(payload.get("workspace_title") or "").strip()
        workspace_kind = str(payload.get("workspace_kind") or "").strip()
        ssh_host_id = str(payload.get("ssh_host_id") or "").strip()
        if workspace_id:
            store = get_workspace_store()
            rec = store.get(workspace_id)
            if not rec:
                raise NotFoundError(f"workspace not found: {workspace_id}")
            cwd = rec.path
            workspace_title = workspace_title or rec.title
            workspace_kind = rec.kind or "local"
            ssh_host_id = rec.ssh_host_id or ""
            payload["workspace_id"] = workspace_id
            payload["cwd"] = cwd
            payload["workspace_title"] = workspace_title
            payload["workspace_kind"] = workspace_kind
            payload["ssh_host_id"] = ssh_host_id
        elif ssh_host_id and cwd:
            store = get_workspace_store()
            host_store = get_ssh_host_store()
            host = host_store.get(ssh_host_id)
            if not host:
                raise NotFoundError(f"ssh host not found: {ssh_host_id}")
            try:
                remote = await ensure_remote_dir(host, cwd)
            except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
                raise ValidationAppError(str(exc)) from exc
            rec = store.create_ssh(ssh_host_id=host.id, remote_path=remote, title=workspace_title)
            payload["workspace_id"] = rec.id
            payload["cwd"] = rec.path
            payload["workspace_title"] = rec.title
            payload["workspace_kind"] = "ssh"
            payload["ssh_host_id"] = host.id
        elif cwd:
            store = get_workspace_store()
            try:
                rec = store.create(cwd, title=workspace_title)
            except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
                raise ValidationAppError(str(exc)) from exc
            payload["workspace_id"] = rec.id
            payload["cwd"] = rec.path
            payload["workspace_title"] = rec.title
            payload["workspace_kind"] = "local"
            payload["ssh_host_id"] = ""
        data = await orch.call("POST", "/rpc/sessions", json=payload)
        wid = str(payload.get("workspace_id") or "")
        sid = str((data or {}).get("session_id") or payload.get("session_id") or "")
        if wid and sid:
            get_workspace_store().attach_session(wid, sid)
        return RpcEnvelope(ok=True, data=data)

    @app.patch("/api/sessions/{session_id}/workspace")
    async def bind_session_workspace(session_id: str, request: Request):
        orch: RpcClient = state["orchestrator"]
        body = await request.json()
        payload = dict(body) if isinstance(body, dict) else {}
        workspace_id = str(payload.get("workspace_id") or "").strip()
        cwd = str(payload.get("cwd") or "").strip()
        ssh_host_id = str(payload.get("ssh_host_id") or "").strip()
        if workspace_id:
            store = get_workspace_store()
            rec = store.get(workspace_id)
            if not rec:
                raise NotFoundError(f"workspace not found: {workspace_id}")
            payload["cwd"] = rec.path
            payload["workspace_id"] = rec.id
            payload["workspace_title"] = rec.title
            payload["workspace_kind"] = rec.kind or "local"
            payload["ssh_host_id"] = rec.ssh_host_id or ""
            store.attach_session(rec.id, session_id)
        elif ssh_host_id and cwd:
            store = get_workspace_store()
            host = get_ssh_host_store().get(ssh_host_id)
            if not host:
                raise NotFoundError(f"ssh host not found: {ssh_host_id}")
            try:
                remote = await ensure_remote_dir(host, cwd)
            except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
                raise ValidationAppError(str(exc)) from exc
            rec = store.create_ssh(ssh_host_id=host.id, remote_path=remote)
            payload["cwd"] = rec.path
            payload["workspace_id"] = rec.id
            payload["workspace_title"] = rec.title
            payload["workspace_kind"] = "ssh"
            payload["ssh_host_id"] = host.id
            store.attach_session(rec.id, session_id)
        elif cwd:
            store = get_workspace_store()
            try:
                rec = store.create(cwd)
            except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
                raise ValidationAppError(str(exc)) from exc
            payload["cwd"] = rec.path
            payload["workspace_id"] = rec.id
            payload["workspace_title"] = rec.title
            payload["workspace_kind"] = "local"
            payload["ssh_host_id"] = ""
            store.attach_session(rec.id, session_id)
        else:
            raise ValidationAppError("workspace_id or cwd required")
        data = await orch.call("PATCH", f"/rpc/sessions/{session_id}/workspace", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/workspaces")
    async def list_workspaces():
        store = get_workspace_store()
        return RpcEnvelope(ok=True, data={"workspaces": store.list_public()})

    @app.get("/api/workspaces/browse")
    async def workspace_browse(path: str = ""):
        try:
            data = browse_directory(path)
        except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as exc:
            raise ValidationAppError(str(exc)) from exc
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/workspaces")
    async def create_workspace(request: Request):
        body = await request.json()
        kind = str((body or {}).get("kind") or "local").strip().lower()
        path = str((body or {}).get("path") or "").strip()
        title = str((body or {}).get("title") or "").strip()
        store = get_workspace_store()
        if kind == "ssh":
            ssh_host_id = str((body or {}).get("ssh_host_id") or "").strip()
            host = get_ssh_host_store().get(ssh_host_id)
            if not host:
                raise NotFoundError(f"ssh host not found: {ssh_host_id}")
            try:
                remote = await ensure_remote_dir(host, path)
            except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
                raise ValidationAppError(str(exc)) from exc
            rec = store.create_ssh(ssh_host_id=host.id, remote_path=remote, title=title)
            return RpcEnvelope(ok=True, data=rec.public())
        try:
            rec = store.create(path, title=title)
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            raise ValidationAppError(str(exc)) from exc
        return RpcEnvelope(ok=True, data=rec.public())

    @app.delete("/api/workspaces/{workspace_id}")
    async def delete_workspace(workspace_id: str):
        store = get_workspace_store()
        ok = store.delete(workspace_id)
        if not ok:
            raise NotFoundError(workspace_id)
        return RpcEnvelope(ok=True, data={"deleted": workspace_id})

    @app.get("/api/ssh/config/hosts")
    async def list_ssh_config_hosts():
        from src.adapters.workspaces.ssh_config import parse_ssh_config, ssh_config_path

        cfg = ssh_config_path()
        entries = parse_ssh_config(cfg)
        return RpcEnvelope(
            ok=True,
            data={
                "config_path": str(cfg),
                "exists": cfg.exists(),
                "hosts": entries,
            },
        )

    @app.post("/api/ssh/hosts/import")
    async def import_ssh_config_host(request: Request):
        body = await request.json()
        alias = str((body or {}).get("alias") or "").strip()
        if not alias:
            raise ValidationAppError("alias required")
        store = get_ssh_host_store()
        try:
            rec = store.import_from_ssh_config(
                alias,
                label=str((body or {}).get("label") or "").strip(),
                default_path=str((body or {}).get("default_path") or "~").strip() or "~",
            )
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        return RpcEnvelope(ok=True, data=rec.public())

    @app.get("/api/ssh/hosts")
    async def list_ssh_hosts():
        store = get_ssh_host_store()
        return RpcEnvelope(ok=True, data={"hosts": store.list_public()})

    @app.post("/api/ssh/hosts")
    async def upsert_ssh_host(request: Request):
        body = await request.json()
        store = get_ssh_host_store()
        try:
            rec = store.upsert(body if isinstance(body, dict) else {})
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        return RpcEnvelope(ok=True, data=rec.public())

    @app.delete("/api/ssh/hosts/{host_id}")
    async def delete_ssh_host(host_id: str):
        store = get_ssh_host_store()
        if not store.delete(host_id):
            raise NotFoundError(host_id)
        return RpcEnvelope(ok=True, data={"deleted": host_id})

    @app.post("/api/ssh/hosts/{host_id}/test")
    async def test_ssh_host_api(host_id: str):
        store = get_ssh_host_store()
        host = store.get(host_id)
        if not host:
            raise NotFoundError(host_id)
        data = await test_ssh_host(host)
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/ssh/hosts/{host_id}/browse")
    async def browse_ssh_host(host_id: str, path: str = ""):
        store = get_ssh_host_store()
        host = store.get(host_id)
        if not host:
            raise NotFoundError(host_id)
        try:
            data = await browse_remote(host, path)
        except Exception as exc:
            raise ValidationAppError(str(exc)) from exc
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/providers")
    async def list_providers(configured_only: bool = True):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/providers",
            params={"configured_only": configured_only},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/settings/models")
    async def settings_models():
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("GET", "/rpc/settings/models")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/settings/models/providers")
    async def upsert_custom_provider(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call("POST", "/rpc/settings/models/providers", json=body)
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/api/settings/models/providers/{provider_id}")
    async def delete_custom_provider(provider_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("DELETE", f"/rpc/settings/models/providers/{provider_id}")
        return RpcEnvelope(ok=True, data=data)

    @app.put("/api/settings/models/default")
    async def set_default_provider(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call("PUT", "/rpc/settings/models/default", json=body)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/settings/models/reload")
    async def reload_model_settings():
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("POST", "/rpc/settings/models/reload")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/settings/models/discover")
    async def discover_models(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call("POST", "/rpc/settings/models/discover", json=body)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/settings/models/test")
    async def test_model_connectivity(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call("POST", "/rpc/settings/models/test", json=body)
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/settings/channels")
    async def list_channels():
        store = get_channel_store()
        return RpcEnvelope(
            ok=True,
            data=store.public_document(
                env_feishu_app_id=settings.feishu_app_id,
                env_feishu_app_secret=settings.feishu_app_secret,
            ),
        )

    @app.put("/api/settings/channels/feishu")
    async def upsert_feishu_channel(request: Request):
        body = await request.json()
        store = get_channel_store()
        store.upsert_feishu(body if isinstance(body, dict) else {})
        restart = state.get("restart_feishu_channel")
        runtime = await restart() if callable(restart) else {}
        return RpcEnvelope(
            ok=True,
            data={
                **store.public_document(
                    env_feishu_app_id=settings.feishu_app_id,
                    env_feishu_app_secret=settings.feishu_app_secret,
                ),
                "runtime": runtime,
            },
        )

    @app.post("/api/settings/channels/feishu/test")
    async def test_feishu_channel(request: Request):
        body = await request.json()
        store = get_channel_store()
        app_id = str(body.get("app_id") or "").strip() or store.feishu.app_id or settings.feishu_app_id
        app_secret = str(body.get("app_secret") or "").strip() or store.feishu.app_secret or settings.feishu_app_secret
        data = await test_feishu_app(app_id=app_id, app_secret=app_secret)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/settings/channels/feishu/reload")
    async def reload_feishu_channel():
        restart = state.get("restart_feishu_channel")
        runtime = await restart() if callable(restart) else {}
        store = get_channel_store()
        return RpcEnvelope(
            ok=True,
            data={
                **store.public_document(
                    env_feishu_app_id=settings.feishu_app_id,
                    env_feishu_app_secret=settings.feishu_app_secret,
                ),
                "runtime": runtime,
            },
        )

    @app.get("/api/plugins")
    async def list_plugins():
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("GET", "/rpc/plugins")
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/tools")
    async def list_tools():
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("GET", "/rpc/tools")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/plugins/{plugin_id}/enable")
    async def enable_plugin(plugin_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("POST", "/rpc/plugins/enable", json={"plugin_id": plugin_id})
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/plugins/{plugin_id}/disable")
    async def disable_plugin(plugin_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("POST", "/rpc/plugins/disable", json={"plugin_id": plugin_id})
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/plugins/reload")
    async def reload_plugins(plugin_id: Optional[str] = None):
        """Reload one plugin (query plugin_id) or all plugins from disk."""
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "POST",
            "/rpc/plugins/reload",
            json={"plugin_id": plugin_id} if plugin_id else {},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/plugins/{plugin_id}/reload")
    async def reload_one_plugin(plugin_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("POST", "/rpc/plugins/reload", json={"plugin_id": plugin_id})
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        orch: RpcClient = state["orchestrator"]
        data = await orch.call("GET", f"/rpc/sessions/{session_id}")
        return RpcEnvelope(ok=True, data=data)

    @app.patch("/api/sessions/{session_id}/interaction")
    async def patch_interaction(session_id: str, body: InteractionPatchRequest):
        orch: RpcClient = state["orchestrator"]
        data = await orch.call(
            "PATCH",
            f"/rpc/sessions/{session_id}/interaction",
            json=body.model_dump(exclude_none=True),
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/approvals")
    async def resolve_approval(session_id: str, body: GateResolveRequest):
        kernel: RpcClient = state["kernel"]
        orch: RpcClient = state["orchestrator"]
        action = (body.action or "allow").strip().lower()
        payload: Dict[str, Any] = {"action": action, "reason": body.reason}
        if action in ("allow_session", "always"):
            payload["action"] = "allow_session"
            try:
                await orch.call(
                    "PATCH",
                    f"/rpc/sessions/{session_id}/interaction",
                    json={"auto_accept": True},
                )
            except Exception:
                logger.exception("failed to set auto_accept for %s", session_id)
        data = await kernel.call(
            "POST",
            "/rpc/gates/resolve",
            json={"call_id": body.call_id, "payload": payload},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/ask-answers")
    async def resolve_ask(session_id: str, body: GateResolveRequest):
        kernel: RpcClient = state["kernel"]
        action = (body.action or "submit").strip().lower()
        payload: Dict[str, Any] = {
            "action": action,
            "answers": body.answers if body.answers is not None else {},
            "reason": body.reason,
        }
        data = await kernel.call(
            "POST",
            "/rpc/gates/resolve",
            json={"call_id": body.call_id, "payload": payload},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/accept-plan")
    async def accept_plan(session_id: str, body: AcceptPlanRequest):
        orch: RpcClient = state["orchestrator"]
        web: WebAdapter = state["web"]
        await orch.call(
            "PATCH",
            f"/rpc/sessions/{session_id}/interaction",
            json={"agent_mode": "agent", "plan_status": "accepted", "auto_accept": body.auto_accept},
        )
        content = (body.content or "").strip() or (
            "用户已接受计划。请按大纲逐步执行：允许使用 edit/write/run_shell。"
            "每完成一项在回复里勾选对应步骤。"
        )
        task = await web.handle_inbound(
            {
                "content": content,
                "session_id": session_id,
                "stream": True,
                "tools_enabled": body.tools_enabled,
                "model_provider": body.model_provider,
                "model_name": body.model_name,
                "workspace_id": body.workspace_id,
                "cwd": body.cwd,
                "workspace_kind": body.workspace_kind,
                "ssh_host_id": body.ssh_host_id,
                "agent_mode": "agent",
                "auto_accept": body.auto_accept,
            }
        )
        if task is None:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "accept-plan failed"})
        return RpcEnvelope(
            ok=True,
            data={"task_id": task.task_id, "session_id": task.session_id, "status": "queued"},
        )

    @app.get("/api/sessions/{session_id}/plugin-calls")
    async def session_plugin_calls(session_id: str, limit: int = 40):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/plugin-calls",
            params={"session_id": session_id, "limit": limit},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        orch: RpcClient = state["orchestrator"]
        data = await orch.call("DELETE", f"/rpc/sessions/{session_id}")
        return RpcEnvelope(ok=True, data=data)

    static_dir = Path(settings.web_static_dir)
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
