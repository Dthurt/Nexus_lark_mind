"""Shared PKCS7 + AES-CBC helpers used by WeCom / DingTalk style callbacks."""

from __future__ import annotations

import base64
import hashlib
import logging
import socket
import struct
import time
from typing import Tuple

logger = logging.getLogger(__name__)


def _aes_key_from_encoding(encoding_aes_key: str) -> bytes:
    # WeCom / DingTalk: EncodingAESKey is 43 chars; append '=' then base64-decode → 32 bytes.
    return base64.b64decode(encoding_aes_key.strip() + "=")


def sha1_signature(*parts: str) -> str:
    raw = "".join(sorted(parts))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def encrypt_payload(*, encoding_aes_key: str, receive_id: str, plaintext: str) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    key = _aes_key_from_encoding(encoding_aes_key)
    iv = key[:16]
    text = plaintext.encode("utf-8")
    random16 = (str(time.time_ns())[-16:]).encode("utf-8")[:16]
    if len(random16) < 16:
        random16 = (random16 + b"0000000000000000")[:16]
    msg_len = struct.pack("!I", len(text))
    body = random16 + msg_len + text + (receive_id or "").encode("utf-8")
    padder = PKCS7(128).padder()
    padded = padder.update(body) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


def decrypt_payload(*, encoding_aes_key: str, receive_id: str, encrypt_b64: str) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    key = _aes_key_from_encoding(encoding_aes_key)
    iv = key[:16]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(base64.b64decode(encrypt_b64)) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    decrypted = unpadder.update(padded) + unpadder.finalize()
    content = decrypted[16:]
    xml_len = socket.ntohl(struct.unpack("I", content[:4])[0])
    xml_content = content[4 : 4 + xml_len].decode("utf-8")
    from_receive_id = content[4 + xml_len :].decode("utf-8")
    if receive_id and from_receive_id and from_receive_id != receive_id:
        logger.warning("IM crypto receive_id mismatch expected=%s got=%s", receive_id, from_receive_id)
    return xml_content


def verify_signature(*, token: str, timestamp: str, nonce: str, encrypt: str, signature: str) -> bool:
    if not token:
        return True
    if not signature:
        return False
    expected = sha1_signature(token, timestamp, nonce, encrypt)
    return expected == signature


def pack_encrypted_response(
    *,
    token: str,
    encoding_aes_key: str,
    receive_id: str,
    plaintext: str,
    nonce: str = "",
) -> Tuple[str, str, str, str]:
    encrypt = encrypt_payload(
        encoding_aes_key=encoding_aes_key,
        receive_id=receive_id,
        plaintext=plaintext,
    )
    timestamp = str(int(time.time()))
    use_nonce = nonce or timestamp[-8:]
    signature = sha1_signature(token, timestamp, use_nonce, encrypt)
    return encrypt, signature, timestamp, use_nonce
