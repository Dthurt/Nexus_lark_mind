"""WeKnora client, sync, extension runtime, prompts, presets, session tree."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core_kernel.extension_runtime import (
    ExtensionRegistry,
    discover_and_load_extensions,
    emit_extension_event,
    get_extension_registry,
    run_tool_call_hooks,
)
from src.core_kernel.presets_loader import apply_preset_to_session_patch, discover_presets, resolve_preset
from src.core_kernel.prompt_templates import (
    discover_prompt_templates,
    expand_slash_command,
    resolve_prompt_template,
)
from src.core_kernel.session_tree import add_bookmark, build_session_tree, remove_bookmark
from src.core_kernel.skills_loader import active_skill_allowed_tools, discover_skills
from src.core_kernel.plugin_runtime.knowledge_store import Base, KnowledgeStore, content_hash
from src.infrastructure.storage.database import Base as AppBase


@pytest.fixture
async def store(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'kb.db').as_posix()}"
    engine = create_async_engine(url, future=True)
    assert Base is AppBase
    async with engine.begin() as conn:
        await conn.run_sync(AppBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    kb = KnowledgeStore(factory)
    await kb.ensure_schema()
    yield kb
    await engine.dispose()


@pytest.mark.asyncio
async def test_weknora_health_and_search_skipped(monkeypatch):
    from src.core_kernel.plugin_runtime.weknora_client import (
        weknora_health,
        weknora_list_knowledge_bases,
        weknora_push_document,
        weknora_search,
    )

    monkeypatch.delenv("WEKNORA_BASE_URL", raising=False)
    h = await weknora_health()
    assert h.get("skipped") is True
    assert h.get("online") is False
    s = await weknora_search("q")
    assert s.get("skipped") is True
    assert s.get("results") == []
    kbs = await weknora_list_knowledge_bases()
    assert kbs.get("skipped") is True
    push = await weknora_push_document(title="t", content="c")
    assert push.get("skipped") is True


@pytest.mark.asyncio
async def test_weknora_search_native_mock(monkeypatch):
    from src.core_kernel.plugin_runtime import weknora_client as wc

    monkeypatch.setenv("WEKNORA_BASE_URL", "http://weknora.test")
    monkeypatch.setenv("WEKNORA_KB_ID", "kb-1")

    class FakeResp:
        def __init__(self, status, data):
            self.status_code = status
            self._data = data
            self.text = ""

        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, headers=None, json=None):
            assert "knowledge-search" in url
            assert json.get("query") == "hello"
            assert json.get("knowledge_base_id") == "kb-1"
            return FakeResp(
                200,
                {
                    "data": [
                        {
                            "content": "hit body",
                            "knowledge_title": "Doc A",
                            "score": 0.9,
                            "knowledge_id": "k1",
                        }
                    ]
                },
            )

        async def get(self, *a, **k):
            return FakeResp(404, {})

    monkeypatch.setattr(wc.httpx, "AsyncClient", FakeClient)
    out = await wc.weknora_search("hello", limit=3)
    assert out.get("ok") is True
    assert out.get("endpoint") == "/api/v1/knowledge-search"
    assert len(out["results"]) == 1
    assert "Doc A" in out["results"][0]["title"]
    assert "WeKnora" in out["citations_md"]


@pytest.mark.asyncio
async def test_weknora_push_and_bidirectional_sync(store, monkeypatch):
    from src.core_kernel.plugin_runtime import knowledge_sync as ks

    monkeypatch.setenv("WEKNORA_BASE_URL", "http://weknora.test")
    monkeypatch.setenv("WEKNORA_KB_ID", "kb-1")

    await store.upsert(
        doc_id="local1",
        title="Note",
        content="hello weknora sync",
        tags="t",
        source="manual",
        workspace_id="ws1",
        content_hash_value=content_hash("hello weknora sync"),
    )

    async def fake_push(**kwargs):
        assert kwargs["kb_id"] == "kb-1"
        assert kwargs.get("content")
        return {"ok": True, "pushed": True, "kb_id": "kb-1", "knowledge_id": "remote-1"}

    async def fake_list(kb_id="", **kwargs):
        return {
            "ok": True,
            "kb_id": kb_id or "kb-1",
            "items": [
                {
                    "id": "remote-2",
                    "title": "From WeKnora",
                    "content": "remote content body",
                }
            ],
        }

    with patch(
        "src.core_kernel.plugin_runtime.weknora_client.weknora_push_document",
        new=fake_push,
    ), patch(
        "src.core_kernel.plugin_runtime.weknora_client.weknora_list_knowledge",
        new=fake_list,
    ), patch(
        "src.core_kernel.plugin_runtime.weknora_client.weknora_get_knowledge",
        new=AsyncMock(return_value={"ok": True, "content": ""}),
    ):
        push = await ks.sync_local_to_weknora(store, workspace_id="ws1", limit=10)
        assert push.get("pushed") == 1
        pull = await ks.sync_weknora_to_local(store, workspace_id="ws1", limit=10)
        assert pull.get("added") == 1
        both = await ks.sync_weknora_bidirectional(
            store, workspace_id="ws1", direction="both", limit=10
        )
        assert both.get("ok") is True
        push2 = await ks.sync_local_to_weknora(store, workspace_id="ws1", limit=10)
        assert push2.get("skipped_unchanged") >= 1


def test_extension_event_bus_and_active_tools(tmp_path: Path):
    reg = ExtensionRegistry()
    seen = []

    def register(api):
        api.on("tool_call", lambda ctx: seen.append(ctx.get("tool")) or {"block": False})
        api.register_tool(
            {
                "name": "ext_ping",
                "description": "ping",
                "inputSchema": {"type": "object", "properties": {}},
            }
        )
        api.set_active_tools(["read_file", "grep"])

    # Load from temp extension dir
    ext_dir = tmp_path / ".nlm" / "extensions"
    ext_dir.mkdir(parents=True)
    (ext_dir / "demo.py").write_text(
        "def register(api):\n"
        "    api.on('tool_call', lambda ctx: {'block': True, 'reason': 'nope'})\n"
        "    api.set_active_tools(['read_file'])\n",
        encoding="utf-8",
    )
    get_extension_registry().reset()
    discover_and_load_extensions(str(tmp_path), reload=True)
    hook = run_tool_call_hooks({"tool": "write_file", "base": "write_file", "arguments": {}})
    assert hook.get("block") is True
    assert get_extension_registry().get_active_tools() == ["read_file"]
    tools = [
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "write_file"}},
        {"type": "function", "function": {"name": "ask_user"}},
    ]
    filtered = get_extension_registry().filter_openai_tools(tools)
    names = [((t.get("function") or {}).get("name")) for t in filtered]
    assert "read_file" in names
    assert "write_file" not in names
    assert "ask_user" in names
    get_extension_registry().reset()


def test_skill_allowed_tools(tmp_path: Path):
    skill = tmp_path / ".nlm" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: demo\ndescription: D\nallowed-tools: read_file, grep\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    skills = discover_skills(str(tmp_path))
    assert skills[0].allowed_tools == ("read_file", "grep")
    assert active_skill_allowed_tools(str(tmp_path), "please /skill:demo now") == [
        "read_file",
        "grep",
    ]
    assert active_skill_allowed_tools(str(tmp_path), "no skill") is None


def test_prompt_templates_and_slash(tmp_path: Path):
    pdir = tmp_path / ".nlm" / "prompts"
    pdir.mkdir(parents=True)
    (pdir / "review.md").write_text(
        "---\nname: review\ndescription: Review\nvariables: FILE\n---\nLook at $FILE\n",
        encoding="utf-8",
    )
    tmpls = discover_prompt_templates(str(tmp_path))
    assert any(t.name == "review" for t in tmpls)
    expanded = expand_slash_command(str(tmp_path), "/review src/app.py")
    assert expanded is not None
    assert "src/app.py" in expanded["prompt"]
    assert resolve_prompt_template(str(tmp_path), "review") is not None


def test_presets_loader():
    presets = discover_presets(None)
    names = {p.name for p in presets}
    assert "code-review" in names
    p = resolve_preset(None, "code-review")
    assert p is not None
    patch = apply_preset_to_session_patch(p)
    assert patch.get("permission_preset") == "read-only"
    assert "read_file" in (patch.get("active_tools") or [])


def test_session_tree_and_bookmarks():
    sessions = [
        {"session_id": "a", "title": "Root", "updated_at": "2"},
        {
            "session_id": "b",
            "title": "Fork",
            "parent_id": "a",
            "fork_point_index": 3,
            "updated_at": "3",
        },
        {"session_id": "c", "title": "Other", "forked_from": "a", "updated_at": "1"},
    ]
    tree = build_session_tree(sessions)
    assert tree["node_count"] == 3
    assert tree["root_count"] == 1
    root = tree["roots"][0]
    assert root["session_id"] == "a"
    assert len(root["children"]) == 2
    marks = add_bookmark([], message_index=2, label="decision")
    assert marks[0]["label"] == "decision"
    marks = remove_bookmark(marks, message_index=2)
    assert marks == []


def test_resolve_weknora_kb_routing(monkeypatch):
    from src.core_kernel.plugin_runtime import weknora_client as wc

    monkeypatch.setenv("WEKNORA_KB_ID", "global-kb")
    monkeypatch.setenv("WEKNORA_KB_MAP", "ws-a=kb-a,ws-b=kb-b")
    assert wc.resolve_weknora_kb_id(kb_id="explicit") == "explicit"
    assert wc.resolve_weknora_kb_id(session_kb_id="sess-kb") == "sess-kb"
    assert wc.resolve_weknora_kb_id(workspace_id="ws-a") == "kb-a"
    assert wc.resolve_weknora_kb_id(workspace_id="unknown") == "global-kb"
    monkeypatch.setenv("WEKNORA_KB_MAP", '{"ws-x":"kb-x"}')
    assert wc.resolve_weknora_kb_id(workspace_id="ws-x") == "kb-x"


@pytest.mark.asyncio
async def test_latest_sync_hash_skip(store):
    await store.log_sync(
        source="weknora_push",
        source_uri="kb-1:local1",
        content_hash_value="abc123",
        status="ok",
        workspace_id="ws1",
    )
    h = await store.latest_sync_hash(
        source="weknora_push",
        source_uri="kb-1:local1",
        workspace_id="ws1",
    )
    assert h == "abc123"
    assert (
        await store.latest_sync_hash(
            source="weknora_push", source_uri="kb-1:missing", workspace_id="ws1"
        )
        is None
    )


def test_fork_point_for_refork():
    from src.core_kernel.session_tree import fork_point_for_refork

    assert fork_point_for_refork({"session_id": "a"}) is None
    point = fork_point_for_refork(
        {"session_id": "b", "parent_id": "a", "fork_point_index": 4, "title": "Try B"}
    )
    assert point["parent_id"] == "a"
    assert point["fork_point_index"] == 4


def test_extension_after_agent_events():
    from src.core_kernel.extension_runtime import emit_extension_event, get_extension_registry

    get_extension_registry().reset()
    seen = []
    get_extension_registry().bus.on("after_agent_turn", lambda ctx: seen.append(ctx.get("event")))
    get_extension_registry().bus.on("compaction", lambda ctx: seen.append("compaction"))
    emit_extension_event("after_agent_turn", {"session_id": "s1"})
    emit_extension_event("compaction", {"via": "llm"})
    assert "after_agent_turn" in seen
    assert "compaction" in seen
    get_extension_registry().reset()


@pytest.mark.asyncio
async def test_session_start_end_events(monkeypatch):
    """P0: session_start / session_end must fire from SessionContext lifecycle."""
    from src.agent_orchestrator.session_context import SessionContext
    from src.core_kernel.extension_runtime import get_extension_registry

    get_extension_registry().reset()
    seen: list[str] = []
    get_extension_registry().bus.on("session_start", lambda ctx: seen.append("start:" + str(ctx.get("session_id"))))
    get_extension_registry().bus.on("session_end", lambda ctx: seen.append("end:" + str(ctx.get("session_id"))))

    class FakeRedis:
        def __init__(self):
            self._store = {}

        async def get_session(self, sid):
            return self._store.get(sid)

        async def set_session(self, sid, payload):
            self._store[sid] = dict(payload)
            return self._store[sid]

        async def delete_session(self, sid):
            self._store.pop(sid, None)

    ctx = SessionContext(FakeRedis())  # type: ignore[arg-type]
    await ctx.ensure("s-new", user_id="u", channel="web")
    await ctx.ensure("s-new", user_id="u", channel="web")  # existing → no second start
    await ctx.clear("s-new")
    assert seen == ["start:s-new", "end:s-new"]
    get_extension_registry().reset()


def test_filter_openai_tools_active_subset():
    from src.core_kernel.agent_runner import _filter_openai_tools

    tools = [
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "write_file"}},
        {"type": "function", "function": {"name": "ask_user"}},
    ]
    out = _filter_openai_tools(
        tools,
        True,
        active_tools=["read_file"],
    )
    names = [((t.get("function") or {}).get("name")) for t in out]
    assert names == ["read_file", "ask_user"]
