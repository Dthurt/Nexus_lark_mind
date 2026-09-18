"""Optional OpenAI-compatible embeddings for hybrid KB search.

Configure via env (no default deps beyond httpx):

  KB_EMBEDDING_BASE_URL  — OpenAI / vLLM / any /v1 embeddings shim
  KB_EMBEDDING_MODEL     — embedding model id
  KB_EMBEDDING_API_KEY   — bearer token (optional if endpoint is open)
  KB_EMBEDDING_DIM       — Matryoshka truncate + L2 re-normalize (WeMM-style)
  KB_EMBEDDING_ENABLED   — set to 0/false to force-disable even when URL is set

WeMM (WeChat Multi-Modal Embedding) is an optional alias, not a hard dep:

  WEMM_BASE_URL          — e.g. http://127.0.0.1:8000/v1  (vLLM pooling / SGLang)
  WEMM_MODEL             — WeMM-Embedding-2B / 4B / 9B
  WEMM_API_KEY           — optional
  WEMM_DIM               — alias for KB_EMBEDDING_DIM (64..4096)

When unset, callers degrade to keyword-only search. Image embed is only
attempted when the backend is WeMM (or KB_EMBEDDING_MULTIMODAL=1).
"""

from __future__ import annotations

import base64
import json
import logging
import math
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import httpx

logger = logging.getLogger(__name__)

_WEMM_DEFAULT_MODEL = "WeMM-Embedding-2B"
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _env_flag_off(name: str) -> bool:
    return _env(name).lower() in {"0", "false", "no", "off"}


def _env_flag_on(name: str) -> bool:
    return _env(name).lower() in {"1", "true", "yes", "on"}


def embedding_base_url() -> str:
    """Prefer explicit KB_EMBEDDING_*; WEMM then GLM/OpenAI chat keys as fallback."""
    explicit = (_env("KB_EMBEDDING_BASE_URL") or _env("WEMM_BASE_URL")).rstrip("/")
    if explicit:
        return explicit
    glm_base = _env("GLM_BASE_URL").rstrip("/")
    if _env("GLM_API_KEY"):
        return glm_base or "https://open.bigmodel.cn/api/paas/v4"
    openai_base = _env("OPENAI_BASE_URL").rstrip("/")
    if _env("OPENAI_API_KEY"):
        return openai_base or "https://api.openai.com/v1"
    return ""


def embeddings_configured() -> bool:
    if _env_flag_off("KB_EMBEDDING_ENABLED"):
        return False
    return bool(embedding_base_url())


def embedding_backend() -> str:
    """Logical backend name for stats / image routing. Never a hard import."""
    if not embeddings_configured():
        return ""
    if _env("WEMM_BASE_URL") or "wemm" in embedding_base_url().lower():
        return "wemm"
    if _env("GLM_API_KEY") and not _env("KB_EMBEDDING_BASE_URL"):
        return "glm"
    return "openai"


def embedding_model() -> str:
    explicit = _env("KB_EMBEDDING_MODEL") or _env("WEMM_MODEL")
    if explicit:
        return explicit
    if embedding_backend() == "wemm":
        return _WEMM_DEFAULT_MODEL
    if embedding_backend() == "glm":
        return "embedding-3"
    return "text-embedding-3-small"


def embedding_api_key() -> str:
    return (
        _env("KB_EMBEDDING_API_KEY")
        or _env("WEMM_API_KEY")
        or _env("GLM_API_KEY")
        or _env("OPENAI_API_KEY")
    )


def embedding_dim() -> int:
    raw = _env("KB_EMBEDDING_DIM") or _env("WEMM_DIM")
    if not raw:
        return 0
    try:
        n = int(raw)
    except ValueError:
        return 0
    return n if n > 0 else 0


def multimodal_embeddings_enabled() -> bool:
    """Image/doc vectors only when WeMM is configured or explicitly opted in."""
    if not embeddings_configured():
        return False
    if _env_flag_off("KB_EMBEDDING_MULTIMODAL"):
        return False
    if embedding_backend() == "wemm":
        return True
    return _env_flag_on("KB_EMBEDDING_MULTIMODAL")


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


def l2_normalize(vec: Sequence[float]) -> List[float]:
    acc = 0.0
    out = [float(x) for x in vec]
    for x in out:
        acc += x * x
    if acc <= 0.0:
        return out
    scale = 1.0 / math.sqrt(acc)
    return [x * scale for x in out]


