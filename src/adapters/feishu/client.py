"""Feishu OpenAPI client — send / update messages & cards."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import httpx

from src.adapters.channels import resolve_feishu
from src.common.config import Settings, get_settings
from src.common.errors import UpstreamError

logger = logging.getLogger(__name__)


class FeishuClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._token: Optional[str] = None
        self.base = "https://open.feishu.cn/open-apis"
        self._app_id = ""
        self._app_secret = ""
        self.refresh_credentials()

    def refresh_credentials(self) -> None:
        creds = resolve_feishu(self.settings)
        self._app_id = creds.app_id
        self._app_secret = creds.app_secret
        self._token = None

    @property
    def configured(self) -> bool:
        creds = resolve_feishu(self.settings)
        return bool(creds.app_id and creds.app_secret and creds.enabled)

    async def get_tenant_access_token(self) -> str:
        self.refresh_credentials()
        if not (self._app_id and self._app_secret):
            raise UpstreamError("Feishu app credentials not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base}/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
            )
            data = resp.json()
            if data.get("code") != 0:
                raise UpstreamError(f"feishu token error: {data}")
            self._token = data["tenant_access_token"]
            return self._token

    async def _headers(self) -> Dict[str, str]:
        token = self._token or await self.get_tenant_access_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def reply_text(self, message_id: str, text: str) -> Dict[str, Any]:
        return await self._post(
            f"/im/v1/messages/{message_id}/reply",
            {
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
        )

    async def send_card_to_chat(self, chat_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post(
            "/im/v1/messages",
            {
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
            params={"receive_id_type": "chat_id"},
        )

    async def update_message_card(self, message_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
        return await self._patch(
            f"/im/v1/messages/{message_id}",
            {"msg_type": "interactive", "content": json.dumps(card)},
        )

    async def _post(
        self,
        path: str,
        json_body: Dict[str, Any],
        params: Optional[dict] = None,
    ) -> Dict[str, Any]:
        if not self.configured:
            logger.warning("Feishu not configured — dry-run POST %s", path)
            return {"code": 0, "dry_run": True, "path": path, "body": json_body}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base}{path}",
                headers=await self._headers(),
                json=json_body,
                params=params,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise UpstreamError(f"feishu API error: {data}")
            return data

    async def _patch(self, path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured:
            logger.warning("Feishu not configured — dry-run PATCH %s", path)
            return {"code": 0, "dry_run": True, "path": path, "body": json_body}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                f"{self.base}{path}",
                headers=await self._headers(),
                json=json_body,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise UpstreamError(f"feishu API error: {data}")
            return data
