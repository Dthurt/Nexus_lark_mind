"""Recorded WeKnora HTTP fixtures — no live server required.

Installs an httpx MockTransport that:
  * records method, path, headers, and JSON body
  * serves canned JSON from tests/fixtures/weknora/canned.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "weknora"
CANNED_PATH = FIXTURE_DIR / "canned.json"


def load_canned() -> Dict[str, Any]:
    return json.loads(CANNED_PATH.read_text(encoding="utf-8"))


class WeknoraHttpRecorder:
    def __init__(self, canned: Optional[Dict[str, Any]] = None) -> None:
        self.canned = canned or load_canned()
        self.requests: List[Dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        path = parsed.path
        body: Any = None
        if request.content:
            try:
                body = json.loads(request.content.decode("utf-8"))
            except Exception:
                body = request.content.decode("utf-8", errors="replace")
        headers = {k: v for k, v in request.headers.items()}
        self.requests.append(
            {
                "method": request.method.upper(),
                "url": str(request.url),
                "path": path,
                "headers": headers,
                "body": body,
            }
        )
        payload, status = self._payload_for(request.method.upper(), path)
        return httpx.Response(status, json=payload)

    def _payload_for(self, method: str, path: str) -> tuple[Dict[str, Any], int]:
        if path.rstrip("/").endswith("/knowledge-search") and method == "POST":
            return self.canned["knowledge_search"], 200
        if path.rstrip("/").endswith("/knowledge/manual") and method == "POST":
            return self.canned["knowledge_manual"], 200
        if path.rstrip("/").endswith("/knowledge") and method == "GET":
            return self.canned["knowledge_list"], 200
        if path.rstrip("/").endswith("/knowledge-bases") and method == "GET":
            return self.canned["knowledge_bases"], 200
        if path.rstrip("/").endswith("/health") or path.rstrip("/").endswith("/system/info"):
            return {"ok": True}, 200
        return {"error": f"unhandled fixture {method} {path}"}, 404

    def assert_auth(self, rec: Dict[str, Any], api_key: str) -> None:
        headers = rec["headers"]
        auth = headers.get("authorization") or headers.get("Authorization") or ""
        xkey = headers.get("x-api-key") or headers.get("X-API-Key") or ""
        assert auth == f"Bearer {api_key}", auth
        assert xkey == api_key, xkey

    def find(self, method: str, path_substr: str) -> Dict[str, Any]:
        for rec in self.requests:
            if rec["method"] == method.upper() and path_substr in rec["path"]:
                return rec
        raise AssertionError(
            f"no recorded {method} containing {path_substr!r}; saw "
            f"{[(r['method'], r['path']) for r in self.requests]}"
        )


def install_weknora_http_fixtures(monkeypatch, recorder: Optional[WeknoraHttpRecorder] = None):
    """Patch weknora_client.httpx.AsyncClient to use the canned transport."""
    rec = recorder or WeknoraHttpRecorder()
    transport = httpx.MockTransport(rec.handler)

    class FixtureAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("transport", transport)
            super().__init__(*args, **kwargs)

    from src.core_kernel.plugin_runtime import weknora_client as wc

    monkeypatch.setattr(wc.httpx, "AsyncClient", FixtureAsyncClient)
    return rec
