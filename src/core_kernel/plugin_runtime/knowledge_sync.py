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
                "Feishu wiki sync not implemented yet — use workspace docs sync "
                "or paste Markdown into the KB UI. TODO: wiki OpenAPI."
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
