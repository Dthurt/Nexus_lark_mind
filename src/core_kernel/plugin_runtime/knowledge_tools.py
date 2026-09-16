"""Builtin knowledge-base tools — chunked SQLite search + optional hybrid embeddings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from src.common.errors import PluginError
from src.core_kernel.plugin_runtime.invoke_context import get_workspace_cwd, get_workspace_meta
from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore, content_hash
from src.core_kernel.plugin_runtime.knowledge_sync import (
    FeishuWikiConnector,
    stable_doc_id_for_path,
    sync_workspace_docs,
)
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest
from src.infrastructure.storage.database import get_session_factory

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "kb_add",
        "description": (
            "Add or update a document in the local knowledge base (SQLite). "
            "Pass title+content, or path (workspace-relative) to ingest a file "
            "(sets source=file:...). Use for notes, specs, decisions, or reference text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path; reads file and sets source=file:...",
                },
                "tags": {"type": "string", "description": "Comma-separated tags"},
                "doc_id": {"type": "string", "description": "Optional id; omit to create new"},
                "source": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "kb_search",
        "description": (
            "Search the local knowledge base (keyword + optional embeddings hybrid). "
            "Returns ranked hits with stable doc_id, chunk_id, and longer snippets. "
            "Always follow with kb_read / kb_get before answering from KB content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 6},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb_read",
        "description": (
            "Read a knowledge-base document window by doc_id (offset/limit chars), "
            "or a chunk plus neighbors (chunk_index + neighbors). Prefer after kb_search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "offset": {"type": "integer", "default": 0},
                "limit": {"type": "integer", "default": 4000},
                "chunk_index": {"type": "integer"},
                "neighbors": {"type": "integer", "default": 1},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "kb_get",
        "description": "Fetch a full knowledge-base document by doc_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "include_chunks": {"type": "boolean", "default": False},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "kb_list",
        "description": "List recent knowledge-base documents.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 20}},
        },
    },
    {
        "name": "kb_delete",
        "description": "Delete a knowledge-base document by doc_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
    },
    {
        "name": "kb_sync_docs",
        "description": (
            "Scan workspace docs/**/*.md (and shallow *.md) into the knowledge base "
            "with content_hash upsert. Use when the user asks to index project docs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_files": {"type": "integer", "default": 400},
            },
        },
    },
]


class KnowledgeToolsPlugin(BasePlugin):
    def __init__(self, manifest: PluginManifest) -> None:
        super().__init__(manifest)
        self._store: KnowledgeStore | None = None

    def _kb(self) -> KnowledgeStore:
        if self._store is None:
            self._store = KnowledgeStore(get_session_factory())
        return self._store

    async def _on_init(self) -> None:
        return None

    async def _on_ready(self) -> None:
        self.manifest.tools = list(TOOLS)
        try:
            await self._kb().ensure_schema()
        except Exception:
            pass

    async def _on_teardown(self) -> None:
        self._store = None

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        meta = get_workspace_meta() or {}
        ws = str(meta.get("workspace_id") or "")
        store = self._kb()
        if tool_name == "kb_add":
            return await self._kb_add(store, arguments, ws)
        if tool_name == "kb_search":
            q = str(arguments.get("query") or "").strip()
            if not q:
                raise PluginError("query required")
            limit = int(arguments.get("limit") or 6)
            hits = await store.search(q, workspace_id=ws, limit=max(1, min(limit, 20)))
            return {"ok": True, "query": q, "results": hits}
        if tool_name == "kb_read":
            doc_id = str(arguments.get("doc_id") or "").strip()
            if not doc_id:
                raise PluginError("doc_id required")
            chunk_index = arguments.get("chunk_index")
            row = await store.read(
                doc_id,
                offset=int(arguments.get("offset") or 0),
                limit=int(arguments.get("limit") or 4000),
                chunk_index=int(chunk_index) if chunk_index is not None else None,
                neighbors=int(arguments.get("neighbors") or 1),
            )
            if not row:
                raise PluginError(f"doc not found: {doc_id}")
            return row
        if tool_name == "kb_get":
            doc_id = str(arguments.get("doc_id") or "").strip()
            row = await store.get(
                doc_id, include_chunks=bool(arguments.get("include_chunks"))
            )
            if not row:
                raise PluginError(f"doc not found: {doc_id}")
            return row
        if tool_name == "kb_list":
            limit = int(arguments.get("limit") or 20)
            return {"ok": True, "docs": await store.list_docs(workspace_id=ws, limit=limit)}
        if tool_name == "kb_delete":
            doc_id = str(arguments.get("doc_id") or "").strip()
            ok = await store.delete(doc_id)
            return {"ok": ok, "doc_id": doc_id}
        if tool_name == "kb_sync_docs":
            cwd = get_workspace_cwd()
            if not cwd:
                raise PluginError("No workspace cwd — bind a workspace first")
            max_files = int(arguments.get("max_files") or 400)
            return await sync_workspace_docs(
                store, cwd, workspace_id=ws, max_files=max(1, min(max_files, 2000))
            )
        if tool_name == "kb_sync_feishu":
            # Hidden/advanced — also available via REST; keep tool optional
            connector = FeishuWikiConnector(
                space_id=str(arguments.get("space_id") or ""),
                enabled=bool(arguments.get("enabled")),
            )
            return await connector.sync_into(store, workspace_id=ws)
        raise PluginError(f"unknown knowledge tool: {tool_name}")

    async def _kb_add(
        self, store: KnowledgeStore, arguments: Dict[str, Any], workspace_id: str
    ) -> Any:
        path_arg = str(arguments.get("path") or "").strip()
        title = str(arguments.get("title") or "").strip()
        content = str(arguments.get("content") or "")
        tags = str(arguments.get("tags") or "")
        source = str(arguments.get("source") or "")
        doc_id = str(arguments.get("doc_id") or "").strip()
        source_uri = ""

        if path_arg:
            cwd = get_workspace_cwd()
            if not cwd:
                raise PluginError("path requires a bound workspace cwd")
            root = Path(cwd).resolve()
            target = (root / path_arg).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise PluginError("path escapes workspace") from exc
            if not target.is_file():
                raise PluginError(f"file not found: {path_arg}")
            raw = target.read_text(encoding="utf-8", errors="replace")
            rel = target.relative_to(root).as_posix()
            content = raw
            if not title:
                title = target.stem
            source = f"file:{rel}"
            source_uri = rel
            if not doc_id:
                doc_id = stable_doc_id_for_path(rel)
            if not tags:
                tags = "file,markdown" if target.suffix.lower() == ".md" else "file"

        if not content and not path_arg:
            raise PluginError("content or path required")
        if not title:
            title = doc_id or "untitled"
        if not doc_id:
            doc_id = f"kb_{uuid4().hex[:12]}"

        return await store.upsert(
            doc_id=doc_id,
            title=title,
            content=content,
            tags=tags,
            source=source,
            source_uri=source_uri,
            workspace_id=workspace_id,
            content_hash_value=content_hash(content),
        )


def knowledge_tools_manifest() -> PluginManifest:
    return PluginManifest(
        plugin_id="builtin.knowledge",
        name="Knowledge Base",
        kind="inprocess",
        version="0.2.0",
        description=(
            "Local SQLite knowledge base with chunked keyword search "
            "and optional OpenAI-compatible embeddings hybrid."
        ),
        enabled=True,
        tools=list(TOOLS),
        config={},
    )
