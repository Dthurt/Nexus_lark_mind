"""Thin Python client for Nexus Lark Mind HTTP + SSE APIs (Wave F)."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlencode, urljoin

import httpx


class NlmClientError(RuntimeError):
    pass


def _unwrap(data: Any) -> Any:
    if isinstance(data, dict) and "ok" in data:
        if not data.get("ok", True):
            err = data.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise NlmClientError(msg or "RPC failed")
        return data.get("data", data)
    return data


class NlmClient:
    """Minimal SDK against adapters HTTP (`http://127.0.0.1:8000`)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", *, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NlmClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._client.request(method, path.lstrip("/"), **kwargs)
        try:
            data = resp.json()
        except Exception as exc:
            raise NlmClientError(f"HTTP {resp.status_code}: {resp.text[:300]}") from exc
        if resp.status_code >= 400:
            raise NlmClientError(f"HTTP {resp.status_code}: {data}")
        return _unwrap(data)

    def health(self) -> Dict[str, Any]:
        resp = self._client.get("health")
        resp.raise_for_status()
        return resp.json()

    def create_session(
        self,
        *,
        session_id: Optional[str] = None,
        cwd: Optional[str] = None,
        workspace_id: Optional[str] = None,
        user_id: str = "sdk-user",
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"user_id": user_id, "channel": "web"}
        if session_id:
            body["session_id"] = session_id
        if cwd:
            body["cwd"] = cwd
        if workspace_id:
            body["workspace_id"] = workspace_id
        return self._json("POST", "/api/sessions", json=body)

    def send(
        self,
        content: str,
        *,
        session_id: str,
        tools_enabled: bool = True,
        cwd: Optional[str] = None,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        agent_mode: str = "agent",
        auto_accept: bool = False,
        multitask: bool = True,
        permission_preset: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "content": content,
            "session_id": session_id,
            "stream": True,
            "tools_enabled": tools_enabled,
            "agent_mode": agent_mode,
            "auto_accept": auto_accept,
            "multitask": multitask,
            "user_id": "sdk-user",
        }
        if cwd:
            body["cwd"] = cwd
        if model_provider:
            body["model_provider"] = model_provider
        if model_name:
            body["model_name"] = model_name
        if permission_preset:
            body["permission_preset"] = permission_preset
        return self._json("POST", "/api/chat", json=body)

    def cancel_task(self, task_id: str, *, keep_inbox: bool = True) -> Dict[str, Any]:
        return self._json(
            "POST",
            f"/api/chat/{task_id}/cancel",
            json={"keep_inbox": keep_inbox},
        )

    def cancel_session(self, session_id: str, *, keep_inbox: bool = True) -> Dict[str, Any]:
        return self._json(
            "POST",
            f"/api/sessions/{session_id}/cancel",
            json={"keep_inbox": keep_inbox},
        )

    def push_inbox(self, session_id: str, *, kind: str, content: str) -> Dict[str, Any]:
        return self._json(
            "POST",
            f"/api/sessions/{session_id}/inbox",
            json={"kind": kind, "content": content},
        )

    def stream_events(
        self,
        session_id: str,
        *,
        after: str = "",
        stop_on_terminal: bool = True,
    ) -> Iterator[Dict[str, Any]]:
        """Yield parsed SSE JSON objects until completed/failed (optional)."""
        q = urlencode({"session_id": session_id, **({"after": after} if after else {})})
        url = urljoin(self.base_url, f"api/chat/stream?{q}")
        with httpx.stream("GET", url, timeout=None) as resp:
            resp.raise_for_status()
            buf = ""
            for chunk in resp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    data_lines: List[str] = []
                    for line in frame.splitlines():
                        if line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                        elif line.startswith(":"):
                            continue
                    if not data_lines:
                        continue
                    raw = "\n".join(data_lines)
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    yield ev
                    if stop_on_terminal and ev.get("event_type") in {
                        "task.completed",
                        "task.failed",
                    }:
                        return

    def chat(
        self,
        content: str,
        *,
        session_id: Optional[str] = None,
        cwd: Optional[str] = None,
        print_deltas: bool = False,
        **send_kwargs: Any,
    ) -> Dict[str, Any]:
        """Create/reuse session, send, stream until done; return final payload."""
        if not session_id:
            sess = self.create_session(cwd=cwd)
            session_id = str(
                (sess.get("session_id") if isinstance(sess, dict) else None)
                or (sess if isinstance(sess, str) else "")
                or ""
            )
            if not session_id and isinstance(sess, dict):
                session_id = str(sess.get("id") or "")
        assert session_id
        queued = self.send(content, session_id=session_id, cwd=cwd, **send_kwargs)
        final: Dict[str, Any] = {"session_id": session_id, "queued": queued, "content": "", "error": None}
        collected = ""
        for ev in self.stream_events(session_id):
            typ = ev.get("event_type")
            payload = ev.get("payload") or {}
            if typ == "task.delta" and payload.get("delta"):
                piece = str(payload["delta"])
                collected += piece
                if print_deltas:
                    print(piece, end="", flush=True)
            elif typ == "task.completed":
                final["content"] = payload.get("content") or collected
                final["usage"] = payload.get("usage")
                if print_deltas and not payload.get("content"):
                    pass
                elif print_deltas:
                    print(flush=True)
                break
            elif typ == "task.failed":
                final["error"] = payload.get("error") or "failed"
                final["content"] = payload.get("partial") or collected
                if print_deltas:
                    print(flush=True)
                break
        return final
