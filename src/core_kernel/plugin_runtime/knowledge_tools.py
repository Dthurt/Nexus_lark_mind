"""Builtin knowledge-base tools — chunked SQLite search + optional hybrid embeddings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.common.errors import PluginError
from src.core_kernel.plugin_runtime.invoke_context import get_workspace_cwd, get_workspace_meta
from src.core_kernel.plugin_runtime.knowledge_ingest import (
    default_tags_for_path,
    read_file_as_text,
)
from src.core_kernel.plugin_runtime.knowledge_store import (
    KnowledgeStore,
    citations_markdown,
    content_hash,
)
from src.core_kernel.plugin_runtime.knowledge_sync import (
    FeishuWikiConnector,
    is_real_remote_id,
    lookup_weknora_remote_id,
    record_weknora_push_identity,
    stable_doc_id_for_path,
    sync_weknora_bidirectional,
    sync_workspace_docs,
)
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest
from src.infrastructure.storage.database import get_session_factory

WEKNORA_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "weknora_list_kbs",
        "description": (
            "List available WeKnora knowledge bases (id, name, doc counts). "
            "Use before weknora_search / weknora_push when multiple KBs exist."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 50}},
        },
    },
    {
        "name": "weknora_search",
        "description": (
            "Search a remote WeKnora knowledge base when WEKNORA_BASE_URL is set. "
            "If this session is bound to a WeKnora KB, that kb_id is used even when omitted. "
            "Do not pick the first listed KB. Prefer local kb_search when the session is on "
            "the local SQLite KB. After search, weknora_read the best doc_id/knowledge_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
                "kb_id": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "weknora_push",
        "description": (
            "Push a document (title+content) or a local kb doc_id into a WeKnora KB "
            "for long-term team sharing. Requires WEKNORA_BASE_URL and a kb_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "doc_id": {
                    "type": "string",
                    "description": "Local KB doc_id to push (alternative to title+content)",
                },
                "kb_id": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "weknora_sync",
        "description": (
            "Bidirectional sync between local SQLite KB and WeKnora. "
            "direction=push|pull|both (default both). Uses content_hash to skip unchanged docs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "push | pull | both",
                    "default": "both",
                },
                "kb_id": {"type": "string"},
                "limit": {"type": "integer", "default": 40},
                "doc_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional local doc_ids for push-only subset",
                },
            },
        },
    },
    {
        "name": "weknora_health",
        "description": "Check WeKnora connectivity, latency, and default KB configuration.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "weknora_read",
        "description": (
            "Read the full remote WeKnora knowledge body by knowledge_id "
            "(use weknora_search doc_id / knowledge_id). Prefer after weknora_search; "
            "do not invent from snippets."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {"type": "string"},
                "doc_id": {
                    "type": "string",
                    "description": "Alias for knowledge_id (weknora_search hit)",
                },
            },
        },
    },
]

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "kb_add",
        "description": (
            "Add or update a document in the local knowledge base (SQLite). "
            "Pass title+content, or path (workspace-relative) to ingest a file "
            "(.md/.txt/.rst/.pdf → source=file:...). Use for notes, specs, decisions."
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
            "Returns ranked hits with stable doc_id, chunk_id, citation, and snippets, "
            "plus citations_md for the reply. Always follow with kb_read before answering "
            "from KB content; cite source paths from citation / citations_md."
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
            "or a chunk plus neighbors (chunk_index + neighbors). Prefer after kb_search. "
            "Response includes citation provenance."
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
            "Scan workspace docs (docs/** and shallow *.md/*.txt/*.rst/*.pdf, plus images "
            "when WeMM/KB embeddings are multimodal) into the knowledge base with "
            "content_hash upsert. Use when the user asks to index project docs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_files": {"type": "integer", "default": 400},
            },
        },
    },
    {
        "name": "kb_stats",
        "description": (
            "Knowledge-base stats: doc/chunk counts and whether hybrid embeddings are ready."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "kb_reindex",
        "description": (
            "Re-embed chunks missing vectors when KB_EMBEDDING_BASE_URL or WEMM_BASE_URL "
            "is configured. No-op / error if embeddings are not configured."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 200}},
        },
    },
]

TOOLS = TOOLS + WEKNORA_TOOLS


def _session_bound_weknora_kb(arguments: Dict[str, Any], meta: Dict[str, Any]) -> str:
    """Bound session KB wins so the model cannot search a different / first KB."""
    session_kb = str(meta.get("weknora_kb_id") or "").strip()
    if session_kb:
        return session_kb
    return str(arguments.get("kb_id") or "").strip()


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
            return {
                "ok": True,
                "query": q,
                "results": hits,
                "citations_md": citations_markdown(hits),
            }
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
            from src.core_kernel.plugin_runtime.knowledge_store import format_citation

            row["citation"] = format_citation(
                title=str(row.get("title") or ""),
                source=str(row.get("source") or ""),
                source_uri=str(row.get("source_uri") or ""),
                doc_id=doc_id,
                chunk_index=row.get("chunk_index") if chunk_index is not None else None,
            )
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
        if tool_name == "kb_stats":
            return {"ok": True, **(await store.stats(workspace_id=ws))}
        if tool_name == "kb_reindex":
            limit = int(arguments.get("limit") or 200)
            return await store.reindex_embeddings(
                workspace_id=ws, limit=max(1, min(limit, 500))
            )
        if tool_name == "kb_sync_feishu":
            connector = FeishuWikiConnector(
                space_id=str(arguments.get("space_id") or ""),
                enabled=bool(arguments.get("enabled")),
            )
            return await connector.sync_into(store, workspace_id=ws)
        if tool_name == "weknora_list_kbs":
            from src.core_kernel.plugin_runtime.weknora_client import weknora_list_knowledge_bases

            return await weknora_list_knowledge_bases(
                limit=int(arguments.get("limit") or 50)
            )
        if tool_name == "weknora_health":
            from src.core_kernel.plugin_runtime.weknora_client import weknora_health

            return await weknora_health()
        if tool_name == "weknora_search":
            from src.core_kernel.plugin_runtime.weknora_client import weknora_search

            q = str(arguments.get("query") or "").strip()
            if not q:
                raise PluginError("query required")
            bound = _session_bound_weknora_kb(arguments, meta)
            return await weknora_search(
                q,
                limit=int(arguments.get("limit") or 5),
                kb_id=bound,
                workspace_id=ws if bound else "",
                session_kb_id=str(meta.get("weknora_kb_id") or ""),
            )
        if tool_name == "weknora_push":
            return await self._weknora_push(store, arguments, ws, meta)
        if tool_name == "weknora_sync":
            doc_ids = arguments.get("doc_ids")
            ids = [str(x) for x in doc_ids] if isinstance(doc_ids, list) else None
            kb = _session_bound_weknora_kb(arguments, meta)
            return await sync_weknora_bidirectional(
                store,
                workspace_id=ws,
                kb_id=kb,
                direction=str(arguments.get("direction") or "both"),
                limit=int(arguments.get("limit") or 40),
                doc_ids=ids,
            )
        if tool_name == "weknora_read":
            from src.core_kernel.plugin_runtime.weknora_client import weknora_get_knowledge

            kid = str(
                arguments.get("knowledge_id") or arguments.get("doc_id") or ""
            ).strip()
            if not kid:
                raise PluginError("knowledge_id required")
            return await weknora_get_knowledge(kid)
        raise PluginError(f"unknown knowledge tool: {tool_name}")

    async def _weknora_push(
        self,
        store: KnowledgeStore,
        arguments: Dict[str, Any],
        workspace_id: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Any:
        from src.core_kernel.plugin_runtime.weknora_client import (
            weknora_push_document,
            weknora_update_document,
        )

        meta = meta or {}
        doc_id = str(arguments.get("doc_id") or "").strip()
        title = str(arguments.get("title") or "").strip()
        content = str(arguments.get("content") or "")
        kb_id = _session_bound_weknora_kb(arguments, meta)
        session_kb = str(meta.get("weknora_kb_id") or "")
        nlm_source = ""
        if doc_id:
            row = await store.get(doc_id)
            if not row:
                raise PluginError(f"doc not found: {doc_id}")
            title = title or str(row.get("title") or doc_id)
            content = content or str(row.get("content") or "")
            digest = str(row.get("content_hash") or content_hash(content))
            nlm_source = str(row.get("source") or "")
        else:
            if not content.strip():
                raise PluginError("content or doc_id required")
            if not title:
                title = "untitled"
            digest = content_hash(content)
            by_hash = await store.find_by_content_hash(digest, workspace_id=workspace_id)
            if by_hash and by_hash.get("doc_id"):
                doc_id = str(by_hash["doc_id"])
            else:
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
        known = await lookup_weknora_remote_id(
            store,
            kb_id=kb_id or session_kb,
            local_doc_id=doc_id,
            workspace_id=workspace_id,
        )
        push_meta = {
            "nlm_doc_id": doc_id,
            "nlm_source": nlm_source,
            "content_hash": digest,
        }
        if is_real_remote_id(known):
            result = await weknora_update_document(
                knowledge_id=known,
                title=title,
                content=content,
                kb_id=kb_id,
                workspace_id=workspace_id,
                session_kb_id=session_kb,
                metadata=push_meta,
            )
            if not (result.get("ok") and (result.get("updated") or result.get("pushed"))):
                return {
                    **result,
                    "doc_id": doc_id,
                    "skipped": True,
                    "reason": "refused append-only POST; update failed",
                }
        elif known.startswith("titlehash:"):
            return {
                "ok": True,
                "skipped": True,
                "pushed": False,
                "reason": "refused append-only POST (remote id unknown; title/hash fallback only)",
                "doc_id": doc_id,
            }
        else:
            result = await weknora_push_document(
                title=title,
                content=content,
                kb_id=kb_id,
                workspace_id=workspace_id,
                session_kb_id=session_kb,
                metadata=push_meta,
            )
        if result.get("ok") and result.get("pushed"):
            await record_weknora_push_identity(
                store,
                kb_id=str(result.get("kb_id") or kb_id),
                local_doc_id=doc_id,
                remote_id=str(result.get("knowledge_id") or known or ""),
                digest=digest,
                workspace_id=workspace_id,
                title=title,
                message=f"pushed knowledge_id={result.get('knowledge_id') or known or ''}",
            )
        return {**result, "doc_id": doc_id}

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
            try:
                raw, note = read_file_as_text(target)
            except ValueError as exc:
                raise PluginError(str(exc)) from exc
            rel = target.relative_to(root).as_posix()
            content = raw
            if not title:
                title = target.stem
            source = f"file:{rel}"
            source_uri = rel
            if not doc_id:
                doc_id = stable_doc_id_for_path(rel)
            if not tags:
                tags = default_tags_for_path(target)
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
            if note:
                row = {**row, "ingest_note": note}
            return row

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
        version="0.4.0",
        description=(
            "Local SQLite knowledge base with chunked keyword search, citations, "
            "workspace ingest, optional embeddings hybrid, and WeKnora bidirectional bridge."
        ),
        enabled=True,
        tools=list(TOOLS),
        config={},
    )
