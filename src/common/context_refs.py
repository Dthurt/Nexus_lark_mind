"""Expand @ context refs into user-message attachments (local workspaces)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.adapters.workspaces.store import resolve_under_workspace


MAX_FILE_CHARS = 24_000
MAX_FILES = 8
MAX_DIR_ENTRIES = 80


def _safe_rel(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if raw in {".", "./"}:
        return "."
    return raw.lstrip("./")


def expand_context_refs(
    cwd: str,
    refs: List[Dict[str, Any]],
    *,
    workspace_kind: str = "local",
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Return (markdown_block, resolved_meta).

    Only local cwd is expanded (SSH left as path-only stubs). Empty block if nothing readable.
    """
    root = str(cwd or "").strip()
    if not root or not refs:
        return "", []

    kind = (workspace_kind or "local").strip().lower() or "local"
    blocks: List[str] = []
    resolved: List[Dict[str, Any]] = []

    for raw in refs[:MAX_FILES]:
        if not isinstance(raw, dict):
            continue
        rel = _safe_rel(str(raw.get("path") or ""))
        if not rel:
            continue
        rkind = str(raw.get("kind") or "file").strip().lower() or "file"
        entry: Dict[str, Any] = {"path": rel, "kind": rkind}

        if kind != "local":
            entry["note"] = "ssh_path_only"
            resolved.append(entry)
            blocks.append(f"### @{rel}\n_(remote path attached — read with tools)_\n")
            continue

        try:
            target = resolve_under_workspace(root, rel)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
            resolved.append(entry)
            continue

        if rkind == "dir" or target.is_dir():
            entry["kind"] = "dir"
            try:
                names = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())[
                    :MAX_DIR_ENTRIES
                ]
                listing = "\n".join(f"- {n}" for n in names) or "_(empty)_"
                blocks.append(f"### @{rel}/ (directory)\n{listing}\n")
                entry["ok"] = True
            except OSError as exc:
                entry["error"] = str(exc)
            resolved.append(entry)
            continue

        if not target.is_file():
            entry["error"] = "not_found"
            resolved.append(entry)
            continue

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            entry["error"] = str(exc)
            resolved.append(entry)
            continue

        truncated = False
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS]
            truncated = True
        fence = "text"
        suf = Path(rel).suffix.lower()
        if suf in {".py"}:
            fence = "python"
        elif suf in {".ts", ".tsx"}:
            fence = "typescript"
        elif suf in {".js", ".jsx"}:
            fence = "javascript"
        elif suf in {".json"}:
            fence = "json"
        elif suf in {".md", ".mdx"}:
            fence = "markdown"
        elif suf in {".css"}:
            fence = "css"
        elif suf in {".html", ".htm"}:
            fence = "html"
        elif suf in {".yml", ".yaml"}:
            fence = "yaml"
        note = "\n…[truncated]…" if truncated else ""
        blocks.append(f"### @{rel}\n```{fence}\n{text}{note}\n```\n")
        entry["ok"] = True
        entry["truncated"] = truncated
        entry["bytes"] = target.stat().st_size
        resolved.append(entry)

    if not blocks:
        return "", resolved
    body = "## Attached context (@)\n" + "\n".join(blocks)
    return body.strip() + "\n", resolved


def merge_user_content_with_context(content: str, context_block: str) -> str:
    user = str(content or "").strip()
    ctx = str(context_block or "").strip()
    if not ctx:
        return user
    if not user:
        return ctx
    return f"{ctx}\n## User request\n{user}"
