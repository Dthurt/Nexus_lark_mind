"""Settings embedding providers sit on top of env KB_EMBEDDING_* fallback."""

from __future__ import annotations

from src.core_kernel.model_gateway.provider_store import ProviderStore
from src.core_kernel.plugin_runtime import knowledge_embeddings as ke
from src.core_kernel.plugin_runtime.knowledge_scope import is_all_local_kbs, local_kb_match_values


def _store(tmp_path):
    return ProviderStore(path=tmp_path / "model_providers.json")


def test_resolve_prefers_settings_default_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "http://env.test/v1")
    monkeypatch.setenv("KB_EMBEDDING_MODEL", "env-model")
    monkeypatch.delenv("KB_EMBEDDING_ENABLED", raising=False)
    store = _store(tmp_path)
    store.upsert(
        {
            "id": "my-emb",
            "label": "My Embed",
            "kind": "embedding",
            "base_url": "http://settings.test/v1",
            "api_key": "sk-test-key",
            "default_model": "settings-embed",
            "models": ["settings-embed"],
            "enabled": True,
        }
    )
    store.set_default("my-emb", kind="embedding")
    ep = ke.resolve_embedding_endpoint(store=store)
    assert ep is not None
    assert ep.source == "settings"
    assert ep.model == "settings-embed"
    assert ep.base_url == "http://settings.test/v1"
    assert ep.provider_id == "my-emb"


def test_resolve_explicit_provider_overrides_default(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "http://env.test/v1")
    monkeypatch.setenv("KB_EMBEDDING_MODEL", "env-model")
    monkeypatch.delenv("KB_EMBEDDING_ENABLED", raising=False)
    store = _store(tmp_path)
    store.upsert(
        {
            "id": "emb-a",
            "kind": "embedding",
            "base_url": "http://a.test/v1",
            "api_key": "sk-a",
            "default_model": "model-a",
            "enabled": True,
        }
    )
    store.upsert(
        {
            "id": "emb-b",
            "kind": "embedding",
            "base_url": "http://b.test/v1",
            "api_key": "sk-b",
            "default_model": "model-b",
            "enabled": True,
        }
    )
    store.set_default("emb-a", kind="embedding")
    ep = ke.resolve_embedding_endpoint("emb-b", store=store)
    assert ep is not None
    assert ep.provider_id == "emb-b"
    assert ep.model == "model-b"


def test_resolve_falls_back_to_env_without_settings_default(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "http://env.test/v1")
    monkeypatch.setenv("KB_EMBEDDING_MODEL", "env-model")
    monkeypatch.delenv("KB_EMBEDDING_ENABLED", raising=False)
    store = _store(tmp_path)
    store.upsert(
        {
            "id": "emb-idle",
            "kind": "embedding",
            "base_url": "http://idle.test/v1",
            "api_key": "sk-idle",
            "default_model": "idle-model",
            "enabled": True,
        }
    )
    ep = ke.resolve_embedding_endpoint(store=store)
    assert ep is not None
    assert ep.source == "env"
    assert ep.model == "env-model"


def test_disabled_flag_still_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "http://env.test/v1")
    monkeypatch.setenv("KB_EMBEDDING_ENABLED", "0")
    store = _store(tmp_path)
    store.upsert(
        {
            "id": "my-emb",
            "kind": "embedding",
            "base_url": "http://settings.test/v1",
            "api_key": "sk-test-key",
            "default_model": "settings-embed",
            "enabled": True,
        }
    )
    store.set_default("my-emb", kind="embedding")
    assert ke.resolve_embedding_endpoint(store=store) is None
    assert ke.embeddings_configured() is False


def test_chat_kind_is_default_and_not_embedding(tmp_path):
    store = _store(tmp_path)
    p = store.upsert(
        {
            "id": "chat-proxy",
            "kind": "chat",
            "base_url": "http://chat.test/v1",
            "api_key": "sk-chat",
            "default_model": "gpt-mini",
            "enabled": True,
        }
    )
    assert p.kind == "chat"
    assert store.providers_of_kind("embedding") == []
    assert store.providers_of_kind("chat")[0].id == "chat-proxy"


def test_all_local_kb_scope_helpers():
    assert is_all_local_kbs("local:all")
    assert is_all_local_kbs("all")
    assert not is_all_local_kbs("")
    assert not is_all_local_kbs("local:default")
    assert local_kb_match_values("") == ["", "local:default"]


def test_chat_catalog_excludes_embedding_and_image(tmp_path, monkeypatch):
    from src.common.config import Settings
    from src.core_kernel.model_gateway.registry import ProviderRegistry

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    store = _store(tmp_path)
    store.upsert(
        {
            "id": "only-emb",
            "kind": "embedding",
            "base_url": "http://emb.test/v1",
            "api_key": "sk-emb",
            "default_model": "emb-1",
            "enabled": True,
        }
    )
    store.upsert(
        {
            "id": "only-img",
            "kind": "image",
            "base_url": "http://img.test/v1",
            "api_key": "sk-img",
            "default_model": "dall-e-3",
            "enabled": True,
        }
    )
    store.upsert(
        {
            "id": "only-chat",
            "kind": "chat",
            "base_url": "http://chat.test/v1",
            "api_key": "sk-chat",
            "default_model": "chat-1",
            "enabled": True,
        }
    )
    reg = ProviderRegistry(settings=Settings(), store=store)
    ids = {p["id"] for p in reg.catalog(configured_only=False)["providers"]}
    assert "only-chat" in ids
    assert "only-emb" not in ids
    assert "only-img" not in ids
    doc = reg.settings_document()
    assert any(p["id"] == "only-emb" for p in doc["embeddings"])
    assert any(p["id"] == "only-img" for p in doc["images"])
