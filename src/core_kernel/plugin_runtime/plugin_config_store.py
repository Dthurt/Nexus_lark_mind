"""Persisted per-plugin configuration (API keys, toggles) — UI-editable, not only .env."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _REPO_ROOT / "data" / "plugin_config.json"

# Declarative schemas for known plugins (shown in UI).
PLUGIN_CONFIG_SCHEMAS: Dict[str, List[Dict[str, Any]]] = {
    "cli.web_search": [
        {
            "key": "TAVILY_API_KEY",
            "label": "Tavily API Key",
            "type": "password",
            "secret": True,
            "hint": "推荐。https://tavily.com — 提升搜索质量与稳定性",
        },
        {
            "key": "BRAVE_API_KEY",
            "label": "Brave Search API Key",
            "type": "password",
            "secret": True,
            "hint": "可选备用搜索源",
        },
        {
            "key": "TAVILY_SEARCH_DEPTH",
            "label": "Tavily depth",
            "type": "select",
            "options": ["basic", "advanced"],
            "hint": "basic 更快，advanced 更全",
        },
    ],
    "cli.literature_search": [
        {
            "key": "SEMANTIC_SCHOLAR_API_KEY",
            "label": "Semantic Scholar API Key",
            "type": "password",
            "secret": True,
            "hint": "可选。默认用 OpenAlex（免费开放）即可",
        },
    ],
    "cli.web_crawl": [
        {
            "key": "CRAWL4AI_MAX_CHARS",
            "label": "Max markdown chars",
            "type": "text",
            "hint": "默认 40000。过大占上下文；过小可能截断长文",
        },
    ],
    "cli.image_search": [
        {
            "key": "SERPAPI_API_KEY",
            "label": "SerpAPI Key（Google 图片）",
            "type": "password",
            "secret": True,
            "hint": "最强：Google Images via SerpAPI — https://serpapi.com",
        },
        {
            "key": "BING_SEARCH_API_KEY",
            "label": "Bing Image Search Key",
            "type": "password",
            "secret": True,
            "hint": "Azure Bing Search v7 — 官方图片检索",
        },
        {
            "key": "BRAVE_API_KEY",
            "label": "Brave Images Key",
            "type": "password",
            "secret": True,
            "hint": "可与网页搜索共用 Brave Key",
        },
        {
            "key": "UNSPLASH_ACCESS_KEY",
            "label": "Unsplash Access Key",
            "type": "password",
            "secret": True,
            "hint": "高质量图库 — https://unsplash.com/developers",
        },
        {
            "key": "PEXELS_API_KEY",
            "label": "Pexels API Key",
            "type": "password",
            "secret": True,
            "hint": "免费图库 — https://www.pexels.com/api/",
        },
    ],
    "builtin.image_gen": [
        {
            "key": "IMAGE_PROVIDER",
            "label": "生图 Provider ID",
            "type": "text",
            "hint": "优先用设置 → 模型 → 生图模型；留空也可回退到默认对话 Provider",
        },
        {
            "key": "IMAGE_MODEL",
            "label": "生图模型名",
            "type": "text",
            "hint": "例如 dall-e-3 / flux / gpt-image-1",
        },
        {
            "key": "IMAGE_SIZE",
            "label": "默认尺寸",
            "type": "select",
            "options": ["1024x1024", "1024x1792", "1792x1024", "512x512"],
        },
    ],
}


class PluginConfigStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or CONFIG_PATH
        self._data: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        self._data = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            plugins = raw.get("plugins") if isinstance(raw, dict) else {}
            if isinstance(plugins, dict):
                self._data = {str(k): dict(v) for k, v in plugins.items() if isinstance(v, dict)}
        except Exception:
            logger.exception("Failed reading %s", self.path)
            self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"plugins": self._data}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, plugin_id: str) -> Dict[str, Any]:
        return dict(self._data.get(plugin_id) or {})

    def upsert(self, plugin_id: str, values: Dict[str, Any], *, keep_blank_secrets: bool = True) -> Dict[str, Any]:
        current = self.get(plugin_id)
        schema = {f["key"]: f for f in PLUGIN_CONFIG_SCHEMAS.get(plugin_id, [])}
        merged = dict(current)
        for k, v in (values or {}).items():
            key = str(k)
            if v is None:
                continue
            text = str(v).strip() if not isinstance(v, (dict, list)) else v
            field = schema.get(key) or {}
            if field.get("secret") and keep_blank_secrets and text == "":
                continue
            if text == "" and key in merged and field.get("secret"):
                continue
            merged[key] = text
        self._data[plugin_id] = merged
        self.save()
        return self.public_view(plugin_id)

    def public_view(self, plugin_id: str) -> Dict[str, Any]:
        raw = self.get(plugin_id)
        schema = PLUGIN_CONFIG_SCHEMAS.get(plugin_id, [])
        fields = []
        for field in schema:
            key = field["key"]
            val = raw.get(key, "")
            secret = bool(field.get("secret"))
            set_flag = bool(str(val or "").strip())
            preview = ""
            if secret and set_flag:
                s = str(val)
                preview = s[:3] + "…" + s[-3:] if len(s) > 8 else "****"
            fields.append(
                {
                    **field,
                    "set": set_flag,
                    "preview": preview,
                    "value": "" if secret else (val if val is not None else ""),
                }
            )
        return {
            "plugin_id": plugin_id,
            "fields": fields,
            "has_schema": bool(schema),
            "values": {f["key"]: ("" if f.get("secret") else raw.get(f["key"], "")) for f in schema},
        }

    def env_for(self, plugin_id: str) -> Dict[str, str]:
        """Flat env-style map for CLI child processes."""
        out: Dict[str, str] = {}
        for k, v in self.get(plugin_id).items():
            if v is None or str(v).strip() == "":
                continue
            out[str(k)] = str(v)
        return out


_store: Optional[PluginConfigStore] = None


def get_plugin_config_store() -> PluginConfigStore:
    global _store
    if _store is None:
        _store = PluginConfigStore()
    return _store