def apply_embedding_dim(vec: Sequence[float], dim: Optional[int] = None) -> List[float]:
    """WeMM Matryoshka: truncate to d then L2-normalize again."""
    values = [float(x) for x in vec]
    n = int(dim if dim is not None else embedding_dim())
    if n > 0 and len(values) > n:
        values = values[:n]
        return l2_normalize(values)
    return values


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


def _embeddings_urls(base: str) -> List[str]:
    b = (base or "").rstrip("/")
    if not b:
        return []
    urls = [f"{b}/embeddings"]
    if b.endswith("/v1"):
        urls.append(f"{b[:-3].rstrip('/')}/embeddings")
    else:
        urls.append(f"{b}/v1/embeddings")
    seen: set[str] = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _auth_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = embedding_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _parse_embedding_rows(body: Any, n: int) -> Optional[List[List[float]]]:
    if not isinstance(body, dict):
        return None
    rows = body.get("data") or body.get("embeddings") or []
    if isinstance(rows, list) and rows and isinstance(rows[0], list):
        # Bare [[float, ...], ...]
        if len(rows) < n:
            return None
        return [apply_embedding_dim(r) for r in rows[:n]]
    by_idx: Dict[int, Any] = {}
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if isinstance(row, dict):
            by_idx[int(row.get("index", i))] = row.get("embedding")
        elif isinstance(row, list):
            by_idx[i] = row
    out: List[List[float]] = []
    for i in range(n):
        emb = by_idx.get(i)
        if not isinstance(emb, list) or not emb:
            return None
        out.append(apply_embedding_dim(emb))
    return out


async def _post_embeddings(payload: Dict[str, Any], *, n: int) -> Optional[List[List[float]]]:
    base = embedding_base_url()
    if not base:
        return None
    headers = _auth_headers()
    last_exc: Optional[Exception] = None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for url in _embeddings_urls(base):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 404:
                        last_exc = httpx.HTTPStatusError(
                            "404", request=resp.request, response=resp
                        )
                        continue
                    resp.raise_for_status()
                    parsed = _parse_embedding_rows(resp.json(), n)
                    if parsed is not None:
                        return parsed
                    last_exc = ValueError("embedding response missing data")
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    if exc.response is not None and exc.response.status_code == 404:
                        continue
                    break
                except Exception as exc:
                    last_exc = exc
                    break
    except Exception as exc:
        last_exc = exc
    if last_exc is not None:
        logger.warning("KB embedding request failed: %s", last_exc)
    return None


async def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Return embeddings for each text, or None if disabled / request failed."""
    if not embeddings_configured() or not texts:
        return None
    payload: Dict[str, Any] = {"model": embedding_model(), "input": texts}
    return await _post_embeddings(payload, n=len(texts))


async def embed_one(text: str) -> Optional[List[float]]:
    result = await embed_texts([text])
    if not result:
        return None
    return result[0]


def _image_data_uri(path: Union[str, Path]) -> Optional[str]:
    p = Path(path)
    if not p.is_file():
        return None
    suffix = p.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        return None
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    if len(raw) > 8_000_000:
        logger.warning("KB image embed skipped (too large): %s", p)
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _image_input_payload(data_uri: str) -> Any:
    return {"type": "image_url", "image_url": {"url": data_uri}}


async def embed_images(paths: List[Union[str, Path]]) -> Optional[List[Optional[List[float]]]]:
    """Embed local image files via WeMM / multimodal OpenAI-compatible endpoint.

    Returns one vector per path, or None on total failure. Individual missing
    files become None slots. No-ops (returns None) when multimodal is off.
    """
    if not multimodal_embeddings_enabled() or not paths:
        return None
    inputs: List[Any] = []
    keep: List[int] = []
    for i, path in enumerate(paths):
        uri = _image_data_uri(path)
        if not uri:
            continue
        inputs.append(_image_input_payload(uri))
        keep.append(i)
    if not inputs:
        return [None] * len(paths)
    vectors = await _post_embeddings(
        {"model": embedding_model(), "input": inputs},
        n=len(inputs),
    )
    if not vectors:
        return None
    out: List[Optional[List[float]]] = [None] * len(paths)
    for slot, vec in zip(keep, vectors):
        out[slot] = vec
    return out


async def embed_one_image(path: Union[str, Path]) -> Optional[List[float]]:
    rows = await embed_images([path])
    if not rows:
        return None
    return rows[0]


def embedding_stats() -> Dict[str, Any]:
    return {
        "configured": embeddings_configured(),
        "backend": embedding_backend(),
        "model": embedding_model() if embeddings_configured() else "",
        "dim": embedding_dim(),
        "multimodal": multimodal_embeddings_enabled(),
    }
