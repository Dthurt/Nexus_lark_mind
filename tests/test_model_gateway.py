"""Model gateway registry tests."""

from src.core_kernel.model_gateway.registry import ProviderRegistry


def test_default_providers_registered():
    registry = ProviderRegistry()
    names = registry.list_providers()
    assert "openai" in names
    assert "deepseek" in names
    assert "glm" in names
    assert "anthropic" in names


def test_get_default_provider():
    registry = ProviderRegistry()
    provider = registry.get("openai")
    assert provider.name == "openai"
