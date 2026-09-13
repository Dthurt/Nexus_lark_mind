"""Persisted channel configs — Web / Feishu / DingTalk / WeCom."""

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


class DingTalkChannelConfig(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    robot_code: str = ""
    token: str = ""
    encoding_aes_key: str = ""
    display_name: str = "钉钉"


class WeComChannelConfig(BaseModel):
    enabled: bool = False
    corp_id: str = ""
    agent_id: str = ""
    secret: str = ""
    token: str = ""
    encoding_aes_key: str = ""
    display_name: str = "企业微信"


class WebChannelConfig(BaseModel):
    enabled: bool = True
    display_name: str = "Web"


def _secret_preview(secret: str) -> str:
    if not secret:
        return ""
    return secret[:3] + "…" + secret[-3:] if len(secret) > 6 else "****"


class ChannelStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or STORE_PATH
        self.feishu = FeishuChannelConfig()
        self.dingtalk = DingTalkChannelConfig()
        self.wecom = WeComChannelConfig()
        self.web = WebChannelConfig()
        self.load()

    def load(self) -> None:
        self.feishu = FeishuChannelConfig()
        self.dingtalk = DingTalkChannelConfig()
        self.wecom = WeComChannelConfig()
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
        if isinstance(channels.get("dingtalk"), dict):
            self.dingtalk = DingTalkChannelConfig.model_validate(channels["dingtalk"])
        if isinstance(channels.get("wecom"), dict):
            self.wecom = WeComChannelConfig.model_validate(channels["wecom"])
        if isinstance(channels.get("web"), dict):
            self.web = WebChannelConfig.model_validate(channels["web"])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "channels": {
                "web": self.web.model_dump(),
                "feishu": self.feishu.model_dump(),
                "dingtalk": self.dingtalk.model_dump(),
                "wecom": self.wecom.model_dump(),
            }
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _upsert_model(self, model_cls: type[BaseModel], current: BaseModel, data: Dict[str, Any], secret_fields: set[str]) -> BaseModel:
        payload = {**current.model_dump()}
        for key, value in data.items():
            if key not in model_cls.model_fields:
                continue
            if key in secret_fields:
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
            payload[key] = value
        return model_cls.model_validate(payload)

    def upsert_feishu(self, data: Dict[str, Any], *, keep_secret_if_blank: bool = True) -> FeishuChannelConfig:
        self.feishu = self._upsert_model(  # type: ignore[assignment]
            FeishuChannelConfig,
            self.feishu,
            data,
            {"app_secret", "encrypt_key", "verification_token"} if keep_secret_if_blank else set(),
        )
        self.save()
        return self.feishu

    def upsert_dingtalk(self, data: Dict[str, Any], *, keep_secret_if_blank: bool = True) -> DingTalkChannelConfig:
        self.dingtalk = self._upsert_model(  # type: ignore[assignment]
            DingTalkChannelConfig,
            self.dingtalk,
            data,
            {"client_secret", "token", "encoding_aes_key"} if keep_secret_if_blank else set(),
        )
        self.save()
        return self.dingtalk

    def upsert_wecom(self, data: Dict[str, Any], *, keep_secret_if_blank: bool = True) -> WeComChannelConfig:
        self.wecom = self._upsert_model(  # type: ignore[assignment]
            WeComChannelConfig,
            self.wecom,
            data,
            {"secret", "token", "encoding_aes_key"} if keep_secret_if_blank else set(),
        )
        self.save()
        return self.wecom

    def public_document(
        self,
        *,
        env_feishu_app_id: str = "",
        env_feishu_app_secret: str = "",
        env_dingtalk_client_id: str = "",
        env_dingtalk_client_secret: str = "",
        env_wecom_corp_id: str = "",
        env_wecom_secret: str = "",
        runtime: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        f = self.feishu
        d = self.dingtalk
        w = self.wecom
        effective_feishu_id = f.app_id or env_feishu_app_id
        effective_feishu_secret = f.app_secret or env_feishu_app_secret
        effective_dt_id = d.client_id or env_dingtalk_client_id
        effective_dt_secret = d.client_secret or env_dingtalk_client_secret
        effective_wc_corp = w.corp_id or env_wecom_corp_id
        effective_wc_secret = w.secret or env_wecom_secret
        return {
            "product": "Nexus Lark Mind",
            "runtime": runtime or {},
            "channels": [
                {
                    "id": "web",
                    "kind": "web",
                    "display_name": self.web.display_name,
                    "enabled": self.web.enabled,
                    "configured": True,
                    "editable": False,
                    "logo": "web",
                    "hint": "内置 Web 对话通道，始终可用",
                },
                {
                    "id": "feishu",
                    "kind": "feishu",
                    "display_name": f.display_name or "飞书",
                    "enabled": f.enabled if f.app_id else bool(env_feishu_app_id),
                    "configured": bool(effective_feishu_id and effective_feishu_secret),
                    "editable": True,
                    "logo": "feishu",
                    "app_id": f.app_id,
                    "app_id_effective": effective_feishu_id,
                    "app_secret_set": bool(f.app_secret or env_feishu_app_secret),
                    "app_secret_preview": _secret_preview(f.app_secret),
                    "verification_token_set": bool(f.verification_token),
                    "encrypt_key_set": bool(f.encrypt_key),
                    "use_long_connection": f.use_long_connection,
                    "source": "settings" if f.app_id else ("env" if env_feishu_app_id else "none"),
                    "webhook_path": "/feishu/webhook",
                    "hint": "填入飞书开放平台 App ID / App Secret，即可把该应用接入 Nexus Lark Mind",
                },
                {
                    "id": "dingtalk",
                    "kind": "dingtalk",
                    "display_name": d.display_name or "钉钉",
                    "enabled": d.enabled if d.client_id else bool(env_dingtalk_client_id),
                    "configured": bool(effective_dt_id and effective_dt_secret),
                    "editable": True,
                    "logo": "dingtalk",
                    "client_id": d.client_id,
                    "client_id_effective": effective_dt_id,
                    "client_secret_set": bool(d.client_secret or env_dingtalk_client_secret),
                    "client_secret_preview": _secret_preview(d.client_secret),
                    "robot_code": d.robot_code,
                    "token_set": bool(d.token),
                    "encoding_aes_key_set": bool(d.encoding_aes_key),
                    "source": "settings" if d.client_id else ("env" if env_dingtalk_client_id else "none"),
                    "webhook_path": "/dingtalk/webhook",
                    "hint": "填入钉钉应用 Client ID / Secret；机器人 HTTP 回调指向 /dingtalk/webhook",
                },
                {
                    "id": "wecom",
                    "kind": "wecom",
                    "display_name": w.display_name or "企业微信",
                    "enabled": w.enabled if w.corp_id else bool(env_wecom_corp_id),
                    "configured": bool(effective_wc_corp and effective_wc_secret and w.agent_id),
                    "editable": True,
                    "logo": "wecom",
                    "corp_id": w.corp_id,
                    "corp_id_effective": effective_wc_corp,
                    "agent_id": w.agent_id,
                    "secret_set": bool(w.secret or env_wecom_secret),
                    "secret_preview": _secret_preview(w.secret),
                    "token_set": bool(w.token),
                    "encoding_aes_key_set": bool(w.encoding_aes_key),
                    "source": "settings" if w.corp_id else ("env" if env_wecom_corp_id else "none"),
                    "webhook_path": "/wecom/webhook",
                    "hint": "填入企业微信 CorpID / AgentId / Secret；回调 URL 指向 /wecom/webhook",
                },
            ],
        }
