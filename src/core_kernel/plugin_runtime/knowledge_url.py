"""SSRF-safe HTTP(S) fetch for local knowledge-base URL ingest."""

from __future__ import annotations

import ipaddress
import socket
from typing import Tuple
from urllib.parse import urljoin, urlparse

import httpx

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "metadata.google.internal",
    "metadata.goog",
    "metadata",
}
_MAX_REDIRECTS = 4
_TIMEOUT = 25.0


def _host_blocked(host: str) -> str:
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return "empty host"
    if h in _BLOCKED_HOSTS or h.endswith(".localhost") or h.endswith(".internal"):
        return f"blocked host: {h}"
    if h.endswith(".local"):
        return f"blocked host: {h}"
    try:
        ip = ipaddress.ip_address(h)
        if _ip_blocked(ip):
            return f"blocked address: {h}"
        return ""
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(h, None)
    except OSError as exc:
        return f"DNS failed: {exc}"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_blocked(ip):
            return f"blocked address: {addr}"
    return ""


def _ip_blocked(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("169.254.0.0/16"))
        or (ip.version == 6 and ip in ipaddress.ip_network("fc00::/7"))
    )


def validate_ingest_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("url required")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("only http(s) URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("URLs with credentials are not allowed")
    host = parsed.hostname or ""
    reason = _host_blocked(host)
    if reason:
        raise ValueError(reason)
    return raw


async def fetch_ingest_url(url: str, *, max_bytes: int) -> Tuple[bytes, str, str]:
    """Return ``(body, content_type, final_url)``. Raises ValueError on reject."""
    current = validate_ingest_url(url)
    headers = {
        "User-Agent": "NexusLarkMind-KB/1.0",
        "Accept": "text/html,application/pdf,text/plain,application/xhtml+xml,*/*;q=0.8",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            validate_ingest_url(current)
            resp = await client.get(current, headers=headers)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = (resp.headers.get("location") or "").strip()
                if not loc:
                    raise ValueError("redirect without Location")
                current = urljoin(current, loc)
                continue
            resp.raise_for_status()
            body = resp.content or b""
            if len(body) > max_bytes:
                raise ValueError(f"URL body too large ({len(body)} bytes, max {max_bytes})")
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            return body, ctype, str(resp.url)
    raise ValueError("too many redirects")


def suffix_for_url(url: str, content_type: str, filename: str = "") -> str:
    from pathlib import Path

    if filename:
        suf = Path(filename).suffix.lower()
        if suf:
            return suf
    path = urlparse(url).path.lower()
    suf = Path(path).suffix.lower()
    if suf in {".pdf", ".md", ".txt", ".html", ".htm", ".docx", ".xlsx", ".pptx", ".rst", ".org"}:
        return suf
    ctype = (content_type or "").lower()
    if "pdf" in ctype:
        return ".pdf"
    if "html" in ctype:
        return ".html"
    if "markdown" in ctype:
        return ".md"
    if ctype.startswith("text/"):
        return ".txt"
    return ".html"
