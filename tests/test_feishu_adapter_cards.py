"""Feishu adapter card streaming / conversation actions — mocked client."""

from __future__ import annotations

import asyncio

from src.adapters.feishu.adapter import FeishuAdapter, STREAM_DEBOUNCE_S
from src.adapters.feishu.cards import card_elements, card_plain_text, iter_card_actions, iter_select_options
from src.common.schemas import BusEvent, ChannelType, EventType, StandardTask


class _FakeRpc:
    def __init__(self) -> None:
        self.calls = []

    async def call(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/rpc/sessions":
            return {"session_id": "feishu:oc_1:ou_1", "model_provider": "glm", "model_name": "x"}
        if path.startswith("/rpc/sessions/"):
            return {"model_provider": "glm", "model_name": "x"}
        return {}


class _FakeClient:
    def __init__(self) -> None:
        self.sends = []
        self.updates = []

    async def send_card_to_chat(self, chat_id, card):
        mid = f"om_{len(self.sends) + 1}"
        self.sends.append((chat_id, card, mid))
        return {"code": 0, "data": {"message_id": mid}}

    async def update_message_card(self, message_id, card):
        self.updates.append((message_id, card))
        return {"code": 0}


def _adapter() -> FeishuAdapter:
    ad = FeishuAdapter(_FakeRpc(), redis_client=None)  # type: ignore[arg-type]
    ad.client = _FakeClient()
    ad.kernel = _FakeRpc()
    return ad


def test_deltas_are_debounced_then_final_card():
    ad = _adapter()

    async def _run():
        task = StandardTask(
            session_id="feishu:oc_1:ou_1",
            channel=ChannelType.FEISHU,
            user_id="ou_1",
            content="你好",
        )
        await ad._seed_turn_card(task, chat_id="oc_1", user_text="你好")
        tid = task.task_id
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_DELTA,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"delta": "你", "content_so_far": "你"},
            )
        )
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_DELTA,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"delta": "好", "content_so_far": "你好"},
            )
        )
        mid_updates = len(ad.client.updates)
        await asyncio.sleep(STREAM_DEBOUNCE_S + 0.15)
        after_debounce = len(ad.client.updates)
        assert after_debounce >= 1
        assert after_debounce - mid_updates <= 2
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_COMPLETED,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"content": "你好世界"},
            )
        )
        final = ad.client.updates[-1][1]
        assert final["schema"] == "2.0"
        assert final["config"]["streaming_mode"] is False
        joined = card_plain_text(final)
        assert "你好世界" in joined
        actions = {a["action"] for a in iter_card_actions(final)}
        assert "retry" in actions
        assert "clear" in actions
        assert "session_setting" in actions
        assert any(o.get("option") == "back_providers" for o in iter_select_options(final))
        think = [el for el in card_elements(final) if el.get("tag") == "collapsible_panel"]
        if think:
            assert think[0]["expanded"] is False

    asyncio.run(_run())


def test_tool_and_error_cards():
    ad = _adapter()

    async def _run():
        task = StandardTask(
            session_id="feishu:oc_1:ou_1",
            channel=ChannelType.FEISHU,
            user_id="ou_1",
            content="查知识库",
        )
        await ad._seed_turn_card(task, chat_id="oc_1", user_text="查知识库")
        tid = task.task_id
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_TOOL_CALL,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"id": "c1", "name": "kb_search"},
            )
        )
        await asyncio.sleep(0.05)
        live = ad.client.updates[-1][1]
        joined = card_plain_text(live)
        assert "kb_search" in joined
        think = next(el for el in card_elements(live) if el.get("tag") == "collapsible_panel")
        assert think["expanded"] is True
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_TOOL_RESULT,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={
                    "id": "c1",
                    "name": "kb_search",
                    "success": True,
                    "result": {"citations_md": "- **doc.md**", "results": [{"title": "doc.md"}]},
                },
            )
        )
        await asyncio.sleep(0.05)
        live = ad.client.updates[-1][1]
        joined = card_plain_text(live)
        assert "doc.md" in joined
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_FAILED,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"error": 'Traceback (most recent call last):\n  File "x.py", line 1\nRuntimeError: 挂了'},
            )
        )
        err = ad.client.updates[-1][1]
        assert err["header"]["template"] == "red"
        joined = card_plain_text(err)
        assert "Traceback" not in joined
        assert "挂了" in joined

    asyncio.run(_run())


