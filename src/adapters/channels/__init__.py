"""Resolve Feishu credentials: settings UI store overrides .env."""

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
    # Fall back to .env
    return FeishuCredentials(
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret,
        verification_token=settings.feishu_verification_token,
        encrypt_key=settings.feishu_encrypt_key,
        use_long_connection=settings.feishu_use_long_connection and bool(settings.feishu_app_id),
        enabled=bool(settings.feishu_app_id and settings.feishu_app_secret),
        source="env" if settings.feishu_app_id else "none",
    )
