"""Adapters FastAPI application — Feishu webhook + Web SSE UI."""

from __future__ import annotations

import asyncio
import logging
import re
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
    multitask: Optional[bool] = None
    permission_preset: Optional[str] = None
    plan_enforcement: Optional[str] = None
    experience_tier: Optional[str] = None
    reasoning_effort: Optional[str] = None


class GateResolveRequest(BaseModel):
    call_id: str
    action: str = "allow"
    reason: Optional[str] = None
    feedback: Optional[str] = None
    answers: Optional[Any] = None
    auto_accept: Optional[bool] = None


class InteractionPatchRequest(BaseModel):
    agent_mode: Optional[str] = None
    auto_accept: Optional[bool] = None
    plan_status: Optional[str] = None
    permission_preset: Optional[str] = None
    plan_enforcement: Optional[str] = None
    experience_tier: Optional[str] = None
    reasoning_effort: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    pending_user_text: Optional[str] = None
    clear_pending_user_text: Optional[bool] = None


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


class EchartsRepairRequest(BaseModel):
    source: str
    error: str = ""
    model_provider: Optional[str] = None
    model_name: Optional[str] = None


class DrawioRepairRequest(BaseModel):
    source: str
    error: str = ""
    model_provider: Optional[str] = None
    model_name: Optional[str] = None


_MERMAID_REPAIR_SYSTEM = (
    "You fix ONLY Mermaid syntax errors. "
    "Return ONLY one fenced ```mermaid block. No prose. "
    "Rules: change the minimum needed for Mermaid v11 to parse; "
    "do NOT redesign the diagram, rename nodes, add/remove edges, or change labels/structure "
    "except to fix invalid punctuation/arrows/keywords. Prefer ASCII punctuation."
)

_ECHARTS_REPAIR_SYSTEM = (
    "You fix ONLY invalid Apache ECharts option JSON syntax/shape. "
    "Return ONLY one fenced ```echarts JSON object. No prose, no comments. "
    "Rules: minimal edits so setOption works — fix trailing commas, quotes, "
    "series must be an array with string type, data must be arrays; "
    "do NOT change chart meaning, titles, categories, or numeric values unless required for valid JSON."
)

