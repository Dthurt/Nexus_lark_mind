"""Wave D: experience tier + reasoning effort helpers."""

from src.common.experience_tiers import (
    experience_tier_prompt_block,
    model_strength,
    normalize_experience_tier,
    normalize_reasoning_effort,
    reasoning_effort_hint,
    suggest_stronger_model,
    tier_meets_model_floor,
    tier_model_floor_hint,
)


def test_normalize_experience_tier():
    assert normalize_experience_tier(None) == "balanced"
    assert normalize_experience_tier("FAST") == "fast"
    assert normalize_experience_tier("3") == "high"
    assert normalize_experience_tier("nope") == "balanced"


def test_normalize_reasoning_effort():
    assert normalize_reasoning_effort("") == "medium"
    assert normalize_reasoning_effort("LOW") == "low"
    assert normalize_reasoning_effort("max") == "high"


def test_prompt_blocks_mention_tier():
    assert "Mermaid only" in experience_tier_prompt_block("fast")
    assert "Draw.io" in experience_tier_prompt_block("high")
    assert "`medium`" in reasoning_effort_hint("medium")


def test_model_strength_heuristics():
    assert model_strength("gpt-4o-mini") == 0
    assert model_strength("claude-sonnet-4") == 2
    assert model_strength("glm-4.7") == 1


def test_tier_model_floor():
    assert tier_meets_model_floor("fast", "gpt-4o-mini")
    assert not tier_meets_model_floor("high", "gpt-4o-mini")
    assert tier_meets_model_floor("high", "claude-opus-4")
    assert suggest_stronger_model(["gpt-4o-mini", "claude-sonnet-4"], "gpt-4o-mini") == (
        "claude-sonnet-4"
    )
    hint = tier_model_floor_hint("high", "flash", ["flash", "sonnet"])
    assert hint and hint["suggestion"] == "sonnet"
