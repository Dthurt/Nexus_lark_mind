"""Feishu long-connection (WebSocket) — dedicated thread + event handler."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from src.common.config import Settings, get_settings

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict], Awaitable[None]]


def _obj_to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _obj_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_obj_to_dict(x) for x in obj]
    if hasattr(obj, "__dict__"):
        raw = {k: v for k, v in vars(obj).items() if not k.startswith("_")}
        # lark models often nest under known attrs
        return {k: _obj_to_dict(v) for k, v in raw.items()}
    return str(obj)


def p2_message_to_payload(data: Any) -> Dict[str, Any]:
    """Normalize lark P2ImMessageReceiveV1 into webhook-like dict."""
    header = getattr(data, "header", None)
    event = getattr(data, "event", None)
    message = getattr(event, "message", None) if event else None
    sender = getattr(event, "sender", None) if event else None

    sender_id = getattr(sender, "sender_id", None) if sender else None
    content = getattr(message, "content", None) if message else None
    if content is not None and not isinstance(content, str):
        content = json.dumps(_obj_to_dict(content), ensure_ascii=False)

    return {
        "header": {
            "event_id": getattr(header, "event_id", None) if header else None,
            "event_type": "im.message.receive_v1",
            "token": getattr(header, "token", None) if header else None,
            "create_time": getattr(header, "create_time", None) if header else None,
            "app_id": getattr(header, "app_id", None) if header else None,
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": getattr(sender_id, "open_id", None) if sender_id else None,
                    "user_id": getattr(sender_id, "user_id", None) if sender_id else None,
                    "union_id": getattr(sender_id, "union_id", None) if sender_id else None,
                },
                "sender_type": getattr(sender, "sender_type", None) if sender else None,
            },
            "message": {
                "message_id": getattr(message, "message_id", None) if message else None,
                "chat_id": getattr(message, "chat_id", None) if message else None,
                "chat_type": getattr(message, "chat_type", None) if message else None,
                "message_type": getattr(message, "message_type", None) if message else "text",
                "content": content or "{}",
                "mentions": _obj_to_dict(getattr(message, "mentions", None) if message else None) or [],
            },
        },
    }


def p2_card_action_to_payload(data: Any) -> Dict[str, Any]:
    """Normalize card.action.trigger into our card_action shape."""
    event = getattr(data, "event", None) or data
    operator = getattr(event, "operator", None)
    action = getattr(event, "action", None)
    value = getattr(action, "value", None) if action else None
    if value is not None and not isinstance(value, (dict, str)):
        value = _obj_to_dict(value)

    open_message_id = getattr(event, "context", None)
    msg_id = None
    if open_message_id is not None:
        msg_id = getattr(open_message_id, "open_message_id", None) or getattr(
            open_message_id, "message_id", None
        )

    return {
        "header": {"event_type": "card.action.trigger"},
        "open_message_id": msg_id or getattr(event, "open_message_id", "") or "",
        "operator": {
            "open_id": getattr(operator, "open_id", None) if operator else None,
            "user_id": getattr(operator, "user_id", None) if operator else None,
        },
        "action": {
            "value": value if isinstance(value, dict) else {"action": str(value or "noop")},
        },
    }


class FeishuLongConnection:
    """
    Runs lark.ws.Client in a dedicated OS thread with its own asyncio loop.
    (SDK calls loop.run_until_complete; cannot share uvicorn's running loop.)
    """

    def __init__(
        self,
        on_event: EventCallback,
        settings: Optional[Settings] = None,
        *,
        app_id: str = "",
        app_secret: str = "",
        use_long_connection: Optional[bool] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.on_event = on_event
        self._app_id = app_id
        self._app_secret = app_secret
        self._use_long = use_long_connection
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self.connected = False

    def _resolve_creds(self) -> tuple[str, str, bool]:
        if self._app_id and self._app_secret:
            use = True if self._use_long is None else bool(self._use_long)
            return self._app_id, self._app_secret, use
        from src.adapters.channels import resolve_feishu

        creds = resolve_feishu(self.settings)
        use = creds.use_long_connection and creds.enabled
        return creds.app_id, creds.app_secret, use

    async def start(self) -> None:
        app_id, app_secret, use_long = self._resolve_creds()
        if not (use_long and app_id and app_secret):
            logger.info("Feishu long connection disabled or unconfigured")
            return
        self._app_id = app_id
        self._app_secret = app_secret
        self._stop.clear()
        self._main_loop = asyncio.get_running_loop()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="feishu-ws",
            daemon=True,
        )
        self._thread.start()
        logger.info("Feishu long-connection thread started (app_id=%s)", app_id)

    async def stop(self) -> None:
        self._stop.set()
        # WS client blocks; daemon thread exits on process shutdown / next disconnect

    def _dispatch_async(self, payload: dict) -> None:
        if not self._main_loop or not self._main_loop.is_running():
            logger.warning("Main loop unavailable; drop feishu event")
            return
        fut = asyncio.run_coroutine_threadsafe(self.on_event(payload), self._main_loop)

        def _done(f: Any) -> None:
            try:
                f.result()
            except Exception:
                logger.exception("Feishu inbound handler failed")

        fut.add_done_callback(_done)

    def _on_message(self, data: Any) -> None:
        try:
            payload = p2_message_to_payload(data)
            logger.info(
                "Feishu message received chat=%s msg=%s",
                payload.get("event", {}).get("message", {}).get("chat_id"),
                payload.get("event", {}).get("message", {}).get("message_id"),
            )
            self._dispatch_async(payload)
        except Exception:
            logger.exception("Failed to normalize feishu message event")

    def _on_card_action(self, data: Any) -> None:
        try:
            payload = p2_card_action_to_payload(data)
            logger.info("Feishu card action received")
            self._dispatch_async(payload)
            # Card action callbacks may expect a response object; return None / empty
            return None
        except Exception:
            logger.exception("Failed to normalize feishu card action")
            return None

    def _thread_main(self) -> None:
        try:
            import lark_oapi as lark
            import lark_oapi.ws.client as lark_ws_client
            from lark_oapi.ws import Client as WSClient
        except Exception:
            logger.exception("lark-oapi WS unavailable — long connection skipped")
            return

        # Fresh event loop owned by this thread — critical for SDK.start()
        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)
        lark_ws_client.loop = ws_loop

        # Long-connection mode: builder encrypt/token must be empty strings per Feishu docs.
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .register_p2_card_action_trigger(self._on_card_action)
            .build()
        )

        while not self._stop.is_set():
            try:
                cli = WSClient(
                    self._app_id,
                    self._app_secret,
                    event_handler=event_handler,
                    log_level=lark.LogLevel.WARNING,
                )
                logger.info(
                    "Connecting Feishu WS (app_id=%s)…",
                    self._app_id,
                )
                self.connected = True
                cli.start()  # blocks until disconnect
                self.connected = False
                logger.warning("Feishu WS disconnected")
            except Exception:
                self.connected = False
                logger.exception("Feishu long connection error; retry in 5s")
            if self._stop.is_set():
                break
            time.sleep(5)

        try:
            ws_loop.stop()
            ws_loop.close()
        except Exception:
            pass
