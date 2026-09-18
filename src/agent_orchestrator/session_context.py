"""Session context helpers via Redis (no direct DB access)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.common.schemas import ChatMessage, ChatRole
from src.common.session_errors import build_error_message, is_persisted_error
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

    async def ensure_user_message(
        self,
        session_id: str,
        content: str,
        *,
        task_id: str = "",
    ) -> bool:
        """Append the user turn if this task has not already recorded it."""
        text = content or ""
        msgs = await self.load_messages(session_id)
        if task_id:
            for m in msgs:
                if not isinstance(m, dict) or m.get("role") != "user":
                    continue
                meta = m.get("metadata") or {}
                if isinstance(meta, dict) and meta.get("task_id") == task_id:
                    return False
        if msgs:
            last = msgs[-1]
            last_meta = last.get("metadata") or {} if isinstance(last, dict) else {}
            last_task = last_meta.get("task_id") if isinstance(last_meta, dict) else None
            if (
                isinstance(last, dict)
                and last.get("role") == "user"
                and (last.get("content") or "") == text
                and (not task_id or not last_task or last_task == task_id)
            ):
                return False
        meta: Dict[str, Any] = {}
        if task_id:
            meta["task_id"] = task_id
        await self.append(
            session_id,
            ChatMessage(role=ChatRole.USER, content=text, metadata=meta),
        )
        return True

    async def persist_turn_error(
        self,
        session_id: str,
        error: str,
        *,
        user_content: str = "",
        task_id: str = "",
        cancelled: bool = False,
        partial: Optional[str] = None,
        user_id: str = "web-user",
        channel: str = "web",
    ) -> None:
        """Write user (if missing) + a styled assistant error onto the session."""
        await self.ensure(session_id, user_id=user_id, channel=channel)
        if user_content:
            await self.ensure_user_message(session_id, user_content, task_id=task_id)
        msgs = await self.load_messages(session_id)
        if task_id:
            for m in msgs:
                if is_persisted_error(m):
                    meta = (m or {}).get("metadata") or {}
                    if isinstance(meta, dict) and meta.get("task_id") == task_id:
                        return
        if cancelled and (partial or "").strip():
            await self.append(
                session_id,
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content=str(partial),
                    metadata={"kind": "partial", "cancelled": True, "task_id": task_id} if task_id else {
                        "kind": "partial",
                        "cancelled": True,
                    },
                ),
            )
        await self.append(
            session_id,
            build_error_message(
                error,
                cancelled=cancelled,
                task_id=task_id,
                partial=partial,
            ),
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
                patch = {
                    "cwd": existing["cwd"],
                    "workspace_id": existing.get("workspace_id") or "",
                    "workspace_title": existing.get("workspace_title") or "",
                    "workspace_kind": existing.get("workspace_kind") or "local",
                    "ssh_host_id": existing.get("ssh_host_id") or "",
                    "updated_at": existing["updated_at"],
                }
                return await self.redis.patch_session(session_id, patch, preserve_messages=True)
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
        try:
            from src.core_kernel.extension_runtime import emit_extension_event

            emit_extension_event(
                "session_start",
                {
                    "session_id": session_id,
                    "channel": channel,
                    "user_id": user_id,
                    "cwd": payload.get("cwd") or "",
                    "workspace_id": payload.get("workspace_id") or "",
                },
            )
        except Exception:
            pass
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
        item = new_inbox_item(kind=kind, content=content, source=source)  # type: ignore[arg-type]
        holder: Dict[str, Any] = {"item": item}

        def mutate(session: Dict[str, Any]) -> None:
            push_inbox(session, holder["item"])
            session["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self.redis.update_session(session_id, mutate, preserve_messages=True)
        return holder["item"]

    async def remove_inbox_item(self, session_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        holder: Dict[str, Any] = {"removed": None}

        def mutate(session: Dict[str, Any]) -> None:
            holder["removed"] = remove_inbox(session, item_id)
            session["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self.redis.update_session(session_id, mutate, preserve_messages=True)
        return holder["removed"]

    async def clear_inbox_items(self, session_id: str) -> List[Dict[str, Any]]:
        holder: Dict[str, Any] = {"prev": []}

        def mutate(session: Dict[str, Any]) -> None:
            holder["prev"] = clear_inbox(session)
            session["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            await self.redis.update_session(session_id, mutate, preserve_messages=True)
        except Exception:
            return []
        return holder["prev"]

    async def claim_steers(self, session_id: str) -> List[Dict[str, Any]]:
        holder: Dict[str, Any] = {"claimed": []}

        def mutate(session: Dict[str, Any]) -> None:
            holder["claimed"] = claim_kind(session, "steer")
            if holder["claimed"]:
                session["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            await self.redis.update_session(session_id, mutate, preserve_messages=True)
        except Exception:
            return []
        return holder["claimed"]

    async def claim_next_queued(self, session_id: str) -> Optional[Dict[str, Any]]:
        holder: Dict[str, Any] = {"claimed": None}

        def mutate(session: Dict[str, Any]) -> None:
            holder["claimed"] = claim_next_queue(session)
            if holder["claimed"]:
                session["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            await self.redis.update_session(session_id, mutate, preserve_messages=True)
        except Exception:
            return None
        return holder["claimed"]

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
        patch = {
            "cwd": session["cwd"],
            "workspace_id": session["workspace_id"],
            "workspace_title": session["workspace_title"],
            "workspace_kind": session["workspace_kind"],
            "ssh_host_id": session["ssh_host_id"],
            "updated_at": session["updated_at"],
        }
        return await self.redis.patch_session(session_id, patch, preserve_messages=True)

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
        active_tools: Optional[Any] = None,
        clear_active_tools: bool = False,
        preset_name: Optional[str] = None,
        system_prompt_append: Optional[str] = None,
        cwd_for_preset: Optional[str] = None,
        weknora_kb_id: Optional[str] = None,
        clear_weknora_kb_id: bool = False,
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
        # Apply mutations on a working copy, then patch fields without touching messages.
        working = dict(session)

        # Named agent preset (Pi-style) — may set tools / permission / model
        if preset_name is not None:
            from src.core_kernel.presets_loader import apply_preset_to_session_patch, resolve_preset

            cwd = (cwd_for_preset or working.get("cwd") or "").strip() or None
            named = resolve_preset(cwd, str(preset_name))
            if named:
                for k, v in apply_preset_to_session_patch(named).items():
                    working[k] = v
            else:
                working["preset_name"] = str(preset_name).strip()

        if permission_preset is not None:
            fields = apply_preset_to_session_fields(permission_preset)
            working.update(fields)
        if agent_mode is not None:
            mode = str(agent_mode).strip().lower()
            if mode not in ("agent", "plan"):
                raise ValueError("agent_mode must be 'agent' or 'plan'")
            working["agent_mode"] = mode
            if mode == "plan":
                working["plan_status"] = plan_status or "drafting"
            elif plan_status is None and working.get("plan_status") == "drafting":
                working["plan_status"] = "idle"
        if auto_accept is not None:
            preset = normalize_preset(working.get("permission_preset"))
            if preset == "read-only":
                working["auto_accept"] = False
            elif preset == "danger-full-access":
                working["auto_accept"] = True
            else:
                working["auto_accept"] = bool(auto_accept)
        if plan_status is not None:
            status = str(plan_status).strip().lower()
            if status not in ("idle", "drafting", "accepted"):
                raise ValueError("plan_status must be idle|drafting|accepted")
            working["plan_status"] = status
        if plan_enforcement is not None:
            working["plan_enforcement"] = normalize_plan_enforcement(plan_enforcement)
        if experience_tier is not None:
            working["experience_tier"] = normalize_experience_tier(experience_tier)
        if reasoning_effort is not None:
            working["reasoning_effort"] = normalize_reasoning_effort(reasoning_effort)
        if model_provider is not None:
            working["model_provider"] = str(model_provider).strip()
        if model_name is not None:
            working["model_name"] = str(model_name).strip()
        if clear_pending_user_text:
            working["pending_user_text"] = ""
        elif pending_user_text is not None:
            working["pending_user_text"] = str(pending_user_text)
        if clear_active_tools:
            working["active_tools"] = None
        elif active_tools is not None:
            if isinstance(active_tools, list):
                working["active_tools"] = [str(x).strip() for x in active_tools if str(x).strip()]
            elif active_tools is False or active_tools == "":
                working["active_tools"] = None
            else:
                raise ValueError("active_tools must be a list of tool names or null")
        if system_prompt_append is not None:
            working["system_prompt_append"] = str(system_prompt_append)
        if clear_weknora_kb_id:
            working["weknora_kb_id"] = ""
        elif weknora_kb_id is not None:
            working["weknora_kb_id"] = str(weknora_kb_id).strip()
        if not working.get("permission_preset"):
            working["permission_preset"] = normalize_preset(None)
        if not working.get("plan_enforcement"):
            working["plan_enforcement"] = normalize_plan_enforcement(None)
        if not working.get("experience_tier"):
            working["experience_tier"] = normalize_experience_tier(None)
        if not working.get("reasoning_effort"):
            working["reasoning_effort"] = normalize_reasoning_effort(None)
        if "model_provider" not in working:
            working["model_provider"] = ""
        if "model_name" not in working:
            working["model_name"] = ""
        working["updated_at"] = datetime.now(timezone.utc).isoformat()
        keys = (
            "agent_mode",
            "auto_accept",
            "plan_status",
            "permission_preset",
            "plan_enforcement",
            "experience_tier",
            "reasoning_effort",
            "model_provider",
            "model_name",
            "pending_user_text",
            "active_tools",
            "preset_name",
            "system_prompt_append",
            "weknora_kb_id",
            "updated_at",
        )
        patch = {k: working.get(k) for k in keys}
        return await self.redis.patch_session(session_id, patch, preserve_messages=True)

    async def touch_title(self, session_id: str, content: str) -> None:
        def mutate(session: Dict[str, Any]) -> None:
            title = (session.get("title") or "").strip()
            if not title or title == "新对话":
                clean = " ".join((content or "").strip().split())
                session["title"] = (clean[:36] + "…") if len(clean) > 36 else (clean or "新对话")
            session["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            await self.redis.update_session(session_id, mutate, preserve_messages=True)
        except Exception:
            return

    async def add_usage(self, session_id: str, usage: Dict[str, Any]) -> Dict[str, Any]:
        holder: Dict[str, Any] = {"totals": {}}

        def mutate(session: Dict[str, Any]) -> None:
            cur = session.get("usage") or {}
            prompt = int(cur.get("prompt_tokens") or 0) + int(usage.get("prompt_tokens") or 0)
            completion = int(cur.get("completion_tokens") or 0) + int(
                usage.get("completion_tokens") or 0
            )
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
            holder["totals"] = totals

        await self.redis.update_session(session_id, mutate, preserve_messages=True)
        return holder["totals"]

    async def clear(self, session_id: str) -> None:
        try:
            from src.core_kernel.extension_runtime import emit_extension_event

            emit_extension_event("session_end", {"session_id": session_id})
        except Exception:
            pass
        await self.redis.delete_session(session_id)

    async def list_summaries(self) -> List[Dict[str, Any]]:
        return await self.redis.list_sessions()
