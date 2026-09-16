"""Optional OpenAI-compatible embeddings for hybrid KB search.

Configure via env (no default deps beyond httpx):
  KB_EMBEDDING_BASE_URL  — e.g. https://api.openai.com/v1 or a WeMM/vLLM OpenAI shim
  KB_EMBEDDING_MODEL     — embedding model id
  KB_EMBEDDING_API_KEY   — bearer token (optional if endpoint is open)
  KB_EMBEDDING_DIM       — expected dim (informational; stored vectors are variable)
  KB_EMBEDDING_ENABLED   — set to 0/false to force-disable even when URL is set

When unset, callers degrade to keyword-only search.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)


def embeddings_configured() -> bool:
    if _env_flag_off("KB_EMBEDDING_ENABLED"):
        return False
    return bool((os.getenv("KB_EMBEDDING_BASE_URL") or "").strip())


def _env_flag_off(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"0", "false", "no", "off"}


def embedding_model() -> str:
    return (os.getenv("KB_EMBEDDING_MODEL") or "text-embedding-3-small").strip()


def serialize_embedding(vec: Sequence[float]) -> str:
    return json.dumps([float(x) for x in vec], separators=(",", ":"))


def deserialize_embedding(raw: Optional[str]) -> Optional[List[float]]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, list) and data:
            return [float(x) for x in data]
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        fx = float(x)
        fy = float(y)
        dot += fx * fy
        na += fx * fx
        nb += fy * fy
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Return embeddings for each text, or None if disabled / request failed."""
    if not embeddings_configured() or not texts:
        return None
    base = (os.getenv("KB_EMBEDDING_BASE_URL") or "").strip().rstrip("/")
    model = embedding_model()
    api_key = (os.getenv("KB_EMBEDDING_API_KEY") or "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = f"{base}/embeddings"
    payload = {"model": model, "input": texts}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()
        rows = body.get("data") or []
        # OpenAI returns objects with index + embedding
        by_idx = {int(r.get("index", i)): r.get("embedding") for i, r in enumerate(rows)}
        out: List[List[float]] = []
        for i in range(len(texts)):
            emb = by_idx.get(i)
            if not isinstance(emb, list):
                return None
            out.append([float(x) for x in emb])
        return out
    except Exception as exc:
        logger.warning("KB embedding request failed: %s", exc)
        return None


async def embed_one(text: str) -> Optional[List[float]]:
    result = await embed_texts([text])
    if not result:
        return None
    return result[0]
