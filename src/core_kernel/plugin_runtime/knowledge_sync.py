"""Workspace docs sync (.md/.txt/.rst + optional PDF) + Feishu connector skeleton."""

from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from src.core_kernel.plugin_runtime.knowledge_ingest import (
    default_tags_for_path,
    is_ingestible,
    read_file_as_text,
)
from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore, content_hash

logger = logging.getLogger(__name__)

_IGNORE_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".nlm",
    "web-static",
    ".pytest_cache",
    ".mypy_cache",
    ".cursor",
}

_SYNC_GLOBS = ("*.md", "*.markdown", "*.mdx", "*.txt", "*.rst", "*.org", "*.pdf")


def stable_doc_id_for_path(rel_path: str) -> str:
    digest = hashlib.sha1(rel_path.replace("\\", "/").encode("utf-8")).hexdigest()[:16]
    return f"file_{digest}"


def _should_skip_dir(name: str) -> bool:
    return name in _IGNORE_DIR_NAMES or name.startswith(".")


def iter_markdown_files(cwd: str, *, max_files: int = 400) -> List[Path]:
    """Backward-compatible alias — returns ingestible workspace docs."""
    return iter_workspace_docs(cwd, max_files=max_files)


def iter_workspace_docs(cwd: str, *, max_files: int = 400) -> List[Path]:
    root = Path(cwd).resolve()
    if not root.is_dir():
        return []
    found: List[Path] = []
    docs = root / "docs"
    candidates: List[Path] = []
    if docs.is_dir():
        for pattern in _SYNC_GLOBS:
            candidates.extend(docs.rglob(pattern))
    for pattern in _SYNC_GLOBS:
        for path in root.rglob(pattern):
            try:
                rel_parts = path.relative_to(root).parts
            except ValueError:
                continue
            if any(_should_skip_dir(p) for p in rel_parts[:-1]):
                continue
            # Skip very deep trees outside docs/
            if rel_parts and rel_parts[0] != "docs" and len(rel_parts) > 3:
                continue
            candidates.append(path)

    seen: Set[str] = set()
    for p in candidates:
        if not is_ingestible(p):
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            found.append(p)
        if len(found) >= max_files:
            break
    return found


async def sync_workspace_docs(
    store: KnowledgeStore,
    cwd: str,
    *,
    workspace_id: str = "",
    max_files: int = 400,
    max_bytes: int = 512_000,
) -> Dict[str, Any]:
    """Scan docs under cwd into KB with content_hash upsert (.md/.txt/.rst/.pdf)."""
    root = Path(cwd).resolve()
    added = 0
    updated = 0
    skipped = 0
    errors: List[str] = []
    files = iter_workspace_docs(str(root), max_files=max_files)
    for path in files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        try:
            text, note = read_file_as_text(path, max_bytes=max_bytes)
            digest = content_hash(text)
            doc_id = stable_doc_id_for_path(rel)
            title = _title_from_md(text, rel)
            tags = default_tags_for_path(path)
            if Path(rel).parts and Path(rel).parts[0] == "docs":
                tags = f"docs,{tags}" if tags else "docs"
            existing = await store.get(doc_id)
            result = await store.upsert(
                doc_id=doc_id,
                title=title,
                content=text,
                tags=tags,
                source=f"file:{rel}",
                source_uri=rel,
                workspace_id=workspace_id,
                content_hash_value=digest,
                skip_if_unchanged=True,
            )
            if result.get("unchanged"):
                skipped += 1
                status = "skip"
                msg = "unchanged" + (f" ({note})" if note else "")
            elif existing:
                updated += 1
                status = "ok"
                msg = "updated" + (f" ({note})" if note else "")
            else:
                added += 1
                status = "ok"
                msg = "added" + (f" ({note})" if note else "")
            await store.log_sync(
                source="workspace_docs",
                source_uri=rel,
                content_hash_value=digest,
                status=status,
                message=msg,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
            await store.log_sync(
                source="workspace_docs",
                source_uri=rel,
                status="error",
                message=str(exc),
                workspace_id=workspace_id,
            )
    return {
        "ok": True,
        "cwd": str(root),
        "scanned": len(files),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:20],
    }


