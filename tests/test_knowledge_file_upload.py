"""Library file ingest (PDF/Office/text) vs session 512KB chips."""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.common.errors import NexusError
from src.core_kernel.knowledge_rpc import MAX_UPLOAD_BYTES, register_knowledge_rpc
from src.core_kernel.plugin_runtime.knowledge_ingest import (
    MAX_SESSION_UPLOAD_BYTES,
    library_ingest_max_bytes,
    read_bytes_as_text,
)
from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore
from src.infrastructure.storage.database import Base as AppBase


@pytest.fixture
async def store(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'kb.db').as_posix()}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(AppBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    kb = KnowledgeStore(factory)
    await kb.ensure_schema()
    yield kb
    await engine.dispose()


def test_session_cap_stays_512kb():
    assert MAX_SESSION_UPLOAD_BYTES == 512_000
    assert MAX_UPLOAD_BYTES == 512_000


def test_library_limit_env(monkeypatch):
    monkeypatch.delenv("KB_INGEST_MAX_BYTES", raising=False)
    assert library_ingest_max_bytes() == 20 * 1024 * 1024
    monkeypatch.setenv("KB_INGEST_MAX_BYTES", "4096")
    assert library_ingest_max_bytes() == 4096
    with pytest.raises(ValueError, match="file too large"):
        read_bytes_as_text(b"x" * 5000, ".txt", filename="big.txt", max_bytes=4096)


def test_session_read_rejects_over_512k():
    blob = b"a" * (MAX_SESSION_UPLOAD_BYTES + 1)
    with pytest.raises(ValueError, match="file too large"):
        read_bytes_as_text(blob, ".txt", filename="n.txt", max_bytes=MAX_SESSION_UPLOAD_BYTES)


@pytest.mark.asyncio
async def test_rpc_library_file_ingest(store):
    app = FastAPI()
    register_knowledge_rpc(app, {"session_factory": store.session_factory})
    raw = b"# Marker hello-library-upload\n\nbody"
    payload = {
        "filename": "note.md",
        "content_b64": base64.b64encode(raw).decode("ascii"),
        "workspace_id": "ws-file",
        "title": "Note",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc/knowledge/docs/file", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["title"] == "Note"
    assert data["source"].startswith("upload:")
    assert "hello-library-upload" in (data.get("content") or "")
    stored = await store.get(data["doc_id"])
    assert stored and "hello-library-upload" in stored["content"]


@pytest.mark.asyncio
async def test_rpc_library_file_too_large(store, monkeypatch):
    monkeypatch.setenv("KB_INGEST_MAX_BYTES", "1024")
    app = FastAPI()
    register_knowledge_rpc(app, {"session_factory": store.session_factory})
    raw = b"x" * 2000
    payload = {
        "filename": "big.txt",
        "content_b64": base64.b64encode(raw).decode("ascii"),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/rpc/knowledge/docs/file", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SIZE"


@pytest.mark.asyncio
async def test_adapters_multipart_and_oversize(monkeypatch):
    from src.adapters.knowledge_routes import register_knowledge_routes

    captured: dict = {}

    class Kernel:
        async def call(self, method, path, json=None, params=None):
            captured["path"] = path
            captured["json"] = json
            return {"doc_id": "upload_abc", "title": json.get("filename")}

    app = FastAPI()

    @app.exception_handler(NexusError)
    async def on_nexus(_, exc: NexusError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "error": exc.to_dict()},
        )

    register_knowledge_routes(app, {"kernel": Kernel()})
    monkeypatch.setenv("KB_INGEST_MAX_BYTES", str(20 * 1024 * 1024))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.post(
            "/api/knowledge/docs/file",
            files={"file": ("guide.txt", b"hello pdf path", "text/plain")},
            data={"workspace_id": "ws1"},
        )
        assert ok.status_code == 200
        envelope = ok.json()
        assert envelope["ok"] is True
        assert captured["path"] == "/rpc/knowledge/docs/file"
        assert captured["json"]["filename"] == "guide.txt"
        assert base64.b64decode(captured["json"]["content_b64"]) == b"hello pdf path"

        monkeypatch.setenv("KB_INGEST_MAX_BYTES", "1024")
        huge = await client.post(
            "/api/knowledge/docs/file",
            files={"file": ("huge.txt", b"y" * 2000, "text/plain")},
        )
    assert huge.status_code == 400
    err = huge.json()
    assert err["ok"] is False
    assert "too large" in str(err.get("error") or err)