def test_retry_and_clear_actions():
    ad = _adapter()

    async def _run():
        ad._last_prompts["feishu:oc_1:ou_1"] = "再来一次"
        from src.adapters.feishu.events import ParsedCardAction

        retry = ParsedCardAction(
            user_id="ou_1",
            open_message_id="om_old",
            action="retry",
            kind="conversation",
            payload="再来一次",
            session_id="feishu:oc_1:ou_1",
            chat_id="oc_1",
        )
        task = await ad._handle_conversation_card(retry)
        assert task is not None
        assert task.content == "再来一次"
        assert ad.client.sends

        cleared = ParsedCardAction(
            user_id="ou_1",
            open_message_id="om_old",
            action="clear",
            kind="conversation",
            session_id="feishu:oc_1:ou_1",
            chat_id="oc_1",
        )
        out = await ad._handle_conversation_card(cleared)
        assert out is None
        assert any(path.endswith("/feishu:oc_1:ou_1") for _, path, _ in ad.orchestrator.calls)
        final = ad.client.updates[-1][1]
        assert final["header"]["title"]["content"] == "会话已清空"

    asyncio.run(_run())


def test_reasoning_folds_then_collapses_on_complete():
    ad = _adapter()

    async def _run():
        task = StandardTask(
            session_id="feishu:oc_1:ou_1",
            channel=ChannelType.FEISHU,
            user_id="ou_1",
            content="推理一下",
        )
        await ad._seed_turn_card(task, chat_id="oc_1", user_text="推理一下")
        tid = task.task_id
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_REASONING,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"delta": "先列步骤"},
            )
        )
        await asyncio.sleep(STREAM_DEBOUNCE_S + 0.15)
        live = ad.client.updates[-1][1]
        think = next(el for el in card_elements(live) if el.get("tag") == "collapsible_panel")
        assert think["expanded"] is True
        assert "先列步骤" in card_plain_text(live)
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_COMPLETED,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"content": "结论", "reasoning": "先列步骤", "usage": {"prompt_tokens": 10, "completion_tokens": 4}},
            )
        )
        final = ad.client.updates[-1][1]
        think = next(el for el in card_elements(final) if el.get("tag") == "collapsible_panel")
        assert think["expanded"] is False
        assert "结论" in card_plain_text(final)
        assert any(el.get("tag") == "chart" for el in card_elements(final))

    asyncio.run(_run())


def test_kb_stats_emits_chart_card():
    ad = _adapter()

    async def _run():
        task = StandardTask(
            session_id="feishu:oc_1:ou_1",
            channel=ChannelType.FEISHU,
            user_id="ou_1",
            content="知识库统计",
        )
        await ad._seed_turn_card(task, chat_id="oc_1", user_text="知识库统计")
        tid = task.task_id
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_TOOL_RESULT,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={
                    "id": "c2",
                    "name": "kb_stats",
                    "success": True,
                    "result": {"docs": 3, "chunks": 11, "chunks_with_embedding": 4},
                },
            )
        )
        await ad.on_bus_event(
            BusEvent(
                event_type=EventType.TASK_COMPLETED,
                task_id=tid,
                session_id=task.session_id,
                channel=ChannelType.FEISHU,
                payload={"content": "当前库有 3 篇文档"},
            )
        )
        reply = ad.client.updates[-1][1]
        assert any(el.get("tag") == "chart" for el in card_elements(reply))
        assert any(card[1]["header"]["title"]["content"] in {"知识库统计", "同步摘要"} for card in ad.client.sends[1:])

    asyncio.run(_run())


def test_session_setting_select_opens_preset():
    ad = _adapter()

    async def _run():
        from src.adapters.feishu.events import ParsedCardAction

        action = ParsedCardAction(
            user_id="ou_1",
            open_message_id="om_old",
            action="session_setting",
            kind="conversation",
            option="open_preset",
            session_id="feishu:oc_1:ou_1",
            chat_id="oc_1",
        )
        out = await ad._handle_conversation_card(action)
        assert out is None
        card = ad.client.updates[-1][1]
        assert card["header"]["title"]["content"] == "权限预设"
        assert any(el.get("tag") == "select_static" for el in card_elements(card))

    asyncio.run(_run())
