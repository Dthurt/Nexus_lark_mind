"""Persisted channel configs — Feishu app credentials join Nexus-Lark-Mind."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

STORE_PATH = Path("data") / "channels.json"


class FeishuChannelConfig(BaseModel):
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    encrypt_key: str = ""
    use_long_connection: bool = True
    display_name: str = "飞书"


class WebChannelConfig(BaseModel):
    enabled: bool = True
    display_name: str = "Web"


class ChannelStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or STORE_PATH
        self.feishu = FeishuChannelConfig()
        self.web = WebChannelConfig()
        self.load()

    def load(self) -> None:
        self.feishu = FeishuChannelConfig()
        self.web = WebChannelConfig()
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed reading %s", self.path)
            return
        channels = raw.get("channels") or raw
        if isinstance(channels.get("feishu"), dict):
            self.feishu = FeishuChannelConfig.model_validate(channels["feishu"])
        if isinstance(channels.get("web"), dict):
            self.web = WebChannelConfig.model_validate(channels["web"])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "channels": {
                "feishu": self.feishu.model_dump(),
                "web": self.web.model_dump(),
            }
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_feishu(self, data: Dict[str, Any], *, keep_secret_if_blank: bool = True) -> FeishuChannelConfig:
        payload = {**self.feishu.model_dump()}
        secret_fields = {"app_secret", "encrypt_key", "verification_token"}
        for key, value in data.items():
            if key not in FeishuChannelConfig.model_fields:
                continue
            if keep_secret_if_blank and key in secret_fields:
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
            payload[key] = value
        self.feishu = FeishuChannelConfig.model_validate(payload)
        self.save()
        return self.feishu

    def public_document(
        self,
        *,
        env_feishu_app_id: str = "",
        env_feishu_app_secret: str = "",
    ) -> Dict[str, Any]:
        f = self.feishu
        secret = f.app_secret or ""
        preview = ""
        if secret:
            preview = secret[:3] + "…" + secret[-3:] if len(secret) > 6 else "****"
        # Effective: store wins if app_id set, else env
        effective_id = f.app_id or env_feishu_app_id
        effective_secret = f.app_secret or env_feishu_app_secret
        return {
            "product": "Nexus Lark Mind",
            "channels": [
                {
                    "id": "web",
                    "kind": "web",
                    "display_name": self.web.display_name,
                    "enabled": self.web.enabled,
                    "configured": True,
                    "editable": False,
                    "hint": "内置 Web 对话通道，始终可用",
                },
                {
                    "id": "feishu",
                    "kind": "feishu",
                    "display_name": f.display_name or "飞书",
                    "enabled": f.enabled if f.app_id else bool(env_feishu_app_id),
                    "configured": bool(effective_id and effective_secret),
                    "editable": True,
                    "app_id": f.app_id,
                    "app_id_effective": effective_id,
                    "app_secret_set": bool(f.app_secret or env_feishu_app_secret),
                    "app_secret_preview": preview,
                    "verification_token_set": bool(f.verification_token),
                    "encrypt_key_set": bool(f.encrypt_key),
                    "use_long_connection": f.use_long_connection,
                    "source": "settings" if f.app_id else ("env" if env_feishu_app_id else "none"),
                    "hint": "填入飞书开放平台 App ID / App Secret，即可把该应用接入 Nexus Lark Mind",
                },
            ],
        }
