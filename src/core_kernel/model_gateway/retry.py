"""Exponential backoff helpers for rate-limited model calls."""

from __future__ import annotations

import random
import re
from typing import Optional, Tuple

from src.common.errors import RateLimitError

_RETRYABLE_MARKERS = (
    "429",
    "rate limit",
    "too many requests",
    "当前访问人数过多",
    "请求过于频繁",
    '"code":"1305"',
    '"code": 1305',
    "1305",
)

# GLM free/flash tiers often return 429 without Retry-After; short waits just re-hit the limit.
_DEFAULT_RETRY_AFTER_SECONDS = 12.0


def is_rate_limit_message(text: str) -> bool:
    low = (text or "").lower()
    if "429" in low or "too many requests" in low or "rate limit" in low:
        return True
    # Chinese vendor messages (GLM etc.)
    for marker in _RETRYABLE_MARKERS:
        if marker.lower() in low or marker in (text or ""):
            return True
    return False


def parse_retry_after_seconds(headers: Optional[dict], body: str = "") -> Optional[float]:
    if headers:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is not None:
            try:
                return max(0.0, float(raw))
            except (TypeError, ValueError):
                pass
    # Some APIs embed wait hint in body
    m = re.search(r"retry[_ -]?after[\"'\s:=]+(\d+(?:\.\d+)?)", body or "", re.I)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def compute_backoff_seconds(
    attempt: int,
    *,
    base: float,
    maximum: float,
    retry_after: Optional[float] = None,
) -> float:
    """attempt is 0-based."""
    if retry_after is not None and retry_after > 0:
        # Slight jitter so concurrent clients don't sync-thump
        return min(maximum, retry_after + random.uniform(0.0, 1.5))
    exp = base * (2**attempt)
    jitter = random.uniform(0.0, min(2.0, base))
    return min(maximum, exp + jitter)


def raise_if_rate_limited(status_code: int, body: str, headers: Optional[dict] = None) -> None:
    if status_code == 429 or is_rate_limit_message(body):
        ra = parse_retry_after_seconds(headers, body)
        if ra is None and status_code == 429:
            # Vendor omitted Retry-After (common for open.bigmodel.cn)
            ra = _DEFAULT_RETRY_AFTER_SECONDS
        raise RateLimitError(
            body or f"HTTP {status_code}",
            retry_after=ra,
            status_code=status_code or 429,
        )


def format_retry_notice(attempt: int, max_retries: int, wait: float) -> str:
    return f"模型限流（429），{wait:.1f}s 后自动重试（第 {attempt}/{max_retries} 次）…"


def format_rate_limit_exhausted(max_retries: int) -> str:
    return (
        f"模型限流（429），已重试 {max_retries} 次仍失败。"
        "请稍后再试，或降低请求频率。"
    )


def classify_http_error(status_code: int, body: str, headers: Optional[dict] = None) -> Tuple[bool, Optional[RateLimitError]]:
    if status_code == 429 or is_rate_limit_message(body):
        ra = parse_retry_after_seconds(headers, body)
        if ra is None and status_code == 429:
            ra = _DEFAULT_RETRY_AFTER_SECONDS
        err = RateLimitError(
            body or f"HTTP {status_code}",
            retry_after=ra,
            status_code=status_code or 429,
        )
        return True, err
    return False, None
