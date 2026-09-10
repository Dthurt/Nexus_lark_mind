"""Builtin knowledge-base tools — SQLite text search (no vectors)."""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from src.common.errors import PluginError
from src.core_kernel.plugin_runtime.invoke_context import get_workspace_meta
from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest
from src.infrastructure.storage.database import get_session_factory

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "kb_add",
        "description": (
            "Add or update a document in the local knowledge base (SQLite). "
            "Use for notes, specs, decisions, or pasted reference text the user wants recalled later."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "tags": {"type": "string", "description": "Comma-separated tags"},
                "doc_id": {"type": "string", "description": "Optional id; omit to create new"},
                "source": {"type": "string"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "kb_search",
        "description": (
            "Search the local knowledge base with keyword / approximate token matching "
            "(not vector embeddings). Returns ranked snippets."
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
        "name": "kb_get",
        "description": "Fetch a knowledge-base document by doc_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
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
            doc_id = str(arguments.get("doc_id") or f"kb_{uuid4().hex[:12]}")
            return await store.upsert(
                doc_id=doc_id,
                title=str(arguments.get("title") or ""),
                content=str(arguments.get("content") or ""),
                tags=str(arguments.get("tags") or ""),
                source=str(arguments.get("source") or ""),
                workspace_id=ws,
            )
        if tool_name == "kb_search":
            q = str(arguments.get("query") or "").strip()
            if not q:
                raise PluginError("query required")
            limit = int(arguments.get("limit") or 6)
            hits = await store.search(q, workspace_id=ws, limit=max(1, min(limit, 20)))
            return {"ok": True, "query": q, "results": hits}
        if tool_name == "kb_get":
            doc_id = str(arguments.get("doc_id") or "").strip()
            row = await store.get(doc_id)
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
        raise PluginError(f"unknown knowledge tool: {tool_name}")


def knowledge_tools_manifest() -> PluginManifest:
    return PluginManifest(
        plugin_id="builtin.knowledge",
        name="Knowledge Base",
        kind="inprocess",
        version="0.1.0",
        description="Local SQLite knowledge base with keyword / approximate search (no vectors).",
        enabled=True,
        tools=list(TOOLS),
        config={},
    )
