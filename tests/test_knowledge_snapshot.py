from src.core_kernel.plugin_runtime.knowledge_snapshot import (
    build_text_snapshot,
    locate_text_match,
)


def test_locate_text_match_prefers_earliest_token():
    loc = locate_text_match("Cats purr and nap in sunbeams.", "feline", ["purr", "sun"])
    assert loc is not None
    start, end, hit = loc
    assert hit == "purr"
    assert "Cats purr and nap in sunbeams."[start:end] == "purr"


def test_snapshot_includes_surrounding_context():
    body = "alpha marker in default library sits here"
    snap = build_text_snapshot(body, query="marker", tokens=["marker"], radius=6)
    assert snap["match_kind"] == "keyword"
    assert snap["highlight"] == "marker"
    assert snap["prefix"].endswith(" ") or "alpha" in snap["prefix"]
    assert snap["suffix"].startswith(" ") or "library" in snap["suffix"]
    assert snap["match_start"] == body.index("marker")


def test_snapshot_semantic_when_no_keyword():
    snap = build_text_snapshot("Cats purr on the windowsill.", query="feline behavior")
    assert snap["match_kind"] == "semantic"
    assert snap["highlight"] == ""
    assert snap["match_start"] == -1
    assert "Cats" in snap["snippet"]
