"""Adapters knowledge-base REST proxy (/api/knowledge/* + session uploads)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request

from src.common.errors import ValidationAppError
from src.common.rpc_client import RpcClient
from src.common.schemas import RpcEnvelope
from src.core_kernel.knowledge_rpc import MAX_UPLOAD_BYTES


def register_knowledge_routes(app: FastAPI, state: Dict[str, Any]) -> None:

    @app.get("/api/knowledge/docs")
    async def knowledge_list(workspace_id: str = "", limit: int = 50, tag: str = ""):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/knowledge/docs",
            params={"workspace_id": workspace_id or "", "limit": limit, "tag": tag or ""},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/search")
    async def knowledge_search(query: str = "", workspace_id: str = "", limit: int = 8, tag: str = "", session_id: str = ""):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/knowledge/search",
            params={"query": query, "workspace_id": workspace_id or "", "limit": limit, "tag": tag or "", "session_id": session_id or ""},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/stats")
    async def knowledge_stats(workspace_id: str = ""):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/knowledge/stats",
            params={"workspace_id": workspace_id or ""},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/docs/{doc_id}")
    async def knowledge_get(doc_id: str, include_chunks: bool = False, session_id: str = ""):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            f"/rpc/knowledge/docs/{doc_id}",
            params={"include_chunks": include_chunks, "session_id": session_id or ""},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/docs/{doc_id}/read")
    async def knowledge_read(
        doc_id: str,
        offset: int = 0,
        limit: int = 4000,
        chunk_index: Optional[int] = None,
        neighbors: int = 1,
        session_id: str = "",
    ):
        kernel: RpcClient = state["kernel"]
        params: Dict[str, Any] = {
            "offset": offset,
            "limit": limit,
            "neighbors": neighbors,
            "session_id": session_id or "",
        }
        if chunk_index is not None:
            params["chunk_index"] = chunk_index
        data = await kernel.call(
            "GET",
            f"/rpc/knowledge/docs/{doc_id}/read",
            params=params,
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/docs")
    async def knowledge_add(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        payload = dict(body) if isinstance(body, dict) else {}
        data = await kernel.call("POST", "/rpc/knowledge/docs", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.patch("/api/knowledge/docs/{doc_id}")
    async def knowledge_patch(doc_id: str, request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        payload = dict(body) if isinstance(body, dict) else {}
        data = await kernel.call("PATCH", f"/rpc/knowledge/docs/{doc_id}", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/api/knowledge/docs/{doc_id}")
    async def knowledge_delete(doc_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("DELETE", f"/rpc/knowledge/docs/{doc_id}")
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/reindex")
    async def knowledge_reindex(request: Request):
        kernel: RpcClient = state["kernel"]
        try:
            body = await request.json()
        except Exception:
            body = {}
        payload = dict(body) if isinstance(body, dict) else {}
        data = await kernel.call("POST", "/rpc/knowledge/reindex", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/sync/docs")
    async def knowledge_sync_docs(request: Request):
        kernel: RpcClient = state["kernel"]
        try:
            body = await request.json()
        except Exception:
            body = {}
        payload = dict(body) if isinstance(body, dict) else {}
        data = await kernel.call("POST", "/rpc/knowledge/sync/docs", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/sync/feishu")
    async def knowledge_sync_feishu(request: Request):
        kernel: RpcClient = state["kernel"]
        try:
            body = await request.json()
        except Exception:
            body = {}
        payload = dict(body) if isinstance(body, dict) else {}
        data = await kernel.call("POST", "/rpc/knowledge/sync/feishu", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/sync/log")
    async def knowledge_sync_log(workspace_id: str = "", limit: int = 40):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/knowledge/sync/log",
            params={"workspace_id": workspace_id or "", "limit": limit},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/weknora/health")
    async def knowledge_weknora_health():
        kernel: RpcClient = state["kernel"]
        data = await kernel.call("GET", "/rpc/knowledge/weknora/health")
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/weknora/kbs")
    async def knowledge_weknora_kbs(limit: int = 50):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET", "/rpc/knowledge/weknora/kbs", params={"limit": limit}
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/weknora/search")
    async def knowledge_weknora_search(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call(
            "POST",
            "/rpc/knowledge/weknora/search",
            json=body if isinstance(body, dict) else {},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/weknora/knowledge")
    async def knowledge_weknora_knowledge(
        kb_id: str = "",
        page: int = 1,
        page_size: int = 40,
    ):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/knowledge/weknora/knowledge",
            params={"kb_id": kb_id or "", "page": page, "page_size": page_size},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/knowledge/weknora/item")
    async def knowledge_weknora_item(knowledge_id: str = ""):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/knowledge/weknora/item",
            params={"knowledge_id": knowledge_id or ""},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/weknora/import")
    async def knowledge_weknora_import(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call(
            "POST",
            "/rpc/knowledge/weknora/import",
            json=body if isinstance(body, dict) else {},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/weknora/push")
    async def knowledge_weknora_push(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call(
            "POST",
            "/rpc/knowledge/weknora/push",
            json=body if isinstance(body, dict) else {},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/knowledge/weknora/sync")
    async def knowledge_weknora_sync(request: Request):
        kernel: RpcClient = state["kernel"]
        body = await request.json()
        data = await kernel.call(
            "POST",
            "/rpc/knowledge/weknora/sync",
            json=body if isinstance(body, dict) else {},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.post("/api/sessions/{session_id}/uploads")
    async def session_upload(session_id: str, request: Request, workspace_id: str = ""):
        kernel: RpcClient = state["kernel"]
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise ValidationAppError("file required")
        filename = Path(str(getattr(upload, "filename", None) or "upload.txt")).name
        raw = await upload.read()  # type: ignore[misc]
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValidationAppError(f"file too large ({len(raw)} bytes)")
        payload = {
            "session_id": session_id,
            "filename": filename,
            "content_b64": base64.b64encode(bytes(raw)).decode("ascii"),
            "workspace_id": workspace_id or str(form.get("workspace_id") or ""),
            "title": str(form.get("title") or ""),
        }
        data = await kernel.call("POST", "/rpc/knowledge/uploads", json=payload)
        return RpcEnvelope(ok=True, data=data)

    @app.get("/api/sessions/{session_id}/uploads")
    async def session_uploads_list(session_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "GET",
            "/rpc/knowledge/uploads",
            params={"session_id": session_id},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/api/sessions/{session_id}/uploads/{doc_id}")
    async def session_upload_delete(session_id: str, doc_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "DELETE",
            f"/rpc/knowledge/uploads/{doc_id}",
            params={"session_id": session_id},
        )
        return RpcEnvelope(ok=True, data=data)

    @app.delete("/api/sessions/{session_id}/uploads")
    async def session_uploads_purge(session_id: str):
        kernel: RpcClient = state["kernel"]
        data = await kernel.call(
            "DELETE",
            "/rpc/knowledge/uploads",
            params={"session_id": session_id},
        )
        return RpcEnvelope(ok=True, data=data)

