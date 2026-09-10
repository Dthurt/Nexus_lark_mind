"""Recover tool calls that weak models emit as plain text instead of API tool_calls."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# Name the model wrote → canonical short tool name
_ALIASES = {
    "cli.web_search": "web_search",
    "cli_web_search": "web_search",
    "cli_web_search_web_search": "web_search",
    "web_search": "web_search",
    "cli.literature_search": "literature_search",
    "cli_literature_search": "literature_search",
    "cli_literature_search_literature_search": "literature_search",
    "literature_search": "literature_search",
    "cli.image_search": "image_search",
    "cli_image_search": "image_search",
    "cli_image_search_image_search": "image_search",
    "image_search": "image_search",
    "cli.web_crawl": "web_crawl",
    "cli_web_crawl": "web_crawl",
    "cli_web_crawl_web_crawl": "web_crawl",
    "web_crawl": "web_crawl",
    "crawl4ai": "web_crawl",
    "ask_user": "ask_user",
    "todo_write": "todo_write",
    "exit_plan_mode": "exit_plan_mode",
    "glob": "glob",
    "grep": "grep",
    "read_file": "read_file",
    "write_file": "write_file",
    "edit_file": "edit_file",
    "run_shell": "run_shell",
    "list_dir": "list_dir",
}

_NAME_RE = (
    r"(?:cli\.)?(?:web_search|literature_search|image_search|web_crawl|crawl4ai|"
    r"ask_user|todo_write|exit_plan_mode|"
    r"glob|grep|read_file|write_file|edit_file|run_shell|list_dir|"
    r"cli_web_search(?:_web_search)?|cli_literature_search(?:_literature_search)?|"
    r"cli_image_search(?:_image_search)?|cli_web_crawl(?:_web_crawl)?)"
)

# Patterns: tool name on its own line, then JSON object
_BLOCK_RE = re.compile(
    rf"(?ms)^\s*(?:[-*]\s*)?(?:`{{0,3}})?(?P<name>{_NAME_RE})(?:`{{0,3}})?"
    rf"(?:\s*\([^)]*\))?\s*\n\s*(?P<body>\{{.*?\}})\s*$"
)

_FENCE_RE = re.compile(
    rf"(?ms)```(?:json|tool|)\s*\n?\s*(?P<name>{_NAME_RE})\s*\n(?P<body>\{{.*?\}})\s*```"
)

_INLINE_RE = re.compile(
    rf"(?ms)(?P<name>{_NAME_RE})\s*(?P<body>\{{[^{{}}]*\"(?:query|url|path|pattern|command|plan|items|questions)\"[^{{}}]*\}})"
)


def _loads_obj(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        # Trailing commas / single quotes — light repair
        try:
            repaired = text.replace("'", '"')
            data = json.loads(repaired)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _canon(name: str) -> Optional[str]:
    key = (name or "").strip()
    return _ALIASES.get(key) or _ALIASES.get(key.replace(".", "_"))


def extract_pseudo_tool_calls(content: str) -> List[Dict[str, Any]]:
    """If the assistant wrote tool invocations as prose/JSON, return OpenAI-shaped tool_calls."""
    text = (content or "").strip()
    if not text or len(text) > 20_000:
        return []

    found: List[Tuple[int, str, Dict[str, Any]]] = []
    for rx in (_FENCE_RE, _BLOCK_RE, _INLINE_RE):
        for m in rx.finditer(text):
            canon = _canon(m.group("name"))
            args = _loads_obj(m.group("body"))
            if not canon or not args:
                continue
            found.append((m.start(), canon, args))

    if not found:
        return []

    # Deduplicate by (name, sorted args) keeping earliest
    seen = set()
    out: List[Dict[str, Any]] = []
    for start, name, args in sorted(found, key=lambda x: x[0]):
        key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": f"pseudo_{name}_{len(out)}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
        if len(out) >= 3:
            break
    return out


def strip_pseudo_tool_text(content: str) -> str:
    """Remove recovered pseudo-tool blocks from visible assistant text."""
    text = content or ""
    text = _FENCE_RE.sub("", text)
    text = _BLOCK_RE.sub("", text)
    # Only strip trailing inline invocations
    text = re.sub(
        rf"(?ms)\n?\s*(?:{_NAME_RE})\s*\{{[^{{}}]*\"(?:query|url|path|pattern|command|plan)\"[^{{}}]*\}}\s*$",
        "",
        text,
    )
    return text.strip()
