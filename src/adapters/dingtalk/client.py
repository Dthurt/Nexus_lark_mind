"""DingTalk OpenAPI client — access token + sessionWebhook / oToMessages."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

from src.adapters.channels import resolve_dingtalk
from src.common.config import Settings, get_settings
from src.common.errors import UpstreamError

logger = logging.getLogger(__name__)


class DingTalkClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._token = ""
        self._expire_at = 0.0

    def refresh_credentials(self) -> None:
        self._token = ""
        self._expire_at = 0.0

    async def get_access_token(self) -> str:
        if self._token and time.time() < self._expire_at - 60:
            return self._token
        creds = resolve_dingtalk(self.settings)
        if not creds.client_id or not creds.client_secret:
            raise UpstreamError("dingtalk client_id/client_secret missing")
        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                json={"appKey": creds.client_id, "appSecret": creds.client_secret},
            )
        data = resp.json() if resp.content else {}
        token = data.get("accessToken") or ""
        if not token:
            raise UpstreamError(f"dingtalk token failed: {data}")
        expire_in = int(data.get("expireIn") or 7200)
        self._token = token
        self._expire_at = time.time() + expire_in
        return token

    async def reply_session_webhook(self, webhook: str, text: str) -> Dict[str, Any]:
        if not webhook:
            raise UpstreamError("dingtalk sessionWebhook missing")
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "Nexus Lark Mind",
                "text": text or "(empty)",
            },
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(webhook, json=payload)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise UpstreamError(f"dingtalk webhook HTTP {resp.status_code}: {resp.text[:300]}")
        return data if isinstance(data, dict) else {"raw": data}

    async def send_text_to_user(self, *, user_id: str, text: str) -> Dict[str, Any]:
        """Best-effort proactive robot text via oToMessages (needs robotCode)."""
        creds = resolve_dingtalk(self.settings)
        token = await self.get_access_token()
        robot_code = creds.robot_code or creds.client_id
        url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": token}
        payload = {
            "robotCode": robot_code,
            "userIds": [user_id],
            "msgKey": "sampleMarkdown",
            "msgParam": '{"title":"Nexus Lark Mind","text":'
            + _json_escape(text or "(empty)")
            + "}",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise UpstreamError(f"dingtalk send HTTP {resp.status_code}: {resp.text[:300]}")
        return data if isinstance(data, dict) else {"raw": data}


def _json_escape(text: str) -> str:
    import json

    return json.dumps(text, ensure_ascii=False)