_DRAWIO_REPAIR_SYSTEM = (
    "You fix ONLY invalid Draw.io / diagrams.net mxfile XML syntax. "
    "Return ONLY one fenced ```drawio XML document (mxfile or mxGraphModel wrapped in mxfile). "
    "No prose. Minimal edits: close tags, escape attributes, wrap mxGraphModel in mxfile if needed. "
    "Do NOT redesign the diagram or change cell labels/geometry beyond what syntax requires."
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

        feishu = FeishuAdapter(orchestrator, redis_client, settings, kernel=kernel)
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
            "Fix ONLY Mermaid syntax so it parses in Mermaid v11. Minimal changes; "
            "do not redesign. Common syntax fixes: `-.->` not `-. -->`; `-->` not `->`/`→`; "
            "edge labels `A -->|label| B`; ASCII punctuation; keep diagram type on first line.\n\n"
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

    @app.post("/api/echarts/repair")
    async def echarts_repair(body: EchartsRepairRequest):
        """Quiet one-shot model call to regenerate invalid ECharts option JSON (not a chat turn)."""
        source = (body.source or "").strip()
        if not source:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "source required"})
        kernel: RpcClient = state["kernel"]
        user = (
            "Fix ONLY ECharts option JSON syntax/shape so setOption works. Minimal changes; "
            "do not redesign the chart or alter data values unless required for valid JSON. "
            "Common fixes: series as array; each series needs type; data must be arrays; "
            "no trailing commas; double-quoted keys.\n\n"
            f"Render error:\n{body.error or '(unknown)'}\n\n"
            f"Broken source:\n```echarts\n{source}\n```\n"
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
                        {"role": "system", "content": _ECHARTS_REPAIR_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                },
            )
        except Exception as exc:
            logger.exception("echarts repair RPC failed")
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

    @app.post("/api/drawio/repair")
    async def drawio_repair(body: DrawioRepairRequest):
        """Quiet one-shot model call to fix invalid Draw.io mxfile XML (syntax only)."""
        source = (body.source or "").strip()
        if not source:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "source required"})
        kernel: RpcClient = state["kernel"]
        user = (
            "Fix ONLY Draw.io / mxfile XML syntax so diagrams.net can load it. "
            "Minimal changes; do not redesign. Wrap bare mxGraphModel in mxfile if needed; "
            "close tags; keep cell ids/labels/geometry.\n\n"
            f"Error:\n{body.error or '(unknown)'}\n\n"
            f"Broken source:\n```drawio\n{source}\n```\n"
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
                        {"role": "system", "content": _DRAWIO_REPAIR_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                },
            )
        except Exception as exc:
            logger.exception("drawio repair RPC failed")
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
    async def cancel_chat(task_id: str, request: Request):
        orch: RpcClient = state["orchestrator"]
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        data = await orch.call("POST", f"/rpc/tasks/{task_id}/cancel", json=body or {})
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/cancel")
    async def cancel_session(session_id: str, request: Request):
        orch: RpcClient = state["orchestrator"]
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        data = await orch.call("POST", f"/rpc/sessions/{session_id}/cancel", json=body or {})
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/sessions/{session_id}/inbox")
    async def get_session_inbox(session_id: str):
        orch: RpcClient = state["orchestrator"]
        data = await orch.call("GET", f"/rpc/sessions/{session_id}/inbox")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/inbox")
    async def post_session_inbox(session_id: str, request: Request):
        orch: RpcClient = state["orchestrator"]
        body = await request.json()
        data = await orch.call("POST", f"/rpc/sessions/{session_id}/inbox", json=body)
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/api/sessions/{session_id}/inbox/{item_id}")
    async def delete_session_inbox_item(session_id: str, item_id: str):
        orch: RpcClient = state["orchestrator"]
        data = await orch.call("DELETE", f"/rpc/sessions/{session_id}/inbox/{item_id}")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/files")
    async def post_session_file(session_id: str, request: Request):
        """Push a generated/uploaded file card into the chat timeline."""
        orch: RpcClient = state["orchestrator"]
        body = await request.json()
        payload = dict(body) if isinstance(body, dict) else {}
        data = await orch.call("POST", f"/rpc/sessions/{session_id}/files", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/delivery")
    async def post_session_delivery(session_id: str, request: Request):
        """Publish Delivery markdown to chat + optional ``.nlm/deliveries/`` on local cwd."""
        from src.common.delivery_store import DeliveryWriteError, write_delivery_to_workspace

        orch: RpcClient = state["orchestrator"]
        body = await request.json()
        payload = dict(body) if isinstance(body, dict) else {}
        content = str(payload.get("content") or "")
        name = str(payload.get("name") or payload.get("file_name") or "Delivery.md").strip()
        cwd = str(payload.get("cwd") or "").strip()
        workspace_kind = str(payload.get("workspace_kind") or "local").strip() or "local"

        file_card = await orch.call(
            "POST",
            f"/rpc/sessions/{session_id}/files",
            json={
                "name": name,
                "content": content,
                "mime": "text/markdown",
                "path": payload.get("path"),
            },
        )
        workspace: Dict[str, Any] = {"ok": False}
        if cwd:
            try:
                workspace = write_delivery_to_workspace(
                    cwd,
                    file_name=name,
                    content=content,
                    workspace_kind=workspace_kind,
                )
            except DeliveryWriteError as exc:
                workspace = {"ok": False, "error": str(exc)}
            except Exception as exc:
                logger.exception("delivery workspace write failed")
                workspace = {"ok": False, "error": str(exc)}

        return RpcEnvelope(
            ok=True,
            data={
                "session_id": session_id,
                "file": file_card,
                "workspace": workspace,
            },
        )

    @app.get("/api/chat/stream")
    async def web_sse(session_id: str, after: str = ""):
        web: WebAdapter = state["web"]
        return StreamingResponse(
            web.sse_stream(session_id, after_event_id=(after or "").strip()),
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

    @app.get("/api/plugins/{plugin_id}/config")
    async def get_plugin_config(plugin_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("GET", f"/rpc/plugins/{plugin_id}/config")
        return RpcEnvelope(ok=True, data=data)

    @app.put("/api/plugins/{plugin_id}/config")
    async def put_plugin_config(plugin_id: str, request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call("PUT", f"/rpc/plugins/{plugin_id}/config", json=body)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/plugins/install")
    async def install_plugin_package(request: Request):
        """Install a local plugin package (directory path or uploaded zip)."""
        from src.common.plugin_package import PluginPackageError, install_from_directory, install_from_zip

        ctype = (request.headers.get("content-type") or "").lower()
        try:
            if "multipart/form-data" in ctype:
                form = await request.form()
                upload = form.get("file")
                if upload is None:
                    raise ValidationAppError("file required")
                staging = Path("data") / "plugin_uploads"
                staging.mkdir(parents=True, exist_ok=True)
                dest = staging / Path(getattr(upload, "filename", None) or "plugin.zip").name
                dest.write_bytes(await upload.read())  # type: ignore[misc]
                data = install_from_zip(dest)
            else:
                body = await request.json()
                path_str = str(body.get("path") or "").strip()
                if not path_str:
                    raise ValidationAppError("path required")
                path = Path(path_str)
                if path.suffix.lower() == ".zip":
                    data = install_from_zip(path)
                else:
                    data = install_from_directory(path)
        except PluginPackageError as exc:
            raise ValidationAppError(str(exc)) from exc

        kernel: RpcClient = state["kernel"]
        try:
            await kernel.call("POST", "/rpc/plugins/reload", json={})
            data["reloaded"] = True
        except Exception:
            data["reloaded"] = False
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/teams/{team_id}")
    async def team_snapshot(team_id: str):
        from src.core_kernel.teams import get_team_dag, get_team_mailbox

        mbox = get_team_mailbox().snapshot(team_id)
        dag = get_team_dag().snapshot(team_id)
        return RpcEnvelope(
            ok=True,
            data={
                "enabled": bool(settings.nlm_experimental_teams),
                "mailbox": mbox,
                "dag": dag,
            },
        )

    @app.post("/api/teams/{team_id}/dag")
    async def team_dag_add(team_id: str, request: Request):
        from src.core_kernel.teams import get_team_dag

        body = await request.json()
        node = get_team_dag().add_node(
            team_id,
            label=str(body.get("label") or ""),
            depends_on=list(body.get("depends_on") or []),
            node_id=body.get("node_id"),
            meta=body.get("meta") if isinstance(body.get("meta"), dict) else None,
        )
        return RpcEnvelope(ok=True, data=node.to_dict())

    @app.post("/api/teams/{team_id}/dag/{node_id}/mark")
    async def team_dag_mark(team_id: str, node_id: str, request: Request):
        from src.core_kernel.teams import get_team_dag

        body = await request.json()
        status = str(body.get("status") or "done")
        node = get_team_dag().mark(team_id, node_id, status)
        if not node:
            raise NotFoundError("dag node not found")
        return RpcEnvelope(ok=True, data=node.to_dict())

    @app.get("/api/acp/backends")
    async def acp_backends():
        from src.core_kernel.subagent.backend import list_subagent_backends

        return RpcEnvelope(ok=True, data={"backends": list_subagent_backends()})

    @app.post("/api/acp/sessions")
    async def acp_create_session(request: Request):
        """Thin ACP-style session create → existing session API."""
        body = await request.json()
        orch: RpcClient = state["orchestrator"]
        data = await orch.call(
            "POST",
            "/rpc/sessions",
            json={
                "cwd": body.get("cwd"),
                "workspace_id": body.get("workspace_id"),
                "title": body.get("title") or "ACP session",
            },
        )
        return RpcEnvelope(ok=True, data={"sessionId": data.get("id") or data.get("session_id"), "raw": data})

    @app.post("/api/acp/sessions/{session_id}/prompt")
    async def acp_prompt(session_id: str, request: Request):
        """Map ACP prompt → /api/chat queue (HTTP+SSE workbench bridge)."""
        body = await request.json()
        prompt = str(body.get("prompt") or body.get("text") or "").strip()
        if not prompt:
            raise ValidationAppError("prompt required")
        web: WebAdapter = state["web"]
        task = await web.handle_inbound(
            {
                "content": prompt,
                "session_id": session_id,
                "user_id": str(body.get("user_id") or "acp-user"),
                "model_provider": body.get("model_provider"),
                "model_name": body.get("model_name"),
                "cwd": body.get("cwd"),
                "stream": True,
            }
        )
        if task is None:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "prompt required"})
        return RpcEnvelope(
            ok=True,
            data={
                "task_id": task.task_id,
                "session_id": task.session_id,
                "status": "queued",
            },
        )

    @app.post("/api/acp/backends/{backend}/spawn")
    async def acp_backend_spawn(backend: str, request: Request):
        from src.core_kernel.subagent.backend import get_subagent_backend

        body = await request.json()
        try:
            be = get_subagent_backend(backend)
        except KeyError as exc:
            raise ValidationAppError(str(exc)) from exc
        prompt = str(body.get("prompt") or "").strip()
        session_id = str(body.get("session_id") or "").strip()
        if not prompt or not session_id:
            raise ValidationAppError("prompt and session_id required")
        data = await be.spawn(
            prompt=prompt,
            session_id=session_id,
            cwd=body.get("cwd"),
            model=body.get("model"),
            label=body.get("label"),
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/generated-images/{name}")
    async def get_generated_image(name: str):
        from fastapi.responses import FileResponse

        safe = Path(name).name
        if not safe.endswith(".png") and not safe.endswith(".jpg") and not safe.endswith(".webp"):
            raise ValidationAppError("invalid image name")
        root = Path(__file__).resolve().parents[2] / "data" / "generated_images"
        path = root / safe
        if not path.exists():
            raise NotFoundError("image not found")
        return FileResponse(path)

    @app.get("/api/workspace/git-info")
    async def workspace_git_info(cwd: str = "", workspace_kind: str = "local"):
        """Return git branch + working-tree line stats vs HEAD (best-effort)."""
        path = (cwd or "").strip()
        empty = {
            "branch": "",
            "is_repo": False,
            "cwd": path,
            "insertions": 0,
            "deletions": 0,
        }
        if not path or workspace_kind == "ssh":
            return RpcEnvelope(ok=True, data=empty)
        root = Path(path)
        if not root.exists():
            return RpcEnvelope(ok=True, data=empty)

        async def _git(*args: str) -> tuple[int, str]:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
            text = out.decode("utf-8", errors="ignore").strip() if out else ""
            return int(proc.returncode or 0), text

        try:
            code, branch = await _git("rev-parse", "--abbrev-ref", "HEAD")
            if code != 0 or not branch:
                return RpcEnvelope(ok=True, data=empty)

            insertions = 0
            deletions = 0
            # Tracked changes vs HEAD (staged + unstaged)
            sc, short = await _git("diff", "--shortstat", "HEAD")
            if sc == 0 and short:
                m_ins = re.search(r"(\d+)\s+insertion", short)
                m_del = re.search(r"(\d+)\s+deletion", short)
                if m_ins:
                    insertions += int(m_ins.group(1))
                if m_del:
                    deletions += int(m_del.group(1))

            return RpcEnvelope(
                ok=True,
                data={
                    "branch": branch,
                    "is_repo": True,
                    "cwd": path,
                    "insertions": insertions,
                    "deletions": deletions,
                },
            )
        except Exception:
            return RpcEnvelope(ok=True, data=empty)

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
            "feedback": body.feedback or body.reason,
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
