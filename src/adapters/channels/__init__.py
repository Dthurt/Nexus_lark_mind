"""Resolve channel credentials: settings UI store overrides .env."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.adapters.channels.store import ChannelStore
from src.common.config import Settings, get_settings


@dataclass
class FeishuCredentials:
    app_id: str
    app_secret: str
    verification_token: str
    encrypt_key: str
    use_long_connection: bool
    enabled: bool
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.app_id and self.app_secret)


@dataclass
class DingTalkCredentials:
    client_id: str
    client_secret: str
    robot_code: str
    token: str
    encoding_aes_key: str
    enabled: bool
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.client_id and self.client_secret)


@dataclass
class WeComCredentials:
    corp_id: str
    agent_id: str
    secret: str
    token: str
    encoding_aes_key: str
    enabled: bool
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.corp_id and self.secret and self.agent_id)


_store: Optional[ChannelStore] = None


def get_channel_store() -> ChannelStore:
    global _store
    if _store is None:
        _store = ChannelStore()
    return _store


def reload_channel_store() -> ChannelStore:
    global _store
    _store = ChannelStore()
    return _store


def resolve_feishu(settings: Optional[Settings] = None) -> FeishuCredentials:
    settings = settings or get_settings()
    store = get_channel_store()
    f = store.feishu
    if f.app_id and f.app_secret:
        return FeishuCredentials(
            app_id=f.app_id,
            app_secret=f.app_secret,
            verification_token=f.verification_token or settings.feishu_verification_token,
            encrypt_key=f.encrypt_key or settings.feishu_encrypt_key,
            use_long_connection=f.use_long_connection if f.enabled else False,
            enabled=f.enabled,
            source="settings",
        )
    return FeishuCredentials(
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret,
        verification_token=settings.feishu_verification_token,
        encrypt_key=settings.feishu_encrypt_key,
        use_long_connection=settings.feishu_use_long_connection and bool(settings.feishu_app_id),
        enabled=bool(settings.feishu_app_id and settings.feishu_app_secret),
        source="env" if settings.feishu_app_id else "none",
    )


def resolve_dingtalk(settings: Optional[Settings] = None) -> DingTalkCredentials:
    settings = settings or get_settings()
    store = get_channel_store()
    d = store.dingtalk
    if d.client_id and d.client_secret:
        return DingTalkCredentials(
            client_id=d.client_id,
            client_secret=d.client_secret,
            robot_code=d.robot_code,
            token=d.token or settings.dingtalk_token,
            encoding_aes_key=d.encoding_aes_key or settings.dingtalk_encoding_aes_key,
            enabled=d.enabled,
            source="settings",
        )
    return DingTalkCredentials(
        client_id=settings.dingtalk_client_id,
        client_secret=settings.dingtalk_client_secret,
        robot_code=settings.dingtalk_robot_code,
        token=settings.dingtalk_token,
        encoding_aes_key=settings.dingtalk_encoding_aes_key,
        enabled=bool(settings.dingtalk_client_id and settings.dingtalk_client_secret),
        source="env" if settings.dingtalk_client_id else "none",
    )


def resolve_wecom(settings: Optional[Settings] = None) -> WeComCredentials:
    settings = settings or get_settings()
    store = get_channel_store()
    w = store.wecom
    if w.corp_id and w.secret:
        return WeComCredentials(
            corp_id=w.corp_id,
            agent_id=w.agent_id or settings.wecom_agent_id,
            secret=w.secret,
            token=w.token or settings.wecom_token,
            encoding_aes_key=w.encoding_aes_key or settings.wecom_encoding_aes_key,
            enabled=w.enabled,
            source="settings",
        )
    return WeComCredentials(
        corp_id=settings.wecom_corp_id,
        agent_id=settings.wecom_agent_id,
        secret=settings.wecom_secret,
        token=settings.wecom_token,
        encoding_aes_key=settings.wecom_encoding_aes_key,
        enabled=bool(settings.wecom_corp_id and settings.wecom_secret and settings.wecom_agent_id),
        source="env" if settings.wecom_corp_id else "none",
    )
