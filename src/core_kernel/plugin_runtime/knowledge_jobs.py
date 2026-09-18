"""Async local ingest jobs: file / folder / URL → parse → SQLite upsert."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core_kernel.plugin_runtime.knowledge_ingest import (
    SUPPORTED_SUFFIXES,
    default_tags_for_name,
    html_to_text,
    library_ingest_max_bytes,
    read_bytes_as_text,
)
from src.core_kernel.plugin_runtime.knowledge_scope import normalize_local_kb_id
from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore, content_hash
from src.core_kernel.plugin_runtime.knowledge_url import fetch_ingest_url, suffix_for_url

logger = logging.getLogger(__name__)

INGEST_ROOT = Path("data") / "kb_ingest"
_running: set[str] = set()


def ingest_sync() -> bool:
    return (os.getenv("KB_INGEST_SYNC") or "").strip().lower() in {"1", "true", "yes", "on"}


def _job_path(job_id: str) -> Path:
    INGEST_ROOT.mkdir(parents=True, exist_ok=True)
    return INGEST_ROOT / job_id


async def enqueue_file_job(
    store: KnowledgeStore,
    *,
    filename: str,
    raw: bytes,
    kb_id: str = "",
    workspace_id: str = "",
    title: str = "",
) -> Dict[str, Any]:
    limit = library_ingest_max_bytes()
    name = Path(filename or "upload.txt").name
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported type: {suffix or name}")
    if not raw:
        raise ValueError("file empty")
    if len(raw) > limit:
        raise ValueError(f"file too large ({len(raw)} bytes, max {limit})")
    job_id = f"job_{uuid4().hex[:16]}"
    path = _job_path(job_id)
    path.write_bytes(raw)
    job = await store.create_ingest_job(
        job_id=job_id,
        kind="file",
        filename=name,
        source_uri=name,
        kb_id=normalize_local_kb_id(kb_id),
        workspace_id=workspace_id,
        bytes_len=len(raw),
        title=title,
        status="pending",
        progress=0,
        message="queued",
    )
    await kick_job(store, job_id)
    return (await store.get_ingest_job(job_id)) or job


async def enqueue_url_job(
    store: KnowledgeStore,
    *,
    url: str,
    kb_id: str = "",
    workspace_id: str = "",
    title: str = "",
) -> Dict[str, Any]:
    job_id = f"job_{uuid4().hex[:16]}"
    job = await store.create_ingest_job(
        job_id=job_id,
        kind="url",
        filename=title or url,
        source_uri=url,
        kb_id=normalize_local_kb_id(kb_id),
        workspace_id=workspace_id,
        bytes_len=0,
        title=title,
        status="pending",
        progress=0,
        message="queued",
    )
    await kick_job(store, job_id)
    return (await store.get_ingest_job(job_id)) or job


async def kick_job(store: KnowledgeStore, job_id: str) -> None:
    if ingest_sync():
        await process_ingest_job(store, job_id)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        await process_ingest_job(store, job_id)
        return
    loop.create_task(_guarded_process(store, job_id))


async def _guarded_process(store: KnowledgeStore, job_id: str) -> None:
    try:
        await process_ingest_job(store, job_id)
    except Exception:
        logger.exception("ingest job failed: %s", job_id)


async def process_ingest_job(store: KnowledgeStore, job_id: str) -> Dict[str, Any]:
    if job_id in _running:
        row = await store.get_ingest_job(job_id)
        return row or {"job_id": job_id, "status": "processing"}
    _running.add(job_id)
    try:
        job = await store.get_ingest_job(job_id)
        if not job:
            return {"job_id": job_id, "status": "failed", "error": "job not found"}
        if job.get("status") == "completed":
            return job
        await store.update_ingest_job(
            job_id,
            status="processing",
            progress=10,
            message="parsing",
            error="",
        )
        kind = str(job.get("kind") or "file")
        kb_id = normalize_local_kb_id(str(job.get("kb_id") or ""))
        workspace_id = str(job.get("workspace_id") or "")
        title = str(job.get("title") or "").strip()
        limit = library_ingest_max_bytes()

        if kind == "url":
            url = str(job.get("source_uri") or "")
            await store.update_ingest_job(job_id, progress=25, message="fetching url")
            try:
                raw, ctype, final_url = await fetch_ingest_url(url, max_bytes=limit)
            except Exception as exc:
                return await _fail(store, job_id, str(exc))
            filename = title or Path(final_url.split("?")[0]).name or "page.html"
            suffix = suffix_for_url(final_url, ctype, filename)
            source = f"url:{final_url}"
            source_uri = final_url
            tags_extra = "url"
        else:
            path = _job_path(job_id)
            if not path.is_file():
                return await _fail(store, job_id, "uploaded bytes missing")
            raw = path.read_bytes()
            filename = str(job.get("filename") or "upload.txt")
            suffix = Path(filename).suffix.lower()
            source = f"upload:{filename}"
            source_uri = filename
            tags_extra = "upload,manual"
            ctype = ""

        await store.update_ingest_job(job_id, progress=45, message="extracting text")
        try:
            if suffix in {".html", ".htm"} or (kind == "url" and (ctype or "").startswith("text/html")):
                html = raw.decode("utf-8", errors="replace")
                content = html_to_text(html)
                ingest_note = "extracted via html"
                if not content.strip():
                    raise ValueError("HTML produced no extractable text")
            else:
                content, ingest_note = read_bytes_as_text(
                    raw, suffix or ".txt", filename=filename, max_bytes=limit
                )
        except ValueError as exc:
            return await _fail(store, job_id, str(exc))

        await store.update_ingest_job(job_id, progress=75, message="indexing")
        digest = content_hash(content)
        key = f"{workspace_id}:{kb_id}:{filename}:{digest}"
        doc_id = "upload_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        tags = default_tags_for_name(filename)
        tags = f"{tags},{tags_extra}" if tags else tags_extra
        if not title:
            title = Path(filename).stem or "untitled"
        row = await store.upsert(
            doc_id=doc_id,
            title=title,
            content=content,
            tags=tags,
            source=source,
            source_uri=source_uri,
            workspace_id=workspace_id,
            kb_id=kb_id,
            parse_status="completed",
            content_hash_value=digest,
        )
        try:
            _job_path(job_id).unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            p = _job_path(job_id)
            if p.exists():
                p.unlink()
        except OSError:
            pass
        updated = await store.update_ingest_job(
            job_id,
            status="completed",
            progress=100,
            message=ingest_note or "indexed",
            doc_id=doc_id,
            error="",
            bytes_len=len(raw),
        )
        if ingest_note:
            updated = {**updated, "ingest_note": ingest_note, "doc": row}
        else:
            updated = {**updated, "doc": row}
        return updated
    except Exception as exc:
        logger.exception("ingest job %s crashed", job_id)
        return await _fail(store, job_id, str(exc))
    finally:
        _running.discard(job_id)


async def _fail(store: KnowledgeStore, job_id: str, error: str) -> Dict[str, Any]:
    return await store.update_ingest_job(
        job_id,
        status="failed",
        progress=100,
        message="failed",
        error=error[:2000],
    )


async def resume_incomplete_jobs(store: KnowledgeStore) -> None:
    try:
        jobs = await store.list_ingest_jobs(status_in=("pending", "processing"), limit=20)
    except Exception:
        return
    for job in jobs:
        jid = str(job.get("job_id") or "")
        if jid:
            await kick_job(store, jid)
