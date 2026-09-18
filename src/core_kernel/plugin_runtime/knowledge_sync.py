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
    library_ingest_max_bytes,
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

_TEXT_GLOBS = ("*.md", "*.markdown", "*.mdx", "*.txt", "*.rst", "*.org", "*.pdf")
_IMAGE_GLOBS = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif")


def _sync_globs() -> tuple[str, ...]:
    from src.core_kernel.plugin_runtime.knowledge_embeddings import multimodal_embeddings_enabled

    if multimodal_embeddings_enabled():
        return _TEXT_GLOBS + _IMAGE_GLOBS
    return _TEXT_GLOBS


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
    globs = _sync_globs()
    if docs.is_dir():
        for pattern in globs:
            candidates.extend(docs.rglob(pattern))
    for pattern in globs:
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
    kb_id: str = "",
    max_files: int = 400,
    max_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Scan docs under cwd into the bound local KB with content_hash upsert."""
    from src.core_kernel.plugin_runtime.knowledge_scope import (
        DEFAULT_LOCAL_KB_ID,
        is_remote_kb_id,
        normalize_local_kb_id,
    )

    if is_remote_kb_id(kb_id):
        return {
            "ok": True,
            "noop": True,
            "reason": "workspace sync is local-only; refuse writing into WeKnora",
            "cwd": cwd,
            "scanned": 0,
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "kb_id": kb_id,
        }
    local_id = normalize_local_kb_id(kb_id)
    limit = library_ingest_max_bytes() if max_bytes is None else max_bytes
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
            text, note = read_file_as_text(path, max_bytes=limit)
            digest = content_hash(text)
            id_key = rel if local_id == DEFAULT_LOCAL_KB_ID else f"{local_id}:{rel}"
            doc_id = stable_doc_id_for_path(id_key)
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
                kb_id=local_id,
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
        "kb_id": local_id,
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


def weknora_mint_doc_id(kb_id: str, remote_id: str) -> str:
    digest = hashlib.sha1(f"{kb_id}:{remote_id}".encode("utf-8")).hexdigest()[:16]
    return f"weknora_{digest}"


def weknora_titlehash_key(title: str, digest: str) -> str:
    """Stable fallback remote key when WeKnora omits knowledge_id."""
    raw = f"{(title or '').strip()}|{(digest or '').strip()}"
    return "titlehash:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_real_remote_id(remote_id: str) -> bool:
    rid = (remote_id or "").strip()
    return bool(rid) and not rid.startswith("titlehash:")


def extract_remote_identity(item: Dict[str, Any]) -> tuple[str, str]:
    """Read nlm_doc_id / content_hash from a WeKnora list/get row."""
    meta: Any = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if not meta and isinstance(item.get("meta"), dict):
        meta = item["meta"]
    nlm_id = str(meta.get("nlm_doc_id") or item.get("nlm_doc_id") or "").strip()
    digest = str(meta.get("content_hash") or item.get("content_hash") or "").strip()
    return nlm_id, digest


def _idmap_remote_from_uri(kb_id: str, source_uri: str) -> str:
    kid = (kb_id or "").strip()
    uri = (source_uri or "").strip()
    prefix = f"{kid}:" if kid else ""
    if prefix and uri.startswith(prefix):
        return uri[len(prefix) :]
    if ":" in uri:
        return uri.split(":", 1)[1]
    return uri


async def record_weknora_push_identity(
    store: KnowledgeStore,
    *,
    kb_id: str,
    local_doc_id: str,
    remote_id: str = "",
    digest: str = "",
    workspace_id: str = "",
    message: str = "",
    title: str = "",
    record_push_log: bool = True,
) -> None:
    """Log push + reverse idmap so pull collapses onto the same local doc.

    When WeKnora omits ``knowledge_id``, still persist a title/hash fallback key.
    """
    kid = (kb_id or "").strip()
    doc_id = (local_doc_id or "").strip()
    if record_push_log and kid and doc_id:
        await store.log_sync(
            source="weknora_push",
            source_uri=f"{kid}:{doc_id}",
            content_hash_value=digest,
            status="ok",
            message=message or (f"pushed knowledge_id={remote_id}" if remote_id else "pushed"),
            workspace_id=workspace_id,
        )
    remote = (remote_id or "").strip()
    if kid and doc_id and is_real_remote_id(remote):
        await store.log_sync(
            source="weknora_idmap",
            source_uri=f"{kid}:{remote}",
            content_hash_value=digest,
            status="ok",
            message=doc_id,
            workspace_id=workspace_id,
        )
    fallback = weknora_titlehash_key(title, digest) if (title or digest) else ""
    if kid and doc_id and fallback:
        await store.log_sync(
            source="weknora_idmap",
            source_uri=f"{kid}:{fallback}",
            content_hash_value=digest,
            status="ok",
            message=doc_id,
            workspace_id=workspace_id,
        )


async def lookup_weknora_remote_id(
    store: KnowledgeStore,
    *,
    kb_id: str,
    local_doc_id: str,
    workspace_id: str = "",
) -> str:
    """Return a previously recorded remote id for this local doc (prefer real ids)."""
    kid = (kb_id or "").strip()
    doc_id = (local_doc_id or "").strip()
    if not kid or not doc_id:
        return ""
    uri = await store.find_sync_uri_by_message(
        source="weknora_idmap",
        message=doc_id,
        workspace_id=workspace_id,
        status="ok",
        source_uri_prefix=f"{kid}:",
    )
    return _idmap_remote_from_uri(kid, uri or "")


async def last_known_weknora_hash(
    store: KnowledgeStore,
    *,
    kb_id: str,
    local_doc_id: str,
    remote_id: str = "",
    workspace_id: str = "",
    title: str = "",
    digest: str = "",
) -> Optional[str]:
    """Newest pull/push/idmap hash for this local↔remote pair."""
    kid = (kb_id or "").strip()
    doc_id = (local_doc_id or "").strip()
    rid = (remote_id or "").strip()
    hashes: List[Optional[str]] = []
    if kid and doc_id:
        hashes.append(
            await store.latest_sync_hash(
                source="weknora_push",
                source_uri=f"{kid}:{doc_id}",
                workspace_id=workspace_id,
                status="ok",
            )
        )
    if kid and rid:
        hashes.append(
            await store.latest_sync_hash(
                source="weknora_pull",
                source_uri=f"{kid}:{rid}",
                workspace_id=workspace_id,
                status="ok",
            )
        )
        hashes.append(
            await store.latest_sync_hash(
                source="weknora_import",
                source_uri=f"{kid}:{rid}",
                workspace_id=workspace_id,
                status="ok",
            )
        )
        hashes.append(
            await store.latest_sync_hash(
                source="weknora_idmap",
                source_uri=f"{kid}:{rid}",
                workspace_id=workspace_id,
                status="ok",
            )
        )
    fallback = weknora_titlehash_key(title, digest) if (title or digest) else ""
    if kid and fallback:
        hashes.append(
            await store.latest_sync_hash(
                source="weknora_idmap",
                source_uri=f"{kid}:{fallback}",
                workspace_id=workspace_id,
                status="ok",
            )
        )
    for h in hashes:
        if h:
            return h
    return None


async def resolve_local_doc_id_for_remote(
    store: KnowledgeStore,
    *,
    kb_id: str,
    remote_id: str,
    workspace_id: str = "",
    nlm_doc_id: str = "",
    digest: str = "",
    title: str = "",
) -> tuple[str, str]:
    """Map a remote WeKnora entry onto an existing local doc when possible.

    Returns (doc_id, reason) where reason is
    nlm_doc_id|idmap|titlehash|content_hash|source_uri|minted.
    """
    kid = (kb_id or "").strip()
    rid = (remote_id or "").strip()
    explicit = (nlm_doc_id or "").strip()
    if explicit:
        existing = await store.get(explicit)
        if existing:
            return explicit, "nlm_doc_id"

    if kid and rid:
        mapped = await store.latest_sync_message(
            source="weknora_idmap",
            source_uri=f"{kid}:{rid}",
            workspace_id=workspace_id,
            status="ok",
        )
        mapped_id = (mapped or "").strip()
        if mapped_id:
            existing = await store.get(mapped_id)
            if existing:
                return mapped_id, "idmap"

    fallback = weknora_titlehash_key(title, digest) if (title or digest) else ""
    if kid and fallback:
        mapped = await store.latest_sync_message(
            source="weknora_idmap",
            source_uri=f"{kid}:{fallback}",
            workspace_id=workspace_id,
            status="ok",
        )
        mapped_id = (mapped or "").strip()
        if mapped_id:
            existing = await store.get(mapped_id)
            if existing:
                return mapped_id, "titlehash"

    if digest:
        by_hash = await store.find_by_content_hash(digest, workspace_id=workspace_id)
        if by_hash and by_hash.get("doc_id"):
            return str(by_hash["doc_id"]), "content_hash"

    if rid and is_real_remote_id(rid):
        by_uri = await store.find_by_source_uri(rid, workspace_id=workspace_id)
        if by_uri and by_uri.get("doc_id"):
            return str(by_uri["doc_id"]), "source_uri"

    mint_key = rid or fallback or digest or title or "unknown"
    return weknora_mint_doc_id(kid, mint_key), "minted"


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
        resolve_weknora_kb_id,
        weknora_configured,
        weknora_ingest_enabled,
        weknora_push_document,
        weknora_update_document,
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
    kid = resolve_weknora_kb_id(kb_id=kb_id, workspace_id=workspace_id).strip()
    if not kid:
        return {
            "ok": False,
            "error": "kb_id required (pass kb_id or set WEKNORA_KB_ID / WEKNORA_KB_MAP)",
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
        # Skip if last successful push for this doc already recorded the same hash
        prev_hash = await store.latest_sync_hash(
            source="weknora_push",
            source_uri=f"{kid}:{doc_id}",
            workspace_id=workspace_id,
            status="ok",
        )
        if prev_hash is not None and prev_hash == digest:
            skipped += 1
            continue
        known_remote = await lookup_weknora_remote_id(
            store, kb_id=kid, local_doc_id=doc_id, workspace_id=workspace_id
        )
        meta = {
            "nlm_doc_id": doc_id,
            "nlm_source": str(full.get("source") or ""),
            "nlm_source_uri": str(full.get("source_uri") or ""),
            "content_hash": digest,
        }
        if is_real_remote_id(known_remote):
            result = await weknora_update_document(
                knowledge_id=known_remote,
                title=title,
                content=body,
                kb_id=kid,
                metadata=meta,
            )
            if not (result.get("ok") and (result.get("updated") or result.get("pushed"))):
                skipped += 1
                err = str(result.get("error") or "update skipped")
                await store.log_sync(
                    source="weknora_push",
                    source_uri=f"{kid}:{doc_id}",
                    content_hash_value=digest,
                    status="skip",
                    message=f"refused append-only POST; update failed: {err}",
                    workspace_id=workspace_id,
                )
                continue
        elif known_remote.startswith("titlehash:"):
            skipped += 1
            await store.log_sync(
                source="weknora_push",
                source_uri=f"{kid}:{doc_id}",
                content_hash_value=digest,
                status="skip",
                message="refused append-only POST (remote id unknown; title/hash fallback only)",
                workspace_id=workspace_id,
            )
            continue
        else:
            result = await weknora_push_document(
                title=title,
                content=body,
                kb_id=kid,
                metadata=meta,
            )
        if result.get("ok") and result.get("pushed"):
            pushed += 1
            await record_weknora_push_identity(
                store,
                kb_id=kid,
                local_doc_id=doc_id,
                remote_id=str(result.get("knowledge_id") or known_remote or ""),
                digest=digest,
                workspace_id=workspace_id,
                title=title,
                message=f"pushed knowledge_id={result.get('knowledge_id') or known_remote or ''}",
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
        resolve_weknora_kb_id,
        weknora_configured,
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
    kid = resolve_weknora_kb_id(kb_id=kb_id, workspace_id=workspace_id).strip()
    if not kid:
        return {
            "ok": False,
            "error": "kb_id required (pass kb_id or set WEKNORA_KB_ID / WEKNORA_KB_MAP)",
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

    added = updated = skipped = collapsed = conflicts = 0
    errors: List[str] = []
    conflicted: List[str] = []
    for item in listed.get("items") or []:
        if not isinstance(item, dict):
            continue
        remote_id = str(item.get("id") or item.get("knowledge_id") or "").strip()
        title = str(item.get("title") or remote_id or "")
        body = str(item.get("content") or "")
        nlm_id, meta_hash = extract_remote_identity(item)
        if not body.strip() and is_real_remote_id(remote_id):
            detail = await weknora_get_knowledge(remote_id)
            if detail.get("ok"):
                body = str(detail.get("content") or "")
                if detail.get("title"):
                    title = str(detail["title"])
                extra_id, extra_hash = extract_remote_identity(detail)
                nlm_id = nlm_id or extra_id
                meta_hash = meta_hash or extra_hash
                if not remote_id:
                    remote_id = str(detail.get("id") or "")
        if not body.strip():
            skipped += 1
            continue
        digest = content_hash(body) or meta_hash
        if not remote_id:
            remote_id = weknora_titlehash_key(title, digest)
        doc_id, reason = await resolve_local_doc_id_for_remote(
            store,
            kb_id=kid,
            remote_id=remote_id,
            workspace_id=workspace_id,
            nlm_doc_id=nlm_id,
            digest=digest,
            title=title,
        )
        try:
            existing = await store.get(doc_id)
            keep_local = bool(existing) and reason != "minted"
            if existing:
                local_hash = str(existing.get("content_hash") or content_hash(str(existing.get("content") or "")))
                last_known = await last_known_weknora_hash(
                    store,
                    kb_id=kid,
                    local_doc_id=doc_id,
                    remote_id=remote_id,
                    workspace_id=workspace_id,
                    title=title,
                    digest=digest,
                )
                if last_known and local_hash != last_known and local_hash != digest:
                    conflicts += 1
                    conflicted.append(doc_id)
                    skipped += 1
                    await store.log_sync(
                        source="weknora_pull",
                        source_uri=f"{kid}:{remote_id}",
                        content_hash_value=digest,
                        status="conflict",
                        message=f"dirty local skipped ({reason})",
                        workspace_id=workspace_id,
                    )
                    if kid and remote_id:
                        await store.log_sync(
                            source="weknora_idmap",
                            source_uri=f"{kid}:{remote_id}",
                            content_hash_value=local_hash,
                            status="ok",
                            message=doc_id,
                            workspace_id=workspace_id,
                        )
                    continue
            tags = str(existing.get("tags") or "") if existing else f"weknora,{kid}"
            if "weknora" not in {t.strip() for t in (tags or "").split(",") if t.strip()}:
                tags = f"{tags},weknora" if tags else f"weknora,{kid}"
            source = (
                str(existing.get("source") or "")
                if keep_local
                else f"weknora:{kid}"
            )
            source_uri = (
                str(existing.get("source_uri") or "")
                if keep_local and existing.get("source_uri")
                else (remote_id if is_real_remote_id(remote_id) else str(existing.get("source_uri") or "") if existing else "")
            )
            result = await store.upsert(
                doc_id=doc_id,
                title=str(existing.get("title") or title) if keep_local else title,
                content=body,
                tags=tags,
                source=source,
                source_uri=source_uri,
                workspace_id=workspace_id or str((existing or {}).get("workspace_id") or ""),
                content_hash_value=digest,
                skip_if_unchanged=True,
            )
            if result.get("unchanged"):
                skipped += 1
                status, msg = "skip", f"unchanged ({reason})"
            elif existing:
                updated += 1
                status, msg = "ok", f"updated ({reason})"
            else:
                added += 1
                status, msg = "ok", f"added ({reason})"
            if reason != "minted":
                collapsed += 1
            await store.log_sync(
                source="weknora_pull",
                source_uri=f"{kid}:{remote_id}",
                content_hash_value=digest,
                status=status,
                message=msg,
                workspace_id=workspace_id,
            )
            await store.log_sync(
                source="weknora_idmap",
                source_uri=f"{kid}:{remote_id}",
                content_hash_value=digest,
                status="ok",
                message=doc_id,
                workspace_id=workspace_id,
            )
            fallback = weknora_titlehash_key(title, digest)
            if fallback != remote_id:
                await store.log_sync(
                    source="weknora_idmap",
                    source_uri=f"{kid}:{fallback}",
                    content_hash_value=digest,
                    status="ok",
                    message=doc_id,
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
        "collapsed": collapsed,
        "conflicts": conflicts,
        "conflicted": conflicted[:20],
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


async def import_weknora_knowledge(
    store: KnowledgeStore,
    *,
    knowledge_id: str,
    workspace_id: str = "",
    kb_id: str = "",
) -> Dict[str, Any]:
    """Import one remote WeKnora doc into local SQLite (browse-first, no remote edit)."""
    from src.core_kernel.plugin_runtime.weknora_client import (
        resolve_weknora_kb_id,
        weknora_configured,
        weknora_get_knowledge,
    )

    rid = (knowledge_id or "").strip()
    if not rid:
        return {"ok": False, "error": "knowledge_id required", "imported": False}
    if not weknora_configured():
        return {
            "ok": True,
            "skipped": True,
            "reason": "WEKNORA_BASE_URL not set",
            "imported": False,
        }
    kid = resolve_weknora_kb_id(kb_id=kb_id, workspace_id=workspace_id).strip()
    detail = await weknora_get_knowledge(rid)
    if not detail.get("ok"):
        return {
            "ok": False,
            "error": detail.get("error") or "get failed",
            "imported": False,
            "knowledge_id": rid,
        }
    title = str(detail.get("title") or rid)
    body = str(detail.get("content") or "")
    if not body.strip():
        return {"ok": False, "error": "remote document has no content", "imported": False}
    nlm_id, meta_hash = extract_remote_identity(detail)
    digest = content_hash(body) or meta_hash
    remote_id = str(detail.get("id") or rid)
    doc_id, reason = await resolve_local_doc_id_for_remote(
        store,
        kb_id=kid,
        remote_id=remote_id,
        workspace_id=workspace_id,
        nlm_doc_id=nlm_id,
        digest=digest,
        title=title,
    )
    existing = await store.get(doc_id)
    if existing:
        local_hash = str(existing.get("content_hash") or content_hash(str(existing.get("content") or "")))
        last_known = await last_known_weknora_hash(
            store,
            kb_id=kid,
            local_doc_id=doc_id,
            remote_id=remote_id,
            workspace_id=workspace_id,
            title=title,
            digest=digest,
        )
        if last_known and local_hash != last_known and local_hash != digest:
            return {
                "ok": True,
                "imported": False,
                "conflict": True,
                "doc_id": doc_id,
                "reason": "dirty local",
                "knowledge_id": remote_id,
            }
        if local_hash == digest:
            return {
                "ok": True,
                "imported": False,
                "unchanged": True,
                "doc_id": doc_id,
                "reason": reason,
                "knowledge_id": remote_id,
            }
    keep_local = bool(existing) and reason != "minted"
    tags = str(existing.get("tags") or "") if existing else f"weknora,{kid}"
    if "weknora" not in {t.strip() for t in (tags or "").split(",") if t.strip()}:
        tags = f"{tags},weknora" if tags else f"weknora,{kid}"
    row = await store.upsert(
        doc_id=doc_id,
        title=str(existing.get("title") or title) if keep_local else title,
        content=body,
        tags=tags,
        source=str(existing.get("source") or "") if keep_local else f"weknora:{kid}",
        source_uri=(
            str(existing.get("source_uri") or "")
            if keep_local and existing.get("source_uri")
            else remote_id
        ),
        workspace_id=workspace_id or str((existing or {}).get("workspace_id") or ""),
        content_hash_value=digest,
        skip_if_unchanged=True,
    )
    await store.log_sync(
        source="weknora_import",
        source_uri=f"{kid}:{remote_id}",
        content_hash_value=digest,
        status="ok",
        message=f"imported ({reason})",
        workspace_id=workspace_id,
    )
    await record_weknora_push_identity(
        store,
        kb_id=kid,
        local_doc_id=doc_id,
        remote_id=remote_id,
        digest=digest,
        workspace_id=workspace_id,
        title=title,
        message=f"imported knowledge_id={remote_id}",
        record_push_log=False,
    )
    return {
        "ok": True,
        "imported": not row.get("unchanged"),
        "unchanged": bool(row.get("unchanged")),
        "doc_id": doc_id,
        "reason": reason,
        "knowledge_id": remote_id,
        "title": title,
        "kb_id": kid,
    }
