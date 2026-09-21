"""In-memory broker for local single-process mode (no Redis / Docker)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Union

import orjson

from src.common.config import Settings, get_settings
from src.common.errors import QueueError
from src.common.schemas import BusEvent, StandardTask

logger = logging.getLogger(__name__)

EventHandler = Callable[[BusEvent], Awaitable[None]]

_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9._-]{1,180}$")
_INDEX_NAME = "index.json"


class MemoryBroker:
    """Duck-compatible with RedisClient for queue / pubsub / session cache."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        persist: bool = False,
        persist_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._subscribers: Set[asyncio.Queue[bytes]] = set()
        self._sessions: Dict[str, dict] = {}
        self._session_order: List[str] = []
        self._kv: Dict[str, Any] = {}
        self._event_logs: Dict[str, List[dict]] = {}
        self._lock = asyncio.Lock()
        self._connected = False
        raw_dir = persist_dir if persist_dir is not None else self.settings.session_persist_dir
        self._persist_dir = Path(str(raw_dir)) if persist and str(raw_dir or "").strip() else None

    async def connect(self) -> None:
        already = self._connected
        self._connected = True
        if not already:
            restored = self._hydrate_from_disk()
            extra = ""
            if self._persist_dir is not None:
                extra = f", persist={self._persist_dir} restored={restored}"
            logger.info("Memory broker ready (local mode, no Redis)%s", extra)

    async def close(self) -> None:
        self._connected = False
        self._subscribers.clear()

    async def enqueue_task(self, task: StandardTask) -> None:
        if not self._connected:
            raise QueueError("Memory broker not connected")
        await self._queue.put(orjson.dumps(task.model_dump(mode="json")))

    async def dequeue_task(self, timeout: int = 5) -> Optional[StandardTask]:
        try:
            raw = await asyncio.wait_for(self._queue.get(), timeout=float(timeout))
        except asyncio.TimeoutError:
            return None
        except Exception as exc:
            raise QueueError(f"dequeue failed: {exc}") from exc
        return StandardTask.model_validate(orjson.loads(raw))

    async def publish_event(self, event: BusEvent) -> None:
        payload = orjson.dumps(event.model_dump(mode="json"))
        dead: List[asyncio.Queue[bytes]] = []
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    async def subscribe_events(
        self,
        handler: EventHandler,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1024)
        self._subscribers.add(q)
        logger.debug("Memory broker subscriber attached (%s total)", len(self._subscribers))
        try:
            while True:
                if stop_event and stop_event.is_set():
                    break
                try:
                    raw = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    event = BusEvent.model_validate(orjson.loads(raw))
                    await handler(event)
                except Exception:
                    logger.exception("Failed to handle memory bus event")
        finally:
            self._subscribers.discard(q)

    def _session_key(self, session_id: str) -> str:
        return f"{self.settings.redis_session_prefix}{session_id}"

    def _session_file(self, session_id: str) -> Path:
        assert self._persist_dir is not None
        name = session_id if _SAFE_SESSION_ID.match(session_id) else hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self._persist_dir / f"{name}.json"

    def _hydrate_from_disk(self) -> int:
        if self._persist_dir is None:
            return 0
        root = self._persist_dir
        if not root.is_dir():
            return 0
        order: List[str] = []
        index_path = root / _INDEX_NAME
        if index_path.is_file():
            try:
                raw = orjson.loads(index_path.read_bytes())
                ids = raw.get("ids") if isinstance(raw, dict) else raw
                if isinstance(ids, list):
                    order = [str(x) for x in ids if str(x).strip()]
            except Exception:
                logger.exception("Failed to read session index %s", index_path)
        loaded: Dict[str, dict] = {}
        for path in root.glob("*.json"):
            if path.name == _INDEX_NAME:
                continue
            try:
                payload = orjson.loads(path.read_bytes())
            except Exception:
                logger.exception("Failed to read session file %s", path)
                continue
            if not isinstance(payload, dict):
                continue
            sid = str(payload.get("session_id") or path.stem).strip()
            if not sid:
                continue
            loaded[sid] = payload
        if not order:
            def _stamp(sid: str) -> str:
                sess = loaded.get(sid) or {}
                return str(sess.get("updated_at") or sess.get("created_at") or "")

            order = sorted(loaded.keys(), key=_stamp)
        else:
            extras = [sid for sid in loaded.keys() if sid not in order]
            extras.sort(key=lambda sid: str((loaded.get(sid) or {}).get("updated_at") or ""))
            order.extend(extras)
        count = 0
        for sid in order:
            payload = loaded.get(sid)
            if not payload:
                continue
            self._sessions[self._session_key(sid)] = payload
            if sid not in self._session_order:
                self._session_order.append(sid)
            count += 1
        return count

    def _write_index(self) -> None:
        if self._persist_dir is None:
            return
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        path = self._persist_dir / _INDEX_NAME
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(orjson.dumps({"ids": list(self._session_order)}))
        os.replace(tmp, path)

    def _persist_session(self, session_id: str, payload: dict) -> None:
        if self._persist_dir is None:
            return
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            path = self._session_file(session_id)
            tmp = path.with_name(path.name + ".tmp")
            blob = dict(payload)
            blob.setdefault("session_id", session_id)
            tmp.write_bytes(orjson.dumps(blob))
            os.replace(tmp, path)
            self._write_index()
        except Exception:
            logger.exception("Failed to persist session %s", session_id)

    def _forget_persisted(self, session_id: str) -> None:
        if self._persist_dir is None:
            return
        try:
            path = self._session_file(session_id)
            if path.is_file():
                path.unlink()
            self._write_index()
        except Exception:
            logger.exception("Failed to delete persisted session %s", session_id)

    def _put_session(self, session_id: str, payload: dict) -> None:
        key = self._session_key(session_id)
        self._sessions[key] = payload
        if session_id not in self._session_order:
            self._session_order.append(session_id)
        self._persist_session(session_id, payload)

    async def set_session(self, session_id: str, payload: dict, ttl: int = 86400) -> None:
        _ = ttl  # local mode has no TTL; disk files survive nlm restart
        async with self._lock:
            self._put_session(session_id, payload)

    async def get_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(self._session_key(session_id))

    async def delete_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(self._session_key(session_id), None)
            self._session_order = [s for s in self._session_order if s != session_id]
            self._forget_persisted(session_id)

    def _session_list_row(self, session_id: str, sess: dict) -> dict:
        msgs = sess.get("messages") or []
        preview = ""
        for m in reversed(msgs):
            if m.get("role") == "user" and m.get("content"):
                preview = str(m["content"])[:80]
                break
        return {
            "session_id": session_id,
            "title": sess.get("title") or "新对话",
            "updated_at": sess.get("updated_at"),
            "created_at": sess.get("created_at"),
            "message_count": len(msgs),
            "preview": preview,
            "channel": sess.get("channel"),
            "cwd": sess.get("cwd") or "",
            "workspace_id": sess.get("workspace_id") or "",
            "workspace_title": sess.get("workspace_title") or "",
            "workspace_kind": sess.get("workspace_kind") or "local",
            "ssh_host_id": sess.get("ssh_host_id") or "",
            "parent_id": sess.get("parent_id") or sess.get("forked_from") or "",
            "forked_from": sess.get("forked_from") or "",
            "fork_point_index": sess.get("fork_point_index"),
            "bookmarks": sess.get("bookmarks") or [],
            "preset_name": sess.get("preset_name") or "",
            "active_tools": sess.get("active_tools"),
        }

    async def list_sessions(self) -> List[dict]:
        out: List[dict] = []
        for sid in reversed(self._session_order):
            sess = self._sessions.get(self._session_key(sid))
            if not sess:
                continue
            out.append(self._session_list_row(sid, sess))
        return out

    async def append_session_message(self, session_id: str, message: dict, ttl: int = 86400) -> dict:
        _ = ttl
        async with self._lock:
            session = self._sessions.get(self._session_key(session_id))
            if session is None:
                raise KeyError(f"session missing for append: {session_id}")
            session.setdefault("messages", []).append(message)
            self._put_session(session_id, session)
            return session

    async def patch_session(
        self,
        session_id: str,
        patch: dict,
        *,
        ttl: int = 86400,
        preserve_messages: bool = True,
    ) -> dict:
        def mutator(session: dict) -> None:
            for k, v in (patch or {}).items():
                if preserve_messages and k == "messages":
                    continue
                session[k] = v

        return await self.update_session(
            session_id,
            mutator,
            ttl=ttl,
            preserve_messages=preserve_messages,
        )

    async def update_session(
        self,
        session_id: str,
        mutator,
        *,
        ttl: int = 86400,
        preserve_messages: bool = True,
    ) -> dict:
        _ = ttl
        async with self._lock:
            session = self._sessions.get(self._session_key(session_id))
            if session is None:
                raise KeyError(f"session missing for update: {session_id}")
            prior_messages = list(session.get("messages") or [])
            mutator(session)
            if preserve_messages:
                session["messages"] = prior_messages
            self._put_session(session_id, session)
            return session

    # ----- Generic KV + SSE event ring (Wave C) -----

    async def kv_set(self, key: str, value: dict, ttl: int = 86400) -> None:
        self._kv[key] = dict(value)

    async def kv_get(self, key: str) -> Optional[dict]:
        raw = self._kv.get(key)
        return dict(raw) if isinstance(raw, dict) else None

    async def kv_delete(self, key: str) -> None:
        self._kv.pop(key, None)

    async def append_session_event(
        self,
        session_id: str,
        event: dict,
        *,
        maxlen: int = 300,
    ) -> None:
        log = self._event_logs.setdefault(session_id, [])
        log.append(dict(event))
        if len(log) > maxlen:
            del log[: len(log) - maxlen]

    async def list_session_events_after(
        self,
        session_id: str,
        after_event_id: str = "",
    ) -> List[dict]:
        log = list(self._event_logs.get(session_id) or [])
        if not after_event_id:
            return log
        out: List[dict] = []
        seen = False
        for ev in log:
            eid = str(ev.get("event_id") or "")
            if not seen:
                if eid == after_event_id:
                    seen = True
                continue
            out.append(ev)
        # If after_id not found, return full log (client may have stale cursor)
        return out if seen else log


_SHARED: Optional[MemoryBroker] = None


def get_shared_memory_broker(settings: Optional[Settings] = None) -> MemoryBroker:
    global _SHARED
    if _SHARED is None:
        _SHARED = MemoryBroker(settings or get_settings(), persist=True)
    return _SHARED
