"""Tests for rate-limit backoff helpers."""

from src.core_kernel.model_gateway.retry import (
    compute_backoff_seconds,
    format_retry_notice,
    is_rate_limit_message,
    raise_if_rate_limited,
)
from src.common.errors import RateLimitError
import pytest


def test_detect_glm_429_body():
    body = '{"error":{"code":"1305","message":"该模型当前访问人数过多，请稍后再试"}}'
    assert is_rate_limit_message(body)
    with pytest.raises(RateLimitError):
        raise_if_rate_limited(429, body, {})


def test_backoff_grows():
    a0 = compute_backoff_seconds(0, base=1.0, maximum=32.0, retry_after=None)
    a2 = compute_backoff_seconds(2, base=1.0, maximum=32.0, retry_after=None)
    assert a0 >= 1.0
    assert a2 >= a0


def test_retry_after_honored():
    wait = compute_backoff_seconds(0, base=1.0, maximum=32.0, retry_after=5.0)
    assert 5.0 <= wait <= 7.0


def test_notice_text():
    msg = format_retry_notice(1, 5, 2.0)
    assert "429" in msg
    assert "1/5" in msg
