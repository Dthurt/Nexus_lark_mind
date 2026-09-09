"""Discover available models from OpenAI-compatible /models endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from src.common.errors import UpstreamError, ValidationAppError

logger = logging.getLogger(__name__)


def _normalize_base(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        raise ValidationAppError("base_url must start with http:// or https://")
    return url


async def discover_openai_models(
    *,
    base_url: str,
    api_key: str = "",
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """
    GET {base_url}/models and return sorted model ids.
    Works with OpenAI, DeepSeek, GLM, and most OpenAI-compatible proxies.
    """
    root = _normalize_base(base_url)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"{root}/models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"failed to reach {url}: {exc}") from exc

    if resp.status_code >= 400:
        raise UpstreamError(f"models list HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        data = resp.json()
    except Exception as exc:
        raise UpstreamError(f"invalid JSON from {url}") from exc

    ids: List[str] = []
    raw_list = data.get("data") if isinstance(data, dict) else None
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
            elif isinstance(item, str):
                ids.append(item)
    elif isinstance(data, dict) and isinstance(data.get("models"), list):
        for item in data["models"]:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
            elif isinstance(item, str):
                ids.append(item)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
            elif isinstance(item, str):
                ids.append(item)

    # de-dupe, sort (chat-ish first-ish: keep alpha)
    seen = set()
    models: List[str] = []
    for m in ids:
        if m and m not in seen:
            seen.add(m)
            models.append(m)
    models.sort(key=lambda x: x.lower())

    if not models:
        raise UpstreamError(
            f"no models found at {url}; response keys={list(data.keys()) if isinstance(data, dict) else type(data)}"
        )

    return {
        "base_url": root,
        "models": models,
        "count": len(models),
        "default_model": models[0],
    }
