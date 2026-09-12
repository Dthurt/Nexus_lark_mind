"""Session context helpers via Redis (no direct DB access)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.common.schemas import ChatMessage
from src.common.session_inbox import (
    claim_kind,
    claim_next_queue,
    clear_inbox,
    list_inbox,
    new_inbox_item,
    push_inbox,
    remove_inbox,
)
from src.infrastructure.redis_client import RedisClient


class SessionContext:
    def __init__(self, redis_client: RedisClient) -> None:
        self.redis = redis_client

    async def load_messages(self, session_id: str) -> List[Dict[str, Any]]:
        session = await self.redis.get_session(session_id)
        if not session:
            return []
        return list(session.get("messages") or [])

    async def append(self, session_id: str, message: ChatMessage) -> Dict[str, Any]:
        return await self.redis.append_session_message(
            session_id,
            message.model_dump(mode="json"),
        )

    async def ensure(
        self,
        session_id: str,
        *,
        user_id: str,
        channel: str,
        cwd: Optional[str] = None,
        workspace_id: Optional[str] = None,
        workspace_title: Optional[str] = None,
        workspace_kind: Optional[str] = None,
        ssh_host_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = await self.redis.get_session(session_id)
        if existing:
            # Bind workspace only if session has none yet (or explicitly empty)
            changed = False
            if cwd and not (existing.get("cwd") or "").strip():
                existing["cwd"] = cwd
                existing["workspace_id"] = workspace_id or existing.get("workspace_id") or ""
                existing["workspace_title"] = workspace_title or existing.get("workspace_title") or ""
                existing["workspace_kind"] = workspace_kind or existing.get("workspace_kind") or "local"
                existing["ssh_host_id"] = ssh_host_id or existing.get("ssh_host_id") or ""
                changed = True
            if changed:
                existing["updated_at"] = datetime.now(timezone.utc).isoformat()
                await self.redis.set_session(session_id, existing)
            return existing
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "channel": channel,
            "title": "新对话",
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cached_tokens": 0},
            "cwd": (cwd or "").strip(),
            "workspace_id": (workspace_id or "").strip(),
            "workspace_title": (workspace_title or "").strip(),
            "workspace_kind": (workspace_kind or ("ssh" if ssh_host_id else "local")).strip(),
            "ssh_host_id": (ssh_host_id or "").strip(),
            "agent_mode": "agent",
            "auto_accept": False,
            "plan_status": "idle",
            "permission_preset": "workspace-write",
            "plan_enforcement": "hard",
            "experience_tier": "balanced",
            "reasoning_effort": "medium",
            "model_provider": "",
            "model_name": "",
            "pending_user_text": "",
            "inbox": [],
        }
        await self.redis.set_session(session_id, payload)
        return payload

    async def get_inbox(self, session_id: str) -> List[Dict[str, Any]]:
        session = await self.redis.get_session(session_id)
        if not session:
            return []
        return list_inbox(session)

    async def push_inbox_item(
        self,
        session_id: str,
        *,
        kind: str,
        content: str,
        source: str = "user",
    ) -> Dict[str, Any]:
        session = await self.redis.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        item = new_inbox_item(kind=kind, content=content, source=source)  # type: ignore[arg-type]
        push_inbox(session, item)
        await self.redis.set_session(session_id, session)
        return item

    async def remove_inbox_item(self, session_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        session = await self.redis.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        removed = remove_inbox(session, item_id)
        await self.redis.set_session(session_id, session)
        return removed

    async def clear_inbox_items(self, session_id: str) -> List[Dict[str, Any]]:
        session = await self.redis.get_session(session_id)
        if not session:
            return []
        prev = clear_inbox(session)
        await self.redis.set_session(session_id, session)
        return prev

    async def claim_steers(self, session_id: str) -> List[Dict[str, Any]]:
        session = await self.redis.get_session(session_id)
        if not session:
            return []
        claimed = claim_kind(session, "steer")
        if claimed:
            await self.redis.set_session(session_id, session)
        return claimed

    async def claim_next_queued(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = await self.redis.get_session(session_id)
        if not session:
            return None
        claimed = claim_next_queue(session)
        if claimed:
            await self.redis.set_session(session_id, session)
        return claimed

    async def bind_workspace(
        self,
        session_id: str,
        *,
        cwd: str,
        workspace_id: str = "",
        workspace_title: str = "",
        workspace_kind: str = "local",
        ssh_host_id: str = "",
        force: bool = False,
    ) -> Dict[str, Any]:
        session = await self.redis.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        msgs = session.get("messages") or []
        if msgs and not force:
            # Allow rebinding only on empty chats by default
            if (session.get("cwd") or "").strip() and (session.get("cwd") or "").strip() != cwd:
                raise ValueError("session already has messages; workspace is locked")
        session["cwd"] = cwd.strip()
        session["workspace_id"] = (workspace_id or "").strip()
        session["workspace_title"] = (workspace_title or "").strip()
        session["workspace_kind"] = (workspace_kind or "local").strip()
        session["ssh_host_id"] = (ssh_host_id or "").strip()
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set_session(session_id, session)
        return session

    async def set_interaction(
        self,
        session_id: str,
        *,
        agent_mode: Optional[str] = None,
        auto_accept: Optional[bool] = None,
        plan_status: Optional[str] = None,
        permission_preset: Optional[str] = None,
        plan_enforcement: Optional[str] = None,
        experience_tier: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        pending_user_text: Optional[str] = None,
        clear_pending_user_text: bool = False,
    ) -> Dict[str, Any]:
        from src.common.experience_tiers import (
            normalize_experience_tier,
            normalize_reasoning_effort,
        )
        from src.common.permission_presets import (
            apply_preset_to_session_fields,
            normalize_plan_enforcement,
            normalize_preset,
        )

        session = await self.redis.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        if permission_preset is not None:
            fields = apply_preset_to_session_fields(permission_preset)
            session.update(fields)
            # Preset owns auto_accept unless caller also passes auto_accept below.
        if agent_mode is not None:
            mode = str(agent_mode).strip().lower()
            if mode not in ("agent", "plan"):
                raise ValueError("agent_mode must be 'agent' or 'plan'")
            session["agent_mode"] = mode
            if mode == "plan":
                session["plan_status"] = plan_status or "drafting"
            elif plan_status is None and session.get("plan_status") == "drafting":
                session["plan_status"] = "idle"
        if auto_accept is not None:
            # read-only forbids accept; danger forces accept
            preset = normalize_preset(session.get("permission_preset"))
            if preset == "read-only":
                session["auto_accept"] = False
            elif preset == "danger-full-access":
                session["auto_accept"] = True
            else:
                session["auto_accept"] = bool(auto_accept)
        if plan_status is not None:
            status = str(plan_status).strip().lower()
            if status not in ("idle", "drafting", "accepted"):
                raise ValueError("plan_status must be idle|drafting|accepted")
            session["plan_status"] = status
        if plan_enforcement is not None:
            session["plan_enforcement"] = normalize_plan_enforcement(plan_enforcement)
        if experience_tier is not None:
            session["experience_tier"] = normalize_experience_tier(experience_tier)
        if reasoning_effort is not None:
            session["reasoning_effort"] = normalize_reasoning_effort(reasoning_effort)
        if model_provider is not None:
            session["model_provider"] = str(model_provider).strip()
        if model_name is not None:
            session["model_name"] = str(model_name).strip()
        if clear_pending_user_text:
            session["pending_user_text"] = ""
        elif pending_user_text is not None:
            session["pending_user_text"] = str(pending_user_text)
        # Ensure defaults exist on older sessions
        if not session.get("permission_preset"):
            session["permission_preset"] = normalize_preset(None)
        if not session.get("plan_enforcement"):
            session["plan_enforcement"] = normalize_plan_enforcement(None)
        if not session.get("experience_tier"):
            session["experience_tier"] = normalize_experience_tier(None)
        if not session.get("reasoning_effort"):
            session["reasoning_effort"] = normalize_reasoning_effort(None)
        if "model_provider" not in session:
            session["model_provider"] = ""
        if "model_name" not in session:
            session["model_name"] = ""
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set_session(session_id, session)
        return session

    async def touch_title(self, session_id: str, content: str) -> None:
        session = await self.redis.get_session(session_id)
        if not session:
            return
        title = (session.get("title") or "").strip()
        if not title or title == "新对话":
            clean = " ".join((content or "").strip().split())
            session["title"] = (clean[:36] + "…") if len(clean) > 36 else (clean or "新对话")
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set_session(session_id, session)

    async def add_usage(self, session_id: str, usage: Dict[str, Any]) -> Dict[str, Any]:
        session = await self.redis.get_session(session_id) or {"session_id": session_id, "messages": []}
        cur = session.get("usage") or {}
        prompt = int(cur.get("prompt_tokens") or 0) + int(usage.get("prompt_tokens") or 0)
        completion = int(cur.get("completion_tokens") or 0) + int(usage.get("completion_tokens") or 0)
        cached = int(cur.get("cached_tokens") or 0) + int(usage.get("cached_tokens") or 0)
        cache_create = int(cur.get("cache_creation_tokens") or 0) + int(
            usage.get("cache_creation_tokens") or 0
        )
        duration = float(cur.get("duration_ms") or 0) + float(usage.get("duration_ms") or 0)
        totals: Dict[str, Any] = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "cached_tokens": cached,
            "cache_creation_tokens": cache_create,
        }
        if duration:
            totals["duration_ms"] = duration
        if usage.get("estimated") or cur.get("estimated"):
            totals["estimated"] = 1
        session["usage"] = totals
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set_session(session_id, session)
        return totals

    async def clear(self, session_id: str) -> None:
        await self.redis.delete_session(session_id)

    async def list_summaries(self) -> List[Dict[str, Any]]:
        return await self.redis.list_sessions()
