"""Feishu provider/model pick helpers and card parsing."""

from src.adapters.feishu.cards import (
    build_model_pick_card,
    build_provider_pick_card,
    iter_card_actions,
)
from src.adapters.feishu.events import classify_payload, parse_card_action
from src.adapters.feishu.model_pick import (
    catalog_choices,
    is_rebind_command,
    session_has_model,
)


def test_catalog_choices_skips_unconfigured_and_empty_models():
    catalog = {
        "providers": [
            {"id": "glm", "label": "GLM", "configured": False, "models": ["a"]},
            {"id": "mine", "label": "Mine", "configured": True, "models": [], "default_model": ""},
            {
                "id": "custom-a",
                "label": "Custom A",
                "configured": True,
                "builtin": False,
                "source": "custom",
                "default_model": "m1",
                "models": ["m2"],
            },
        ]
    }
    choices = catalog_choices(catalog)
    assert [c["id"] for c in choices] == ["custom-a"]
    assert choices[0]["models"][0] == "m1"
    assert "m2" in choices[0]["models"]


def test_session_has_model_and_rebind():
    assert not session_has_model({})
    assert not session_has_model({"model_provider": "glm", "model_name": ""})
    assert session_has_model({"model_provider": "glm", "model_name": "x"})
    assert is_rebind_command("切换模型")
    assert is_rebind_command("/model")
    assert not is_rebind_command("你好")


def test_provider_pick_card_embeds_session():
    card = build_provider_pick_card(
        providers=[
            {"id": "custom-a", "label": "A", "models": ["m1", "m2"], "source": "custom"},
            {"id": "glm", "label": "GLM", "models": ["g"], "source": "env"},
        ],
        session_id="feishu:oc_1:ou_1",
        chat_id="oc_1",
    )
    values = iter_card_actions(card)
    assert any(v.get("kind") == "provider_pick" and v.get("provider_id") == "custom-a" for v in values)
    assert all(v.get("session_id") == "feishu:oc_1:ou_1" for v in values if v.get("kind") == "provider_pick")


def test_model_pick_card_and_parse_action():
    card = build_model_pick_card(
        provider_id="custom-a",
        provider_label="A",
        models=["m1", "m2", "m3"],
        session_id="feishu:oc_1:ou_1",
        chat_id="oc_1",
    )
    pick = next(a for a in iter_card_actions(card) if a.get("action") == "pick_model")
    payload = {
        "open_message_id": "om_x",
        "operator": {"open_id": "ou_1"},
        "action": {"value": pick},
    }
    parsed = parse_card_action(payload)
    assert parsed is not None
    assert parsed.kind == "model_pick"
    assert parsed.provider_id == "custom-a"
    assert parsed.model_name == "m1"
    assert parsed.session_id == "feishu:oc_1:ou_1"
    kind, data = classify_payload(
        {
            "header": {"event_type": "card.action.trigger"},
            "open_message_id": "om_x",
            "operator": {"open_id": "ou_1"},
            "action": {"value": pick},
        }
    )
    assert kind == "card_action"
    assert data.kind == "model_pick"
