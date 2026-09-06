"""Provider registry — add vendors without touching business code."""

from __future__ import annotations

from typing import Dict, Optional

from src.common.config import Settings, get_settings
from src.common.errors import NotFoundError
from src.core_kernel.model_gateway.anthropic import AnthropicProvider
from src.core_kernel.model_gateway.base import BaseModelProvider
from src.core_kernel.model_gateway.openai_compat import OpenAICompatProvider


class ProviderRegistry:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._providers: Dict[str, BaseModelProvider] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(
            OpenAICompatProvider(
                name="openai",
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                default_model="gpt-4o-mini",
                settings=self.settings,
            )
        )
        self.register(
            OpenAICompatProvider(
                name="deepseek",
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                default_model="deepseek-chat",
                settings=self.settings,
            )
        )
        self.register(
            OpenAICompatProvider(
                name="glm",
                api_key=self.settings.glm_api_key,
                base_url=self.settings.glm_base_url,
                default_model=self.settings.glm_default_model or self.settings.default_model_name,
                settings=self.settings,
            )
        )
        self.register(AnthropicProvider(self.settings))

    def register(self, provider: BaseModelProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: Optional[str] = None) -> BaseModelProvider:
        key = name or self.settings.default_model_provider
        provider = self._providers.get(key)
        if provider is None:
            raise NotFoundError(f"model provider not found: {key}")
        return provider

    def list_providers(self) -> list[str]:
        return sorted(self._providers.keys())
