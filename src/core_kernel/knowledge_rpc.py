"""Kernel knowledge-base RPC routes (/rpc/knowledge/*)."""

from __future__ import annotations

import base64
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, Request

from src.common.schemas import RpcEnvelope

from src.core_kernel.plugin_runtime.knowledge_ingest import (
    MAX_SESSION_UPLOAD_BYTES,
    library_ingest_max_bytes,
)

SESSION_UPLOAD_ROOT = Path("data") / "session_uploads"
MAX_UPLOAD_BYTES = MAX_SESSION_UPLOAD_BYTES
logger = logging.getLogger(__name__)


def register_knowledge_rpc(app: FastAPI, state: Dict[str, Any]) -> None:

    def _kb_store():
        from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore

        return KnowledgeStore(state["session_factory"])

    def _guard_session_doc(row: Optional[Dict[str, Any]], session_id: str = "") -> bool:
        from src.core_kernel.plugin_runtime.knowledge_store import row_visible_for_session

        return row_visible_for_session(row, session_id)

    @app.get("/rpc/knowledge/docs")
    async def kb_list_docs(workspace_id: str = "", limit: int = 50, tag: str = ""):
        store = _kb_store()
        await store.ensure_schema()
        docs = await store.list_docs(
            workspace_id=workspace_id or "", limit=min(max(limit, 1), 200), tag=tag or ""
        )
        return RpcEnvelope(ok=True, data={"docs": docs})

    @app.get("/rpc/knowledge/search")
    async def kb_search(query: str = "", workspace_id: str = "", limit: int = 8, tag: str = "", session_id: str = ""):
        from src.core_kernel.plugin_runtime.knowledge_store import citations_markdown

        store = _kb_store()
        await store.ensure_schema()
        q = (query or "").strip()
        if not q:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "query required"})
        hits = await store.search(
            q, workspace_id=workspace_id or "", limit=min(max(limit, 1), 40), tag=tag or "", session_id=session_id or ""
        )
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
    async def kb_get_doc(doc_id: str, include_chunks: bool = False, session_id: str = ""):
        store = _kb_store()
        await store.ensure_schema()
        row = await store.get(doc_id, include_chunks=include_chunks)
        if not row or not _guard_session_doc(row, session_id):
            return RpcEnvelope(ok=False, error={"code": "NOT_FOUND", "message": f"doc not found: {doc_id}"})
        return RpcEnvelope(ok=True, data=row)

    @app.get("/rpc/knowledge/docs/{doc_id}/read")
    async def kb_read_doc(
        doc_id: str,
        offset: int = 0,
        limit: int = 4000,
        chunk_index: Optional[int] = None,
        neighbors: int = 1,
        session_id: str = "",
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
        if not row or not _guard_session_doc(row, session_id):
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
                content, ingest_note = read_file_as_text(
                    target, max_bytes=library_ingest_max_bytes()
                )
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

    @app.post("/rpc/knowledge/docs/file")
    async def kb_add_library_file(request: Request):
        from src.core_kernel.plugin_runtime.knowledge_ingest import (
            SUPPORTED_SUFFIXES,
            default_tags_for_name,
            read_bytes_as_text,
        )
        from src.core_kernel.plugin_runtime.knowledge_store import content_hash

        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        filename = Path(str(body.get("filename") or "upload.txt")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return RpcEnvelope(
                ok=False,
                error={"code": "TYPE", "message": f"unsupported type: {suffix or filename}"},
            )
        raw_b64 = str(body.get("content_b64") or "")
        try:
            raw = base64.b64decode(raw_b64, validate=False)
        except Exception:
            return RpcEnvelope(ok=False, error={"code": "BAD", "message": "content_b64 invalid"})
        if not raw:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "file empty"})
        limit = library_ingest_max_bytes()
        if len(raw) > limit:
            return RpcEnvelope(
                ok=False,
                error={"code": "SIZE", "message": f"file too large ({len(raw)} bytes, max {limit})"},
            )
        try:
            content, ingest_note = read_bytes_as_text(
                raw, suffix, filename=filename, max_bytes=limit
            )
        except ValueError as exc:
            return RpcEnvelope(ok=False, error={"code": "INGEST", "message": str(exc)})
        workspace_id = str(body.get("workspace_id") or "")
        digest = content_hash(content)
        doc_id = str(body.get("doc_id") or "").strip()
        if not doc_id:
            key = f"{workspace_id}:{filename}:{digest}"
            doc_id = "upload_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        tags = default_tags_for_name(filename)
        extra = "upload,manual"
        tags = f"{tags},{extra}" if tags else extra
        title = str(body.get("title") or "").strip() or Path(filename).stem
        row = await store.upsert(
            doc_id=doc_id,
            title=title,
            content=content,
            tags=tags,
            source=f"upload:{filename}",
            source_uri=filename,
            workspace_id=workspace_id,
            content_hash_value=digest,
        )
        if ingest_note:
            row = {**row, "ingest_note": ingest_note}
        row = {**row, "filename": filename, "bytes": len(raw)}
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
    async def kb_delete_doc(doc_id: str, session_id: str = ""):
        store = _kb_store()
        await store.ensure_schema()
        row = await store.get(doc_id)
        if row and not _guard_session_doc(row, session_id):
            return RpcEnvelope(ok=False, error={"code": "NOT_FOUND", "message": f"doc not found: {doc_id}"})
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
        if not title:
            title = "untitled"
        digest = content_hash(content)
        if not doc_id:
            by_hash = await store.find_by_content_hash(digest, workspace_id=workspace_id)
            if by_hash and by_hash.get("doc_id"):
                doc_id = str(by_hash["doc_id"])
            else:
                from uuid import uuid4

                doc_id = f"kb_{uuid4().hex[:12]}"
                await store.upsert(
                    doc_id=doc_id,
                    title=title,
                    content=content,
                    tags="weknora",
                    source="weknora_push",
                    workspace_id=workspace_id,
                    content_hash_value=digest,
                )
        from src.core_kernel.plugin_runtime.knowledge_sync import (
            is_real_remote_id,
            lookup_weknora_remote_id,
            record_weknora_push_identity,
        )
        from src.core_kernel.plugin_runtime.weknora_client import weknora_update_document

        known = await lookup_weknora_remote_id(
            store, kb_id=kb_id, local_doc_id=doc_id, workspace_id=workspace_id
        )
        push_meta = {"nlm_doc_id": doc_id, "content_hash": digest}
        if is_real_remote_id(known):
            data = await weknora_update_document(
                knowledge_id=known,
                title=title,
                content=content,
                kb_id=kb_id,
                workspace_id=workspace_id,
                metadata=push_meta,
            )
            if not (data.get("ok") and (data.get("updated") or data.get("pushed"))):
                data = {
                    **data,
                    "skipped": True,
                    "reason": "refused append-only POST; update failed",
                    "doc_id": doc_id,
                }
                return RpcEnvelope(ok=bool(data.get("ok")), data=data)
        elif known.startswith("titlehash:"):
            data = {
                "ok": True,
                "skipped": True,
                "pushed": False,
                "reason": "refused append-only POST (remote id unknown; title/hash fallback only)",
                "doc_id": doc_id,
            }
            return RpcEnvelope(ok=True, data=data)
        else:
            data = await weknora_push_document(
                title=title,
                content=content,
                kb_id=kb_id,
                workspace_id=workspace_id,
                metadata=push_meta,
            )
        if data.get("ok") and data.get("pushed"):
            await record_weknora_push_identity(
                store,
                kb_id=str(data.get("kb_id") or kb_id),
                local_doc_id=doc_id,
                remote_id=str(data.get("knowledge_id") or known or ""),
                digest=digest,
                workspace_id=workspace_id,
                title=title,
                message=f"pushed knowledge_id={data.get('knowledge_id') or known or ''}",
            )
        data = {**data, "doc_id": doc_id}
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

    @app.get("/rpc/knowledge/weknora/item")
    async def weknora_get_knowledge_rpc(knowledge_id: str = ""):
        from src.core_kernel.plugin_runtime.weknora_client import weknora_get_knowledge

        kid = (knowledge_id or "").strip()
        if not kid:
            return RpcEnvelope(
                ok=False, error={"code": "EMPTY", "message": "knowledge_id required"}
            )
        data = await weknora_get_knowledge(kid)
        return RpcEnvelope(ok=bool(data.get("ok") or data.get("skipped")), data=data)

    @app.post("/rpc/knowledge/weknora/import")
    async def weknora_import_rpc(request: Request):
        from src.core_kernel.plugin_runtime.knowledge_sync import import_weknora_knowledge

        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        kid = str(body.get("knowledge_id") or body.get("doc_id") or "").strip()
        if not kid:
            return RpcEnvelope(
                ok=False, error={"code": "EMPTY", "message": "knowledge_id required"}
            )
        data = await import_weknora_knowledge(
            store,
            knowledge_id=kid,
            workspace_id=str(body.get("workspace_id") or ""),
            kb_id=str(body.get("kb_id") or ""),
        )
        return RpcEnvelope(ok=bool(data.get("ok")), data=data)

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

    @app.post("/rpc/knowledge/uploads")
    async def kb_session_upload(request: Request):
        from src.core_kernel.plugin_runtime.knowledge_ingest import (
            SUPPORTED_SUFFIXES,
            default_tags_for_name,
            read_bytes_as_text,
        )
        from src.core_kernel.plugin_runtime.knowledge_store import content_hash

        store = _kb_store()
        await store.ensure_schema()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        session_id = str(body.get("session_id") or "").strip()
        if not session_id:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "session_id required"})
        filename = Path(str(body.get("filename") or "upload.txt")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return RpcEnvelope(
                ok=False,
                error={"code": "TYPE", "message": f"unsupported type: {suffix or filename}"},
            )
        raw_b64 = str(body.get("content_b64") or "")
        try:
            raw = base64.b64decode(raw_b64, validate=False)
        except Exception:
            return RpcEnvelope(ok=False, error={"code": "BAD", "message": "content_b64 invalid"})
        if not raw:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "file empty"})
        if len(raw) > MAX_UPLOAD_BYTES:
            return RpcEnvelope(
                ok=False,
                error={"code": "SIZE", "message": f"file too large ({len(raw)} bytes)"},
            )
        try:
            content, ingest_note = read_bytes_as_text(
                raw, suffix, filename=filename, max_bytes=MAX_UPLOAD_BYTES
            )
        except ValueError as exc:
            return RpcEnvelope(ok=False, error={"code": "INGEST", "message": str(exc)})
        dest_dir = SESSION_UPLOAD_ROOT / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        dest.write_bytes(raw)
        digest = content_hash(content)
        doc_id = "upl_" + hashlib.sha1(f"{session_id}:{filename}:{digest}".encode()).hexdigest()[:16]
        tags = default_tags_for_name(filename)
        extra = f"session-upload,session:{session_id}"
        tags = f"{tags},{extra}" if tags else extra
        row = await store.upsert(
            doc_id=doc_id,
            title=str(body.get("title") or Path(filename).stem),
            content=content,
            tags=tags,
            source="session-upload",
            source_uri=f"session/{session_id}/{filename}",
            workspace_id=str(body.get("workspace_id") or ""),
            content_hash_value=digest,
        )
        if ingest_note:
            row = {**row, "ingest_note": ingest_note}
        row = {**row, "filename": filename, "bytes": len(raw), "session_id": session_id}
        return RpcEnvelope(ok=True, data=row)

    @app.get("/rpc/knowledge/uploads")
    async def kb_session_uploads(session_id: str = ""):
        sid = (session_id or "").strip()
        if not sid:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "session_id required"})
        store = _kb_store()
        await store.ensure_schema()
        docs = await store.list_docs(limit=80, tag=f"session:{sid}")
        return RpcEnvelope(ok=True, data={"docs": docs, "session_id": sid})

    @app.delete("/rpc/knowledge/uploads/{doc_id}")
    async def kb_session_upload_delete(doc_id: str, session_id: str = ""):
        store = _kb_store()
        await store.ensure_schema()
        row = await store.get(doc_id)
        if not row:
            return RpcEnvelope(ok=False, error={"code": "NOT_FOUND", "message": f"doc not found: {doc_id}"})
        sid = (session_id or "").strip()
        if not sid:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "session_id required"})
        tags = str(row.get("tags") or "")
        if f"session:{sid}" not in tags:
            return RpcEnvelope(ok=False, error={"code": "FORBIDDEN", "message": "not this session"})
        if str(row.get("source") or "") != "session-upload":
            return RpcEnvelope(ok=False, error={"code": "BAD", "message": "not a session upload"})
        ok = await store.delete(doc_id)
        uri = str(row.get("source_uri") or "")
        if uri.startswith("session/") and sid:
            path = SESSION_UPLOAD_ROOT / sid / Path(uri).name
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return RpcEnvelope(ok=True, data={"ok": ok, "doc_id": doc_id})

    @app.delete("/rpc/knowledge/uploads")
    async def kb_session_uploads_purge(session_id: str = ""):
        sid = (session_id or "").strip()
        if not sid:
            return RpcEnvelope(ok=False, error={"code": "EMPTY", "message": "session_id required"})
        store = _kb_store()
        await store.ensure_schema()
        docs = await store.list_docs(limit=200, tag=f"session:{sid}")
        deleted = 0
        for doc in docs:
            did = str(doc.get("doc_id") or "")
            if did and await store.delete(did):
                deleted += 1
        dest = SESSION_UPLOAD_ROOT / sid
        try:
            shutil.rmtree(dest, ignore_errors=True)
        except OSError:
            logger.debug("session upload dir cleanup failed: %s", dest, exc_info=True)
        return RpcEnvelope(ok=True, data={"ok": True, "deleted": deleted, "session_id": sid})

