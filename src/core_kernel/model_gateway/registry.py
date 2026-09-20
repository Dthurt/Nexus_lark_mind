"""Provider registry — builtin env vendors + persisted custom OpenAI-compat routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.common.config import Settings, get_settings
from src.common.errors import NotFoundError, ValidationAppError
from src.core_kernel.model_gateway.anthropic import AnthropicProvider
from src.core_kernel.model_gateway.base import BaseModelProvider
from src.core_kernel.model_gateway.openai_compat import OpenAICompatProvider
from src.core_kernel.model_gateway.provider_store import BUILTIN_IDS, ProviderStore


def _split_models(raw: str, fallback: str = "") -> List[str]:
    items = [x.strip() for x in (raw or "").split(",") if x.strip()]
    if fallback and fallback not in items:
        items.insert(0, fallback)
    seen = set()
    out: List[str] = []
    for m in items:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


class ProviderRegistry:
    def __init__(self, settings: Optional[Settings] = None, store: Optional[ProviderStore] = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or ProviderStore()
        self._providers: Dict[str, BaseModelProvider] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        self._providers.clear()
        self._meta.clear()
        self.store.load()
        self._register_defaults()
        self._register_customs()

    def _register_defaults(self) -> None:
        s = self.settings
        self.register(
            OpenAICompatProvider(
                name="openai",
                api_key=s.openai_api_key,
                base_url=s.openai_base_url,
                default_model=s.openai_default_model or "gpt-4o-mini",
                settings=s,
            ),
            label="OpenAI",
            configured=bool(s.openai_api_key),
            models=_split_models(s.openai_models, s.openai_default_model),
            builtin=True,
            base_url=s.openai_base_url,
            api="openai-completions",
            api_key_set=bool(s.openai_api_key),
        )
        self.register(
            OpenAICompatProvider(
                name="deepseek",
                api_key=s.deepseek_api_key,
                base_url=s.deepseek_base_url,
                default_model=s.deepseek_default_model or "deepseek-chat",
                settings=s,
            ),
            label="DeepSeek",
            configured=bool(s.deepseek_api_key),
            models=_split_models(s.deepseek_models, s.deepseek_default_model),
            builtin=True,
            base_url=s.deepseek_base_url,
            api="openai-completions",
            api_key_set=bool(s.deepseek_api_key),
        )
        self.register(
            OpenAICompatProvider(
                name="glm",
                api_key=s.glm_api_key,
                base_url=s.glm_base_url,
                default_model=s.glm_default_model or s.default_model_name,
                settings=s,
            ),
            label="GLM / 智谱",
            configured=bool(s.glm_api_key),
            models=_split_models(s.glm_models, s.glm_default_model or s.default_model_name),
            builtin=True,
            base_url=s.glm_base_url,
            api="openai-completions",
            api_key_set=bool(s.glm_api_key),
        )
        anthropic = AnthropicProvider(s)
        anthropic.default_model = s.anthropic_default_model or anthropic.default_model
        self.register(
            anthropic,
            label="Anthropic",
            configured=bool(s.anthropic_api_key),
            models=_split_models(s.anthropic_models, s.anthropic_default_model),
            builtin=True,
            base_url=s.anthropic_base_url,
            api="anthropic-messages",
            api_key_set=bool(s.anthropic_api_key),
        )

    def _register_customs(self) -> None:
        for p in self.store.providers.values():
            if not p.enabled:
                continue
            if (getattr(p, "kind", None) or "chat") != "chat":
                continue
            models = p.model_ids()
            if p.api == "anthropic-messages":
                provider = AnthropicProvider(
                    self.settings,
                    name=p.id,
                    api_key=p.api_key,
                    base_url=p.base_url,
                    default_model=p.default_model or (models[0] if models else ""),
                )
            else:
                provider = OpenAICompatProvider(
                    name=p.id,
                    api_key=p.api_key,
                    base_url=p.base_url,
                    default_model=p.default_model or (models[0] if models else ""),
                    settings=self.settings,
                )
            self.register(
                provider,
                label=p.label or p.id,
                configured=bool(p.api_key) and bool(models),
                models=models,
                builtin=False,
                base_url=p.base_url,
                api=p.api,
                api_key_set=bool(p.api_key),
            )

    def register(
        self,
        provider: BaseModelProvider,
        *,
        label: Optional[str] = None,
        configured: bool = True,
        models: Optional[List[str]] = None,
        builtin: bool = False,
        base_url: str = "",
        api: str = "openai-completions",
        api_key_set: bool = False,
    ) -> None:
        self._providers[provider.name] = provider
        default_model = getattr(provider, "default_model", "") or ""
        model_list = list(models or [])
        if default_model and default_model not in model_list:
            model_list.insert(0, default_model)
        self._meta[provider.name] = {
            "id": provider.name,
            "label": label or provider.name,
            "configured": configured,
            "default_model": default_model,
            "models": model_list,
            "builtin": builtin,
            "base_url": base_url,
            "api": api,
            "kind": "chat",
            "api_key_set": api_key_set,
            "source": "env" if builtin else "custom",
        }

    def get(self, name: Optional[str] = None) -> BaseModelProvider:
        key = name or self.store.default_provider or self.settings.default_model_provider
        provider = self._providers.get(key)
        if provider is None:
            raise NotFoundError(f"model provider not found: {key}")
        return provider

    def list_providers(self) -> list[str]:
        return sorted(self._providers.keys())

    def catalog(self, *, configured_only: bool = True) -> Dict[str, Any]:
        providers = []
        for name in sorted(self._providers.keys()):
            meta = dict(
                self._meta.get(name)
                or {"id": name, "label": name, "configured": True, "models": [], "builtin": False}
            )
            if configured_only and not meta.get("configured"):
                continue
            providers.append(meta)

        default_provider = self.store.default_provider or self.settings.default_model_provider
        if providers and default_provider not in {p["id"] for p in providers}:
            default_provider = providers[0]["id"]

        default_model = self.settings.default_model_name
        for p in providers:
            if p["id"] == default_provider:
                default_model = p.get("default_model") or default_model
                break

        return {
            "default_provider": default_provider,
            "default_model": default_model,
            "providers": providers,
        }

    def settings_document(self) -> Dict[str, Any]:
        """Full settings view: builtins (env) + customs (editable)."""
        builtins = []
        for name in sorted(BUILTIN_IDS):
            meta = self._meta.get(name)
            if not meta:
                continue
            builtins.append(
                {
                    **meta,
                    "editable": False,
                    "hint": "来自 .env，修改后需重启进程；自定义请新增 Provider",
                }
            )
        customs = self.store.list_public()
        embeddings = [
            ProviderStore.to_public(p) for p in self.store.providers_of_kind("embedding")
        ]
        images = [ProviderStore.to_public(p) for p in self.store.providers_of_kind("image")]
        env_embedding = None
        try:
            from src.core_kernel.plugin_runtime.knowledge_embeddings import env_embedding_public

            env_embedding = env_embedding_public()
        except Exception:
            env_embedding = None
        return {
            "default_provider": self.store.default_provider or self.settings.default_model_provider,
            "default_embedding_provider": self.store.default_embedding_provider or "",
            "default_image_provider": self.store.default_image_provider or "",
            "builtins": builtins,
            "customs": customs,
            "embeddings": embeddings,
            "images": images,
            "env_embedding": env_embedding,
        }

    def upsert_custom(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            p = self.store.upsert(data)
        except Exception as exc:
            raise ValidationAppError(str(exc)) from exc
        self.reload()
        return ProviderStore.to_public(p)

    def delete_custom(self, provider_id: str) -> None:
        if provider_id in BUILTIN_IDS:
            raise ValidationAppError("cannot delete builtin provider")
        if not self.store.delete(provider_id):
            raise NotFoundError(f"custom provider not found: {provider_id}")
        self.reload()

    def set_default_provider(self, provider_id: str, kind: str = "chat") -> Dict[str, Any]:
        k = (kind or "chat").strip().lower() or "chat"
        pid = (provider_id or "").strip()
        if k in {"embedding", "image"}:
            if pid and pid not in self.store.providers:
                raise NotFoundError(f"provider not found: {pid}")
            if pid:
                custom = self.store.providers.get(pid)
                if custom and (custom.kind or "chat") != k:
                    raise ValidationAppError(f"provider '{pid}' is kind={custom.kind}, not {k}")
            self.store.set_default(pid or None, kind=k)
            return self.settings_document()
        if pid not in self._providers and pid not in self.store.providers:
            # allow setting to builtin even if not configured
            if pid not in BUILTIN_IDS:
                raise NotFoundError(f"provider not found: {pid}")
        self.store.set_default(pid, kind="chat")
        return self.catalog(configured_only=False)
