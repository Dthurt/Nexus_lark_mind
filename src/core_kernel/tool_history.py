"""Normalize chat history so OpenAI/DeepSeek tool_calls sequences stay legal.

Providers reject any assistant message that has `tool_calls` unless the
**immediately following** messages include a `role=tool` row for every
`tool_call_id`. NLM can emit illegal sequences when:

- Session replay stores one assistant row per parallel tool_call
- Compaction inserts a user checkpoint between tool_calls and results
- Hard-drop / overflow trim keeps tool_calls but drops tool rows
- A cancelled/failed tool never wrote a result, then a new user turn starts
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Sequence

from src.common.schemas import ChatMessage, ChatRole

MISSING_TOOL_RESULT = json.dumps(
    {"ok": False, "error": "tool result missing from history (sanitized)"},
    ensure_ascii=False,
)


def _role(m: ChatMessage) -> str:
    role = getattr(m, "role", None)
    return role.value if hasattr(role, "value") else str(role or "")


def _metadata(m: ChatMessage) -> Dict[str, Any]:
    meta = getattr(m, "metadata", None)
    return dict(meta) if isinstance(meta, dict) else {}


def assistant_tool_calls(m: ChatMessage) -> List[Dict[str, Any]]:
    if _role(m) != "assistant":
        return []
    tcs = _metadata(m).get("tool_calls")
    if not isinstance(tcs, list):
        return []
    return [dict(tc) for tc in tcs if isinstance(tc, dict)]


def _tool_fn_name(tc: Dict[str, Any]) -> str:
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    return str(fn.get("name") or tc.get("name") or "unknown")


def _ensure_call_id(tc: Dict[str, Any], idx: int) -> str:
    cid = str(tc.get("id") or "").strip()
    if not cid:
        cid = f"call_{idx}"
        tc["id"] = cid
    return cid


def _strip_empty_tool_calls(m: ChatMessage) -> ChatMessage:
    meta = _metadata(m)
    if "tool_calls" not in meta:
        return m
    meta.pop("tool_calls", None)
    return m.model_copy(update={"metadata": meta})


def _merge_tool_call_assistants(group: Sequence[ChatMessage]) -> ChatMessage:
    contents = [(m.content or "").strip() for m in group if (m.content or "").strip()]
    merged_tcs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    meta: Dict[str, Any] = {}
    for m in group:
        meta.update(_metadata(m))
        for tc in assistant_tool_calls(m):
            cid = _ensure_call_id(tc, len(merged_tcs))
            if cid in seen:
                continue
            seen.add(cid)
            merged_tcs.append(tc)
    meta["tool_calls"] = merged_tcs
    first = group[0]
    return ChatMessage(
        role=ChatRole.ASSISTANT,
        content="\n".join(contents),
        name=getattr(first, "name", None),
        metadata=meta,
    )


def _synth_tool_result(call_id: str, name: str) -> ChatMessage:
    return ChatMessage(
        role=ChatRole.TOOL,
        content=MISSING_TOOL_RESULT,
        name=name or "unknown",
        tool_call_id=call_id,
        metadata={"kind": "synthesized_tool_result", "sanitized": True},
    )


def sanitize_tool_call_messages(messages: Sequence[ChatMessage]) -> List[ChatMessage]:
    """Return a copy of *messages* that is legal for chat.completions.

    - Drops empty ``tool_calls`` arrays
    - Merges consecutive assistant tool_call rows (session replay of parallel calls)
    - Pulls matching tool results up so they immediately follow the assistant
    - Synthesizes error tool results for any missing ``tool_call_id``
    - Drops orphan tool rows that have no preceding assistant tool_calls
    """
    msgs = list(messages or [])
    out: List[ChatMessage] = []
    i = 0
    n = len(msgs)
    while i < n:
        m = msgs[i]
        if _role(m) == "tool":
            # Orphan tool result — providers also reject these.
            i += 1
            continue

        tcs = assistant_tool_calls(m)
        if _role(m) == "assistant" and not tcs:
            out.append(_strip_empty_tool_calls(m) if "tool_calls" in _metadata(m) else m)
            i += 1
            continue

        if _role(m) != "assistant" or not tcs:
            out.append(m)
            i += 1
            continue

        group = [m]
        j = i + 1
        while j < n and _role(msgs[j]) == "assistant" and assistant_tool_calls(msgs[j]):
            group.append(msgs[j])
            j += 1
        merged = _merge_tool_call_assistants(group)
        merged_tcs = assistant_tool_calls(merged)
        needed: List[str] = []
        id_to_name: Dict[str, str] = {}
        for idx, tc in enumerate(merged_tcs):
            cid = _ensure_call_id(tc, idx)
            if cid not in needed:
                needed.append(cid)
            id_to_name[cid] = _tool_fn_name(tc)
        merged.metadata["tool_calls"] = merged_tcs

        found: Dict[str, ChatMessage] = {}
        remainder: List[ChatMessage] = []
        k = j
        while k < n:
            cur = msgs[k]
            if _role(cur) == "assistant" and assistant_tool_calls(cur):
                break
            if _role(cur) == "tool":
                cid = str(getattr(cur, "tool_call_id", None) or "").strip()
                if cid in needed and cid not in found:
                    found[cid] = cur
                k += 1
                continue
            remainder.append(cur)
            k += 1

        out.append(merged)
        for cid in needed:
            if cid in found:
                out.append(found[cid])
            else:
                out.append(_synth_tool_result(cid, id_to_name.get(cid, "unknown")))
        for r in remainder:
            if _role(r) == "tool":
                continue
            if _role(r) == "assistant" and not assistant_tool_calls(r) and "tool_calls" in _metadata(r):
                out.append(_strip_empty_tool_calls(r))
            else:
                out.append(r)
        i = k

    return out


def openai_tool_sequence_is_legal(payload: Iterable[Dict[str, Any]]) -> bool:
    """True if *payload* satisfies the OpenAI tool_calls pairing rule."""
    pending: Optional[set[str]] = None
    for item in payload:
        if not isinstance(item, dict):
            return False
        role = str(item.get("role") or "")
        tcs = item.get("tool_calls")
        if role == "assistant" and tcs:
            if not isinstance(tcs, list) or not tcs:
                return False
            ids = {str(tc.get("id") or "") for tc in tcs if isinstance(tc, dict)}
            if not ids or "" in ids:
                return False
            pending = set(ids)
            continue
        if pending is not None:
            if role != "tool":
                return False
            cid = str(item.get("tool_call_id") or "")
            if cid not in pending:
                return False
            pending.discard(cid)
            if not pending:
                pending = None
            continue
        if role == "tool":
            return False
    return pending is None