def _title_from_md(text: str, fallback: str) -> str:
    for line in (text or "").splitlines()[:40]:
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()[:200]
    name = Path(fallback).stem.replace("_", " ").replace("-", " ")
    return name[:200] or fallback


class KnowledgeConnector(ABC):
    """Incremental sync connector (source + source_uri + content_hash)."""

    name: str = "base"

    @abstractmethod
    async def fetch_candidates(self) -> Iterable[Dict[str, Any]]:
        """Yield dicts with keys: source_uri, title, content, content_hash?."""

    async def sync_into(
        self,
        store: KnowledgeStore,
        *,
        workspace_id: str = "",
    ) -> Dict[str, Any]:
        added = updated = skipped = 0
        errors: List[str] = []
        for item in await self._as_list(await self.fetch_candidates()):
            uri = str(item.get("source_uri") or "").strip()
            body = str(item.get("content") or "")
            title = str(item.get("title") or uri or self.name)
            digest = str(item.get("content_hash") or content_hash(body))
            doc_id = str(item.get("doc_id") or f"{self.name}_{hashlib.sha1(uri.encode()).hexdigest()[:12]}")
            try:
                existing = await store.get(doc_id)
                result = await store.upsert(
                    doc_id=doc_id,
                    title=title,
                    content=body,
                    tags=str(item.get("tags") or self.name),
                    source=f"{self.name}:{uri}" if uri else self.name,
                    source_uri=uri,
                    workspace_id=workspace_id,
                    content_hash_value=digest,
                    skip_if_unchanged=True,
                )
                if result.get("unchanged"):
                    skipped += 1
                    status, msg = "skip", "unchanged"
                elif existing:
                    updated += 1
                    status, msg = "ok", "updated"
                else:
                    added += 1
                    status, msg = "ok", "added"
                await store.log_sync(
                    source=self.name,
                    source_uri=uri,
                    content_hash_value=digest,
                    status=status,
                    message=msg,
                    workspace_id=workspace_id,
                )
            except Exception as exc:
                errors.append(f"{uri}: {exc}")
                await store.log_sync(
                    source=self.name,
                    source_uri=uri,
                    status="error",
                    message=str(exc),
                    workspace_id=workspace_id,
                )
        return {
            "ok": True,
            "source": self.name,
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "errors": errors[:20],
        }

    @staticmethod
    async def _as_list(items: Any) -> List[Dict[str, Any]]:
        if items is None:
            return []
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        return [x for x in items if isinstance(x, dict)]


class FeishuWikiConnector(KnowledgeConnector):
    """Skeleton: Feishu wiki/doc sync is not implemented yet.

    Prefer manual paste / file sync first. When Feishu Doc/Wiki OpenAPI access
    is configured, implement fetch_candidates() using FeishuClient.
    Prefer WeKnora multi-source ingestion (Feishu → WeKnora → NLM) when available.
    """

    name = "feishu_wiki"

    def __init__(self, *, space_id: str = "", enabled: bool = False) -> None:
        self.space_id = space_id
        self.enabled = enabled

    async def fetch_candidates(self) -> List[Dict[str, Any]]:
        # TODO: list wiki nodes via Feishu OpenAPI, download markdown/plaintext,
        # and yield incremental {source_uri, title, content, content_hash}.
        logger.info(
            "FeishuWikiConnector stub — space_id=%s enabled=%s (no-op)",
            self.space_id,
            self.enabled,
        )
        return []

    async def sync_into(
        self,
        store: KnowledgeStore,
        *,
        workspace_id: str = "",
    ) -> Dict[str, Any]:
        await store.log_sync(
            source=self.name,
            source_uri=self.space_id or "",
            status="skip",
            message=(
                "Feishu wiki sync not implemented yet — use workspace docs sync, "
                "paste Markdown, or sync via WeKnora (weknora_sync pull) when Feishu "
                "is connected there. TODO: direct wiki OpenAPI."
            ),
            workspace_id=workspace_id,
        )
        return {
            "ok": True,
            "source": self.name,
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "todo": "Implement Feishu wiki/doc OpenAPI fetch; prefer incremental content_hash.",
        }


