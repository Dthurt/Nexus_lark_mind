"""Channel / provider connectivity probes."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from src.common.errors import UpstreamError, ValidationAppError
from src.core_kernel.model_gateway.discover import discover_openai_models

logger = logging.getLogger(__name__)


async def test_openai_compat(
    *,
    base_url: str,
    api_key: str = "",
    model: str = "",
) -> Dict[str, Any]:
    """Probe /models then optional tiny chat/completions."""
    discovered = await discover_openai_models(base_url=base_url, api_key=api_key)
    models = discovered.get("models") or []
    use_model = model or discovered.get("default_model") or (models[0] if models else "")
    chat_ok = False
    chat_error = None
    if use_model and api_key:
        root = discovered["base_url"]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
            "temperature": 0,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{root}/chat/completions", headers=headers, json=payload)
            if resp.status_code < 400:
                chat_ok = True
            else:
                chat_error = f"HTTP {resp.status_code}: {resp.text[:240]}"
        except Exception as exc:
            chat_error = str(exc)
    return {
        "ok": True,
        "models_ok": True,
        "models_count": len(models),
        "sample_models": models[:8],
        "chat_ok": chat_ok,
        "chat_model": use_model,
        "chat_error": chat_error,
        "message": "连通成功" if chat_ok or not api_key else f"模型列表可达；对话探测：{chat_error or '跳过'}",
    }


async def test_feishu_app(*, app_id: str, app_secret: str) -> Dict[str, Any]:
    if not app_id or not app_secret:
        raise ValidationAppError("app_id and app_secret required")
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json={"app_id": app_id, "app_secret": app_secret})
            data = resp.json()
    except httpx.HTTPError as exc:
        raise UpstreamError(f"feishu unreachable: {exc}") from exc
    if data.get("code") != 0:
        raise UpstreamError(f"feishu auth failed: {data}")
    token = data.get("tenant_access_token") or ""
    return {
        "ok": True,
        "message": "飞书 App 凭证有效，已取得 tenant_access_token",
        "token_preview": (token[:6] + "…") if token else "",
        "expire": data.get("expire"),
    }
