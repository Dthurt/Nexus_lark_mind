"""Deterministic knowledge-base retrieval injected into each agent turn.

When a session is bound to a WeKnora KB, search that id only (never KB[0] /
WEKNORA_KB_ID fallback). When unbound, search the local SQLite KB. Snippets
are appended to the latest user message so the model cannot skip retrieval.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from src.common.schemas import ChatMessage, ChatRole

MIN_QUERY_CHARS = 2
MAX_SNIPPET = 420
MAX_HITS = 6

RetrieveFn = Callable[..., Any]


def last_user_query(messages: List[ChatMessage]) -> str:
    """Latest user text for retrieval (skip already-injected grounding)."""
    for m in reversed(messages or []):
        role = getattr(m, "role", None)
        role_s = role.value if hasattr(role, "value") else str(role or "")
        if role_s != "user":
            continue
        meta = getattr(m, "metadata", None) or {}
        if isinstance(meta, dict) and meta.get("kind") == "kb_grounding":
            continue
        text = str(getattr(m, "content", "") or "").strip()
        if "<knowledge_context" in text:
            # Already grounded — use the prefix before the tag as the query.
            text = text.split("<knowledge_context", 1)[0].strip()
        return text
    return ""


def bound_weknora_kb_id(meta: Optional[Dict[str, Any]]) -> str:
    """Session picker value only — empty means local SQLite, not default remote."""
    return str((meta or {}).get("weknora_kb_id") or "").strip()


def format_grounding_block(result: Dict[str, Any]) -> str:
    source = str(result.get("source") or "local")
    kb_id = str(result.get("kb_id") or "") or "local"
    hits: List[Dict[str, Any]] = list(result.get("results") or [])
    citations = str(result.get("citations_md") or "").strip()
    error = str(result.get("error") or "").strip()
    skipped = bool(result.get("skipped"))
    read_tool = "weknora_read" if source == "weknora" else "kb_read"
    search_tool = "weknora_search" if source == "weknora" else "kb_search"

    lines = [
        f'<knowledge_context source="{source}" kb_id="{kb_id}">',
        "Server-side retrieval against the bound knowledge base for this turn. "
        f"Answer from these hits first. Cite titles/paths. Call `{read_tool}` "
        f"(after `{search_tool}` if you need more) for full bodies — do not invent.",
    ]
    if error:
        lines.append(f"Retrieval error: {error}")
    elif skipped:
        lines.append(
            str(result.get("reason") or "Remote knowledge base is not configured; no remote hits.")
        )
    if citations:
        lines.append(citations)
    if hits:
        lines.append("")
        lines.append("### Snippets")
        for i, hit in enumerate(hits[:MAX_HITS], 1):
            title = str(hit.get("title") or hit.get("doc_id") or hit.get("source_uri") or "untitled")
            doc_id = str(hit.get("doc_id") or hit.get("knowledge_id") or "")
            cite = str(hit.get("citation") or hit.get("source_uri") or "")
            section = str(hit.get("context_header") or hit.get("heading") or "").replace("\n", " › ")
            snip = str(hit.get("snippet") or hit.get("content") or "").replace("\n", " ").strip()
            if len(snip) > MAX_SNIPPET:
                snip = snip[: MAX_SNIPPET - 1] + "…"
            head = f"{i}. **{title}**"
            if section:
                head += f" § {section}"
            if doc_id:
                head += f" [{doc_id}]"
            if cite and cite not in head:
                head += f" — {cite}"
            lines.append(head)
            if snip:
                lines.append(f"   {snip}")
    elif not error and not skipped:
        lines.append("No hits in the bound knowledge base for this query.")
    lines.append("</knowledge_context>")
    return "\n".join(lines)


def inject_grounding(messages: List[ChatMessage], block: str) -> List[ChatMessage]:
    """Append the grounding block to the latest real user message (in-memory only)."""
    if not (block or "").strip():
        return list(messages)
    out = list(messages or [])
    for i in range(len(out) - 1, -1, -1):
        m = out[i]
        role = getattr(m, "role", None)
        role_s = role.value if hasattr(role, "value") else str(role or "")
        if role_s != "user":
            continue
        meta = dict(getattr(m, "metadata", None) or {})
        if meta.get("kind") == "kb_grounding":
            continue
        content = str(getattr(m, "content", "") or "")
        if "<knowledge_context" in content:
            return out
        meta = {**meta, "kb_grounded": True}
        out[i] = ChatMessage(
            role=m.role,
            content=content.rstrip() + "\n\n" + block.strip(),
            name=getattr(m, "name", None),
            tool_call_id=getattr(m, "tool_call_id", None),
            metadata=meta,
        )
        return out
    out.append(
        ChatMessage(
            role=ChatRole.USER,
            content=block.strip(),
            metadata={"kind": "kb_grounding"},
        )
    )
    return out


async def retrieve_bound_knowledge(
    query: str,
    meta: Optional[Dict[str, Any]] = None,
    *,
    store: Any = None,
    weknora_search_fn: Optional[RetrieveFn] = None,
    limit: int = MAX_HITS,
) -> Dict[str, Any]:
    """Search the session-bound KB. Never lists KBs to pick the first one."""
    q = (query or "").strip()
    meta = dict(meta or {})
    bound = bound_weknora_kb_id(meta)
    workspace_id = str(meta.get("workspace_id") or "")
    n = max(1, min(int(limit or MAX_HITS), 12))

    if bound:
        search = weknora_search_fn
        if search is None:
            from src.core_kernel.plugin_runtime.weknora_client import weknora_search as search
        data = await search(
            q,
            limit=n,
            kb_id=bound,
            session_kb_id=bound,
            workspace_id=workspace_id,
        )
        if not isinstance(data, dict):
            data = {"ok": False, "error": "invalid weknora response", "results": []}
        results = list(data.get("results") or [])
        return {
            "ok": bool(data.get("ok", True)) and not data.get("error"),
            "source": "weknora",
            "kb_id": bound,
            "query": q,
            "results": results,
            "citations_md": str(data.get("citations_md") or ""),
            "error": str(data.get("error") or ""),
            "skipped": bool(data.get("skipped")),
            "reason": str(data.get("reason") or ""),
            "hit_count": len(results),
        }

    from src.core_kernel.plugin_runtime.knowledge_store import citations_markdown

    kb = store
    if kb is None:
        from src.core_kernel.plugin_runtime.knowledge_store import KnowledgeStore
        from src.infrastructure.storage.database import get_session_factory

        kb = KnowledgeStore(get_session_factory())
        await kb.ensure_schema()
    hits = await kb.search(q, workspace_id=workspace_id, limit=n)
    return {
        "ok": True,
        "source": "local",
        "kb_id": "",
        "query": q,
        "results": hits,
        "citations_md": citations_markdown(hits),
        "error": "",
        "skipped": False,
        "reason": "",
        "hit_count": len(hits),
    }


def grounding_notice(result: Dict[str, Any]) -> str:
    source = str(result.get("source") or "local")
    kb_id = str(result.get("kb_id") or "")
    n = int(result.get("hit_count") or 0)
    if source == "weknora":
        label = f"WeKnora「{kb_id}」"
    else:
        label = "本地知识库"
    if result.get("error"):
        return f"知识库检索失败 · {label} · {result.get('error')}"
    if result.get("skipped"):
        return f"知识库未检索 · {label} · {result.get('reason') or '未配置'}"
    return f"已检索{label} · {n} 条"


async def apply_turn_grounding(
    messages: List[ChatMessage],
    meta: Optional[Dict[str, Any]] = None,
    *,
    store: Any = None,
    weknora_search_fn: Optional[RetrieveFn] = None,
) -> Tuple[List[ChatMessage], Optional[Dict[str, Any]]]:
    """Retrieve + inject. Returns (messages, SSE event or None). Never raises."""
    query = last_user_query(messages)
    if len(query) < MIN_QUERY_CHARS:
        return list(messages), None
    for m in reversed(messages or []):
        role = getattr(m, "role", None)
        role_s = role.value if hasattr(role, "value") else str(role or "")
        if role_s != "user":
            continue
        if "<knowledge_context" in str(getattr(m, "content", "") or ""):
            return list(messages), None
        break
    try:
        result = await retrieve_bound_knowledge(
            query,
            meta,
            store=store,
            weknora_search_fn=weknora_search_fn,
        )
    except Exception as exc:
        bound = bound_weknora_kb_id(meta)
        result = {
            "ok": False,
            "source": "weknora" if bound else "local",
            "kb_id": bound,
            "query": query,
            "results": [],
            "citations_md": "",
            "error": str(exc),
            "skipped": False,
            "hit_count": 0,
        }
    block = format_grounding_block(result)
    injected = inject_grounding(messages, block)
    event = {
        "delta": "",
        "done": False,
        "notice": grounding_notice(result),
        "notice_kind": "kb_grounding",
        "kb_grounding": {
            "source": result.get("source"),
            "kb_id": result.get("kb_id") or "",
            "hit_count": result.get("hit_count") or 0,
        },
    }
    return injected, event