async def sync_local_to_weknora(
    store: KnowledgeStore,
    *,
    workspace_id: str = "",
    kb_id: str = "",
    limit: int = 40,
    doc_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Push local SQLite docs to WeKnora with content_hash skip-if-unchanged."""
    from src.core_kernel.plugin_runtime.weknora_client import (
        weknora_configured,
        weknora_default_kb_id,
        weknora_ingest_enabled,
        weknora_push_document,
    )

    if not weknora_configured():
        return {
            "ok": True,
            "skipped": True,
            "reason": "WEKNORA_BASE_URL not set",
            "pushed": 0,
            "skipped_unchanged": 0,
            "errors": [],
        }
    if not weknora_ingest_enabled():
        return {
            "ok": False,
            "error": "WeKnora ingest disabled",
            "pushed": 0,
            "skipped_unchanged": 0,
            "errors": [],
        }
    kid = (kb_id or weknora_default_kb_id()).strip()
    if not kid:
        return {
            "ok": False,
            "error": "kb_id required (pass kb_id or set WEKNORA_KB_ID)",
            "pushed": 0,
            "skipped_unchanged": 0,
            "errors": [],
        }

    pushed = skipped = 0
    errors: List[str] = []
    docs: List[Dict[str, Any]] = []
    if doc_ids:
        for did in doc_ids[:limit]:
            row = await store.get(str(did).strip())
            if row:
                docs.append(row)
    else:
        docs = await store.list_docs(workspace_id=workspace_id, limit=max(1, min(limit, 200)))

    for summary in docs:
        doc_id = str(summary.get("doc_id") or "")
        full = await store.get(doc_id) if doc_id else None
        if not full:
            continue
        title = str(full.get("title") or doc_id)
        body = str(full.get("content") or "")
        if not body.strip():
            skipped += 1
            continue
        digest = str(full.get("content_hash") or content_hash(body))
        # Skip if last successful push logged same hash for this doc
        recent = await store.list_sync_log(workspace_id=workspace_id, limit=80)
        already = any(
            e.get("source") == "weknora_push"
            and e.get("source_uri") == f"{kid}:{doc_id}"
            and e.get("content_hash") == digest
            and e.get("status") == "ok"
            for e in recent
        )
        if already:
            skipped += 1
            continue
        result = await weknora_push_document(
            title=title,
            content=body,
            kb_id=kid,
            metadata={
                "nlm_doc_id": doc_id,
                "nlm_source": str(full.get("source") or ""),
                "nlm_source_uri": str(full.get("source_uri") or ""),
                "content_hash": digest,
            },
        )
        if result.get("ok") and result.get("pushed"):
            pushed += 1
            await store.log_sync(
                source="weknora_push",
                source_uri=f"{kid}:{doc_id}",
                content_hash_value=digest,
                status="ok",
                message=f"pushed knowledge_id={result.get('knowledge_id') or ''}",
                workspace_id=workspace_id,
            )
        else:
            err = str(result.get("error") or "push failed")
            errors.append(f"{doc_id}: {err}")
            await store.log_sync(
                source="weknora_push",
                source_uri=f"{kid}:{doc_id}",
                content_hash_value=digest,
                status="error",
                message=err,
                workspace_id=workspace_id,
            )
    return {
        "ok": True,
        "direction": "local_to_weknora",
        "kb_id": kid,
        "scanned": len(docs),
        "pushed": pushed,
        "skipped_unchanged": skipped,
        "errors": errors[:20],
    }


async def sync_weknora_to_local(
    store: KnowledgeStore,
    *,
    workspace_id: str = "",
    kb_id: str = "",
    limit: int = 40,
) -> Dict[str, Any]:
    """Pull WeKnora knowledge entries into local SQLite with content_hash upsert."""
    from src.core_kernel.plugin_runtime.weknora_client import (
        weknora_configured,
        weknora_default_kb_id,
        weknora_get_knowledge,
        weknora_list_knowledge,
    )

    if not weknora_configured():
        return {
            "ok": True,
            "skipped": True,
            "reason": "WEKNORA_BASE_URL not set",
            "added": 0,
            "updated": 0,
            "skipped_unchanged": 0,
            "errors": [],
        }
    kid = (kb_id or weknora_default_kb_id()).strip()
    if not kid:
        return {
            "ok": False,
            "error": "kb_id required",
            "added": 0,
            "updated": 0,
            "skipped_unchanged": 0,
            "errors": [],
        }

    listed = await weknora_list_knowledge(kid, page=1, page_size=max(1, min(limit, 100)))
    if not listed.get("ok"):
        return {
            "ok": False,
            "error": listed.get("error") or "list failed",
            "added": 0,
            "updated": 0,
            "skipped_unchanged": 0,
            "errors": [],
            "kb_id": kid,
        }

    added = updated = skipped = 0
    errors: List[str] = []
    for item in listed.get("items") or []:
        if not isinstance(item, dict):
            continue
        remote_id = str(item.get("id") or "").strip()
        if not remote_id:
            continue
        title = str(item.get("title") or remote_id)
        body = str(item.get("content") or "")
        if not body.strip():
            detail = await weknora_get_knowledge(remote_id)
            if detail.get("ok"):
                body = str(detail.get("content") or "")
                if detail.get("title"):
                    title = str(detail["title"])
        if not body.strip():
            skipped += 1
            continue
        digest = content_hash(body)
        doc_id = f"weknora_{hashlib.sha1(f'{kid}:{remote_id}'.encode()).hexdigest()[:16]}"
        try:
            existing = await store.get(doc_id)
            result = await store.upsert(
                doc_id=doc_id,
                title=title,
                content=body,
                tags=f"weknora,{kid}",
                source=f"weknora:{kid}",
                source_uri=remote_id,
                workspace_id=workspace_id,
                content_hash_value=digest,
                skip_if_unchanged=True,
            )
            if result.get("unchanged"):
                skipped += 1
                status, msg = "skip", "unchanged"
            elif existing:
                updated += 1
                status, msg = "ok", "updated"
            else:
                added += 1
                status, msg = "ok", "added"
            await store.log_sync(
                source="weknora_pull",
                source_uri=f"{kid}:{remote_id}",
                content_hash_value=digest,
                status=status,
                message=msg,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            errors.append(f"{remote_id}: {exc}")
            await store.log_sync(
                source="weknora_pull",
                source_uri=f"{kid}:{remote_id}",
                status="error",
                message=str(exc),
                workspace_id=workspace_id,
            )
    return {
        "ok": True,
        "direction": "weknora_to_local",
        "kb_id": kid,
        "scanned": len(listed.get("items") or []),
        "added": added,
        "updated": updated,
        "skipped_unchanged": skipped,
        "errors": errors[:20],
    }


async def sync_weknora_bidirectional(
    store: KnowledgeStore,
    *,
    workspace_id: str = "",
    kb_id: str = "",
    direction: str = "both",
    limit: int = 40,
    doc_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Bidirectional sync: local ↔ WeKnora.

    direction: push | pull | both
    """
    d = (direction or "both").strip().lower()
    out: Dict[str, Any] = {"ok": True, "direction": d, "kb_id": kb_id or ""}
    if d in {"push", "both", "local_to_weknora"}:
        out["push"] = await sync_local_to_weknora(
            store,
            workspace_id=workspace_id,
            kb_id=kb_id,
            limit=limit,
            doc_ids=doc_ids,
        )
        if not out["push"].get("ok") and not out["push"].get("skipped"):
            out["ok"] = False
    if d in {"pull", "both", "weknora_to_local"}:
        out["pull"] = await sync_weknora_to_local(
            store,
            workspace_id=workspace_id,
            kb_id=kb_id,
            limit=limit,
        )
        if not out["pull"].get("ok") and not out["pull"].get("skipped"):
            out["ok"] = False
    return out
