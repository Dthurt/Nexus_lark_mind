"""WeCom (企业微信) OpenAPI client."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

from src.adapters.channels import resolve_wecom
from src.common.config import Settings, get_settings
from src.common.errors import UpstreamError

logger = logging.getLogger(__name__)


class WeComClient:
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
        creds = resolve_wecom(self.settings)
        if not creds.corp_id or not creds.secret:
            raise UpstreamError("wecom corp_id/secret missing")
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params={"corpid": creds.corp_id, "corpsecret": creds.secret})
        data = resp.json() if resp.content else {}
        if int(data.get("errcode") or 0) != 0:
            raise UpstreamError(f"wecom token failed: {data}")
        token = data.get("access_token") or ""
        if not token:
            raise UpstreamError(f"wecom token empty: {data}")
        expire_in = int(data.get("expires_in") or 7200)
        self._token = token
        self._expire_at = time.time() + expire_in
        return token

    async def send_text(self, *, user_id: str, text: str) -> Dict[str, Any]:
        creds = resolve_wecom(self.settings)
        token = await self.get_access_token()
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        payload = {
            "touser": user_id,
            "msgtype": "markdown",
            "agentid": int(creds.agent_id) if str(creds.agent_id).isdigit() else creds.agent_id,
            "markdown": {"content": (text or "(empty)")[:2048]},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
        data = resp.json() if resp.content else {}
        if int(data.get("errcode") or 0) != 0:
            # Fallback to plain text if markdown not allowed for agent
            payload_text = {
                "touser": user_id,
                "msgtype": "text",
                "agentid": payload["agentid"],
                "text": {"content": (text or "(empty)")[:2048]},
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp2 = await client.post(url, json=payload_text)
            data = resp2.json() if resp2.content else {}
            if int(data.get("errcode") or 0) != 0:
                raise UpstreamError(f"wecom send failed: {data}")
        return data if isinstance(data, dict) else {"raw": data}
