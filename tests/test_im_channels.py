"""Tests for DingTalk / WeCom event parsing and IM crypto roundtrip."""

from __future__ import annotations

import base64

from src.adapters import im_crypto
from src.adapters.dingtalk.events import classify_payload, parse_robot_message
from src.adapters.wecom.events import classify_xml, parse_xml


def test_dingtalk_robot_message_parse():
    payload = {
        "msgtype": "text",
        "text": {"content": "@bot 帮我写个脚本"},
        "senderStaffId": "u001",
        "conversationId": "cid-1",
        "conversationType": "2",
        "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=abc",
        "msgId": "m1",
    }
    msg = parse_robot_message(payload)
    assert msg is not None
    assert "脚本" in msg.text
    assert msg.user_id == "u001"
    kind, data = classify_payload(payload)
    assert kind == "message"
    assert data.session_webhook.endswith("abc")


def test_wecom_text_xml():
    xml = """<xml>
<ToUserName><![CDATA[ww]]></ToUserName>
<FromUserName><![CDATA[ZhangSan]]></FromUserName>
<CreateTime>1348831860</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[hello https://example.com]]></Content>
<MsgId>1234567890123456</MsgId>
<AgentID>1000002</AgentID>
</xml>"""
    fields = parse_xml(xml)
    kind, msg = classify_xml(fields)
    assert kind == "message"
    assert msg.user_id == "ZhangSan"
    assert "example.com" in msg.text


def test_im_crypto_roundtrip():
    # 43-char EncodingAESKey → 32-byte key
    key = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii").rstrip("=")
    assert len(key) == 43
    plain = "<xml><Content>ping</Content></xml>"
    enc = im_crypto.encrypt_payload(encoding_aes_key=key, receive_id="corp", plaintext=plain)
    out = im_crypto.decrypt_payload(encoding_aes_key=key, receive_id="corp", encrypt_b64=enc)
    assert out == plain
    sig = im_crypto.sha1_signature("tok", "1", "n", enc)
    assert im_crypto.verify_signature(
        token="tok", timestamp="1", nonce="n", encrypt=enc, signature=sig
    )
