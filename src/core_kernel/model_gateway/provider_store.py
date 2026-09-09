"""Persisted custom model providers (DSH-inspired settings store)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

STORE_PATH = Path("data") / "model_providers.json"
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
BUILTIN_IDS = frozenset({"openai", "deepseek", "glm", "anthropic"})


class CustomProvider(BaseModel):
    id: str
    label: str = ""
    api: str = "openai-completions"  # openai-completions | anthropic-messages (future)
    base_url: str
    api_key: str = ""
    default_model: str = ""
    models: List[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not ID_RE.match(v):
            raise ValueError("id must look like my-provider (lowercase kebab-case)")
        if v in BUILTIN_IDS:
            raise ValueError(f"id '{v}' is reserved for builtin providers")
        return v

    @field_validator("base_url")
    @classmethod
    def _url_ok(cls, v: str) -> str:
        v = (v or "").strip().rstrip("/")
        if not v.startswith("http://") and not v.startswith("https://"):
            raise ValueError("base_url must start with http:// or https://")
        return v

    def model_ids(self) -> List[str]:
        items = [m.strip() for m in self.models if str(m).strip()]
        if self.default_model and self.default_model not in items:
            items.insert(0, self.default_model)
        seen = set()
        out: List[str] = []
        for m in items:
            if m not in seen:
                seen.add(m)
                out.append(m)
        return out


class ProviderStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or STORE_PATH
        self.default_provider: Optional[str] = None
        self.providers: Dict[str, CustomProvider] = {}
        self.load()

    def load(self) -> None:
        self.providers = {}
        self.default_provider = None
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed reading %s", self.path)
            return
        self.default_provider = raw.get("default_provider") or None
        for item in raw.get("providers") or []:
            try:
                p = CustomProvider.model_validate(item)
                self.providers[p.id] = p
            except Exception:
                logger.exception("Skip invalid custom provider: %s", item)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "default_provider": self.default_provider,
            "providers": [p.model_dump() for p in self.providers.values()],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_public(self) -> List[Dict[str, Any]]:
        out = []
        for p in self.providers.values():
            out.append(self.to_public(p))
        return out

    @staticmethod
    def to_public(p: CustomProvider) -> Dict[str, Any]:
        key = p.api_key or ""
        preview = ""
        if key:
            preview = key[:4] + "…" + key[-4:] if len(key) > 8 else "****"
        return {
            "id": p.id,
            "label": p.label or p.id,
            "api": p.api,
            "base_url": p.base_url,
            "default_model": p.default_model,
            "models": p.model_ids(),
            "enabled": p.enabled,
            "builtin": False,
            "api_key_set": bool(key),
            "api_key_preview": preview,
            "configured": bool(key) and bool(p.model_ids()),
        }

    def upsert(self, data: Dict[str, Any], *, keep_key_if_blank: bool = True) -> CustomProvider:
        existing = self.providers.get(str(data.get("id") or "").lower())
        payload = dict(data)
        if keep_key_if_blank and existing and not str(payload.get("api_key") or "").strip():
            payload["api_key"] = existing.api_key
        if "models" in payload and isinstance(payload["models"], str):
            payload["models"] = [x.strip() for x in payload["models"].split(",") if x.strip()]
        p = CustomProvider.model_validate(payload)
        if not p.label:
            p.label = p.id
        if not p.default_model and p.models:
            p.default_model = p.models[0]
        self.providers[p.id] = p
        self.save()
        return p

    def delete(self, provider_id: str) -> bool:
        pid = provider_id.strip().lower()
        if pid not in self.providers:
            return False
        del self.providers[pid]
        if self.default_provider == pid:
            self.default_provider = None
        self.save()
        return True

    def set_default(self, provider_id: Optional[str]) -> None:
        self.default_provider = provider_id
        self.save()
