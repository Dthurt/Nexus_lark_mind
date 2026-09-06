"""Feishu crypto helpers — verification token + optional encrypt key."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict, Optional

from src.common.errors import AuthError


def verify_token(payload: Dict[str, Any], expected: str) -> None:
    token = payload.get("token") or (payload.get("header") or {}).get("token")
    if expected and token and token != expected:
        raise AuthError("invalid feishu verification token")


def compute_signature(timestamp: str, nonce: str, encrypt_key: str, body: str) -> str:
    content = f"{timestamp}{nonce}{encrypt_key}{body}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_request_signature(
    *,
    timestamp: str,
    nonce: str,
    signature: str,
    encrypt_key: str,
    body: str,
) -> None:
    if not encrypt_key:
        return
    expected = compute_signature(timestamp, nonce, encrypt_key, body)
    if not signature or signature != expected:
        raise AuthError("invalid feishu request signature")


class AESCipher:
    """Feishu event encrypt/decrypt (AES-256-CBC). Soft dependency on pycryptodome-like API.

    For zero-extra-deps installs we support plaintext events; encrypted events require
    `cryptography` if present. Otherwise raise a clear error.
    """

    def __init__(self, encrypt_key: str) -> None:
        self.encrypt_key = encrypt_key
        self._key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()

    def decrypt(self, encrypt: str) -> Dict[str, Any]:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives.padding import PKCS7
        except ImportError as exc:
            raise AuthError(
                "encrypted Feishu events require `cryptography` package"
            ) from exc

        raw = base64.b64decode(encrypt)
        iv, ciphertext = raw[:16], raw[16:]
        cipher = Cipher(algorithms.AES(self._key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        data = unpadder.update(padded) + unpadder.finalize()
        # Feishu payload: 16-byte random + JSON + optional app_id
        content = data[16:]
        # strip trailing app_id if present — find last JSON brace
        end = content.rfind(b"}")
        if end != -1:
            content = content[: end + 1]
        return json.loads(content.decode("utf-8"))
