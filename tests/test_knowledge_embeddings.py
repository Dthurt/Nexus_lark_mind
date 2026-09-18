"""WeMM / OpenAI-compatible embedding backend tests (no live network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core_kernel.plugin_runtime import knowledge_embeddings as ke
from src.core_kernel.plugin_runtime.knowledge_query import (
    expand_queries,
    merge_hits_by_id,
    should_expand,
)


def test_wemm_alias_configures_backend(monkeypatch):
    monkeypatch.delenv("KB_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("KB_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("WEMM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("WEMM_MODEL", "WeMM-Embedding-2B")
    monkeypatch.setenv("WEMM_DIM", "256")
    monkeypatch.delenv("KB_EMBEDDING_ENABLED", raising=False)
    assert ke.embeddings_configured() is True
    assert ke.embedding_backend() == "wemm"
    assert ke.embedding_model() == "WeMM-Embedding-2B"
    assert ke.embedding_dim() == 256
    assert ke.multimodal_embeddings_enabled() is True


def test_kb_url_wins_over_wemm_for_base(monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("WEMM_BASE_URL", "http://127.0.0.1:8000/v1")
    assert ke.embedding_base_url() == "https://api.openai.com/v1"
    assert ke.embedding_backend() == "wemm"  # WEMM_* still marks multimodal backend


def test_disabled_flag_degrades(monkeypatch):
    monkeypatch.setenv("WEMM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("KB_EMBEDDING_ENABLED", "0")
    assert ke.embeddings_configured() is False
    assert ke.embedding_backend() == ""


def test_matryoshka_truncate_renormalizes():
    vec = [3.0, 4.0, 0.0, 1.0]
    out = ke.apply_embedding_dim(vec, 2)
    assert len(out) == 2
    # 3-4-5 triangle → unit vector
    assert abs(out[0] - 0.6) < 1e-9
    assert abs(out[1] - 0.8) < 1e-9


def test_embeddings_urls_try_v1_and_bare():
    urls = ke._embeddings_urls("http://host:8000/v1")
    assert "http://host:8000/v1/embeddings" in urls
    urls2 = ke._embeddings_urls("http://host:8000")
    assert "http://host:8000/embeddings" in urls2
    assert "http://host:8000/v1/embeddings" in urls2


@pytest.mark.asyncio
async def test_embed_texts_404_falls_back_to_v1(monkeypatch):
    monkeypatch.setenv("KB_EMBEDDING_BASE_URL", "http://embed.test")
    monkeypatch.setenv("KB_EMBEDDING_MODEL", "demo")
    monkeypatch.delenv("KB_EMBEDDING_ENABLED", raising=False)

    calls = []

    class FakeResp:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload
            self.request = None

        def raise_for_status(self):
            if self.status_code >= 400:
                import httpx

                raise httpx.HTTPStatusError(
                    "err", request=httpx.Request("POST", "http://x"), response=self
                )

        def json(self):
            return self._payload

    async def fake_post(url, headers=None, json=None):
        calls.append(url)
        if url.endswith("/embeddings") and "/v1/" not in url:
            return FakeResp(404, {})
        return FakeResp(
            200,
            {"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}]},
        )

    client = MagicMock()
    client.post = AsyncMock(side_effect=fake_post)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(ke.httpx, "AsyncClient", return_value=client):
        out = await ke.embed_texts(["hello"])
    assert out == [[1.0, 0.0, 0.0]]
    assert any("/v1/embeddings" in u for u in calls)


@pytest.mark.asyncio
async def test_embed_texts_degrades_on_error(monkeypatch):
    monkeypatch.setenv("WEMM_BASE_URL", "http://down.invalid")
    with patch.object(ke.httpx, "AsyncClient", side_effect=RuntimeError("no net")):
        assert await ke.embed_texts(["hello"]) is None


@pytest.mark.asyncio
async def test_embed_images_noop_without_wemm(monkeypatch, tmp_path):
    monkeypatch.delenv("WEMM_BASE_URL", raising=False)
    monkeypatch.delenv("KB_EMBEDDING_BASE_URL", raising=False)
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    assert await ke.embed_images([img]) is None


def test_expand_queries_strips_question_and_stopwords():
    variants = expand_queries("what is knowledge retrieval architecture")
    assert variants
    joined = " ".join(variants).lower()
    assert "knowledge" in joined or "architecture" in joined
    assert not any(v.lower().startswith("what is") for v in variants)
    zh = expand_queries("\u4ec0\u4e48\u662f\u77e5\u8bc6\u5e93\u68c0\u7d22")
    assert zh
    assert not any(v.startswith("\u4ec0\u4e48\u662f") for v in zh)


def test_should_expand_and_merge():
    assert should_expand(0, 8) is True
    assert should_expand(8, 8) is False
    merged = merge_hits_by_id(
        [{"chunk_id": "a", "score": 1.0}],
        [{"chunk_id": "a", "score": 3.0}, {"chunk_id": "b", "score": 2.0}],
        limit=2,
    )
    assert merged[0]["chunk_id"] == "a"
    assert merged[0]["score"] == 3.0
    assert merged[1]["chunk_id"] == "b"
