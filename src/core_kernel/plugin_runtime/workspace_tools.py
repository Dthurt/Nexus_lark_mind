"""In-process workspace tools — coding agent FS + shell scoped to session cwd."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from src.adapters.workspaces.store import resolve_under_workspace
from src.common.errors import PluginError, ValidationAppError
from src.core_kernel.plugin_runtime.invoke_context import (
    fs_was_observed,
    get_workspace_cwd,
    get_workspace_meta,
    mark_fs_observed,
)
from src.core_kernel.plugin_runtime.lifecycle import BasePlugin, PluginManifest

logger = logging.getLogger(__name__)

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "web-static",
    ".cursor",
    ".tox",
    ".nlm_run",
}

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "list_dir",
        "description": (
            "List files and directories under the session workspace. "
            "path is relative to workspace root (default '.')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside workspace", "default": "."},
            },
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a UTF-8 text file from the workspace. Prefer this over shell cat/type. "
            "Results include line numbers — use offset/limit to continue large files. "
            "You must read a file before editing or overwriting it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "offset": {"type": "integer", "description": "Start line (1-based)", "default": 1},
                "limit": {"type": "integer", "description": "Max lines to return", "default": 200},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create a new UTF-8 file, or completely replace an existing file's contents. "
            "Prefer edit_file for targeted changes. If the file already exists, you must have "
            "read_file'd it earlier in this turn (unless you just created it)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Apply a targeted edit: replace an exact substring. old_string must appear exactly once "
            "unless replace_all=true. Prefer edit_file over write_file for existing files. "
            "Read the file first in this turn. On failure, re-read and use a more unique anchor."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "run_shell",
        "description": (
            "Run a shell command with cwd=session workspace (local or remote SSH). "
            "Prefer small, non-interactive commands. Prefer glob/grep/read_file over find/cat/rg. "
            "Always inspect the exit/return code before continuing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "number", "default": 60},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_code",
        "description": (
            "Execute a short Python snippet in the session workspace (local). "
            "Prefer this over run_shell for quick calculations / parsing. "
            "Code runs with cwd=workspace; stdout/stderr are captured. "
            "Not a full PTC sandbox — no nested tool calls from inside the snippet."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source to run"},
                "timeout_seconds": {"type": "number", "default": 30},
            },
            "required": ["code"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the human a concise question via an interactive form ONLY when you hit a true "
            "blocker: missing credentials, irreversible choice, or product ambiguity that tools "
            "cannot resolve. Prefer inspection and then act — do NOT use this to confirm "
            "\"should I execute?\" after reading files, or to restate a plan for permission. "
            "If you recommend an option, put it first and append '(Recommended)' to that label. "
            "Supports multiple questions, single/multi select, and optional custom text. "
            "Do NOT use this to present a finished implementation plan — use exit_plan_mode instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short form title"},
                "questions": {
                    "type": "array",
                    "description": "One or more questions",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "prompt": {"type": "string"},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "label": {"type": "string"},
                                    },
                                    "required": ["id", "label"],
                                },
                            },
                            "allow_multiple": {"type": "boolean", "default": False},
                            "allow_custom": {"type": "boolean", "default": True},
                        },
                        "required": ["id", "prompt"],
                    },
                },
            },
            "required": ["questions"],
        },
    },
    {
        "name": "exit_plan_mode",
        "description": (
            "Use only in plan mode. Present your plan for the user's review and, on approval, "
            "leave plan mode. Send the COMPLETE plan as markdown, starting with a # heading "
            "that names it. The user may approve (carry out the plan from your next step) or "
            "keep planning — their feedback comes back in the tool result; revise and present again."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": "The complete plan, as markdown, starting with a # heading that names it.",
                },
            },
            "required": ["plan"],
        },
    },
    {
        "name": "todo_write",
        "description": (
            "Record and update a structured task list for the current work. Send the ENTIRE list "
            "every call — it REPLACES the previous list (no partial updates). Use it to plan "
            "multi-step work and show progress: add one todo per concrete step before you start. "
            "Keep AT MOST ONE todo in_progress at a time; while work remains, exactly one should "
            "be in_progress. Mark a todo completed the moment it is done (do not batch). Skip for "
            "trivial single-step tasks. Statuses: pending | in_progress | completed | cancelled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "The COMPLETE task list, replacing any previous list.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {
                                "type": "string",
                                "description": "What the task is — a short imperative line.",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                "description": "pending | in_progress | completed | cancelled",
                            },
                        },
                        "required": ["id", "content", "status"],
                    },
                },
            },
            "required": ["items"],
        },
    },
    {
        "name": "open_canvas",
        "description": (
            "Open a durable side-pane Canvas document for the user (beside chat). "
            "Use for large Mermaid/ECharts/Draw.io diagrams, markdown briefs, or tables "
            "instead of only dumping them in the chat bubble. Optionally writes "
            "`{cwd}/.nlm/canvases/` on local workspaces. The UI opens the Canvas automatically."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short tab title"},
                "kind": {
                    "type": "string",
                    "enum": ["markdown", "mermaid", "drawio", "echarts", "table", "delivery"],
                    "description": "Canvas document kind (default markdown)",
                },
                "body": {
                    "type": "string",
                    "description": "Document body: mermaid/drawio source, echarts JSON, markdown, or table JSON/markdown",
                },
                "file_name": {
                    "type": "string",
                    "description": "Optional file name under .nlm/canvases/ (default from title/kind)",
                },
                "persist": {
                    "type": "boolean",
                    "default": True,
                    "description": "Write under .nlm/canvases/ when local cwd is available",
                },
            },
            "required": ["body"],
        },
    },
    {
        "name": "glob",
        "description": (
            "Find files by glob (e.g. **/*.py, src/**/*.vue). Prefer this over shell find. "
            "Skips node_modules, .git, venv."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob relative to workspace root"},
                "path": {"type": "string", "description": "Subdirectory to search", "default": "."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "grep",
        "description": (
            "Search file contents with a regex. Prefer this over shell grep/rg. "
            "Returns path:line:text matches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python/JS-style regular expression"},
                "path": {"type": "string", "description": "File or directory, relative", "default": "."},
                "glob": {"type": "string", "description": "Optional filename glob, e.g. *.py"},
                "max_matches": {"type": "integer", "default": 80},
            },
            "required": ["pattern"],
        },
    },
]


def _require_cwd() -> str:
    cwd = get_workspace_cwd()
    if not cwd:
        raise ValidationAppError(
            "No workspace bound to this session. Create a chat with a workspace (working directory) first."
        )
    return cwd


def _edit_miss_hint(text: str, old: str) -> str:
    """Offer a short recovery hint when old_string is missing."""
    needle = (old or "").strip().splitlines()
    if not needle:
        return ""
    first = needle[0].strip()
    if len(first) < 4:
        return ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if first[:40] in line or (len(first) > 12 and first[:12] in line):
            lo = max(0, i - 1)
            hi = min(len(lines), i + 2)
            sample = " | ".join(lines[lo:hi])[:180]
            return f"nearby line {i + 1}: {sample}"
    return ""


def _is_ssh() -> bool:
    meta = get_workspace_meta()
    return (meta.get("workspace_kind") or meta.get("kind") or "") == "ssh"


def _ssh_host_id() -> str:
    return str(get_workspace_meta().get("ssh_host_id") or "").strip()


class WorkspaceToolsPlugin(BasePlugin):
    async def _on_init(self) -> None:
        return None

    async def _on_ready(self) -> None:
        self.manifest.tools = list(TOOLS)

    async def _on_invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "ask_user":
            raise PluginError("ask_user is handled by the agent runner, not invoked directly")
        if tool_name == "exit_plan_mode":
            raise PluginError("exit_plan_mode is handled by the agent runner, not invoked directly")
        cwd = _require_cwd()
        if _is_ssh():
            return await self._invoke_ssh(tool_name, cwd, arguments)
        if tool_name == "list_dir":
            return self._list_dir(cwd, str(arguments.get("path") or "."))
        if tool_name == "read_file":
            return self._read_file(
                cwd,
                str(arguments.get("path") or ""),
                offset=int(arguments.get("offset") or 1),
                limit=int(arguments.get("limit") or 200),
            )
        if tool_name == "write_file":
            return self._write_file(cwd, str(arguments.get("path") or ""), str(arguments.get("content") or ""))
        if tool_name == "edit_file":
            return self._edit_file(
                cwd,
                str(arguments.get("path") or ""),
                str(arguments.get("old_string") or ""),
                str(arguments.get("new_string") or ""),
                replace_all=bool(arguments.get("replace_all")),
            )
        if tool_name == "run_shell":
            return await self._run_shell(
                cwd,
                str(arguments.get("command") or ""),
                timeout=float(arguments.get("timeout_seconds") or 60),
            )
        if tool_name == "run_code":
            return await self._run_code(
                cwd,
                str(arguments.get("code") or ""),
                timeout=float(arguments.get("timeout_seconds") or 30),
            )
        if tool_name == "ask_user":
            raise PluginError("ask_user is handled by the agent runner, not invoked directly")
        if tool_name == "exit_plan_mode":
            raise PluginError("exit_plan_mode is handled by the agent runner, not invoked directly")
        if tool_name == "todo_write":
            return self._todo_write(arguments.get("items") or [])
        if tool_name == "open_canvas":
            return self._open_canvas(cwd, arguments)
        if tool_name == "glob":
            return self._glob(
                cwd,
                str(arguments.get("pattern") or ""),
                str(arguments.get("path") or "."),
            )
        if tool_name == "grep":
            return self._grep(
                cwd,
                str(arguments.get("pattern") or ""),
                str(arguments.get("path") or "."),
                glob=str(arguments.get("glob") or ""),
                max_matches=int(arguments.get("max_matches") or 80),
            )
        raise PluginError(f"unknown workspace tool: {tool_name}")

    async def _invoke_ssh(self, tool_name: str, cwd: str, arguments: Dict[str, Any]) -> Any:
        from src.adapters.workspaces.ssh_fs import get_remote_fs

        host_id = _ssh_host_id()
        if not host_id:
            raise ValidationAppError("ssh_host_id missing for remote workspace")
        fs = get_remote_fs(host_id, cwd)
        if tool_name == "list_dir":
            return await fs.list_dir(str(arguments.get("path") or "."))
        if tool_name == "read_file":
            rel = str(arguments.get("path") or "")
            out = await fs.read_file(
                rel,
                offset=int(arguments.get("offset") or 1),
                limit=int(arguments.get("limit") or 200),
            )
            mark_fs_observed(rel)
            return out
        if tool_name == "write_file":
            rel = str(arguments.get("path") or "")
            # Soft gate on SSH too — existence check via read observation
            # (create-new is allowed without prior read)
            try:
                await fs.read_file(rel, offset=1, limit=1)
                exists = True
            except Exception:
                exists = False
            if exists and not fs_was_observed(rel):
                raise ValidationAppError(
                    f'cannot overwrite "{rel}": file has not been read in this turn — '
                    "read_file first, or use edit_file for a targeted change"
                )
            out = await fs.write_file(rel, str(arguments.get("content") or ""))
            mark_fs_observed(rel)
            return out
        if tool_name == "edit_file":
            rel = str(arguments.get("path") or "")
            if not fs_was_observed(rel):
                raise ValidationAppError(
                    f'cannot modify "{rel}": file has not been read in this turn — '
                    "read_file, then retry the edit"
                )
            try:
                out = await fs.edit_file(
                    rel,
                    str(arguments.get("old_string") or ""),
                    str(arguments.get("new_string") or ""),
                    replace_all=bool(arguments.get("replace_all")),
                )
            except Exception as exc:
                msg = str(exc)
                if "not found" in msg.lower() or "old_string" in msg.lower():
                    raise ValidationAppError(
                        f'edit failed on "{rel}": {msg}. Re-read the file and use an exact unique anchor.'
                    ) from exc
                raise
            mark_fs_observed(rel)
            return out
        if tool_name == "run_shell":
            return await fs.run_shell(
                str(arguments.get("command") or ""),
                timeout=float(arguments.get("timeout_seconds") or 60),
            )
        if tool_name == "run_code":
            code = str(arguments.get("code") or "")
            timeout = float(arguments.get("timeout_seconds") or 30)
            # Remote: run via python -c (escaped) through SSH shell
            import base64

            b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
            cmd = (
                "python -c \"import base64,sys; "
                f"exec(base64.b64decode('{b64}').decode())\""
            )
            return await fs.run_shell(cmd, timeout=timeout)
        if tool_name == "todo_write":
            return self._todo_write(arguments.get("items") or [])
        if tool_name == "open_canvas":
            return self._open_canvas(cwd, arguments)
        if tool_name == "glob":
            return await fs.glob_files(
                str(arguments.get("pattern") or ""),
                str(arguments.get("path") or "."),
            )
        if tool_name == "grep":
            return await fs.grep(
                str(arguments.get("pattern") or ""),
                str(arguments.get("path") or "."),
                glob=str(arguments.get("glob") or ""),
                max_matches=int(arguments.get("max_matches") or 80),
            )
        raise PluginError(f"unknown workspace tool: {tool_name}")

    async def _on_teardown(self) -> None:
        return None

    def _list_dir(self, cwd: str, rel: str) -> Dict[str, Any]:
        target = resolve_under_workspace(cwd, rel)
        if not target.exists():
            raise FileNotFoundError(str(target))
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        entries = []
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:200]:
            entries.append(
                {
                    "name": child.name,
                    "path": str(child.relative_to(Path(cwd).resolve())),
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"cwd": cwd, "path": rel, "entries": entries, "kind": "local"}

    def _read_file(self, cwd: str, rel: str, *, offset: int, limit: int) -> Dict[str, Any]:
        target = resolve_under_workspace(cwd, rel)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = max(1, offset) - 1
        end = start + max(1, min(limit, 400))
        slice_lines = lines[start:end]
        numbered = "\n".join(f"{i + start + 1:>5}|{line}" for i, line in enumerate(slice_lines))
        from src.core_kernel.tool_output import truncate_tool_text

        numbered, cut = truncate_tool_text(numbered)
        mark_fs_observed(rel)
        return {
            "path": rel,
            "total_lines": len(lines),
            "offset": start + 1,
            "limit": end - start,
            "content": numbered,
            "truncated": end < len(lines) or cut,
            "kind": "local",
        }

    def _write_file(self, cwd: str, rel: str, content: str) -> Dict[str, Any]:
        target = resolve_under_workspace(cwd, rel)
        existed = target.is_file()
        if existed and not fs_was_observed(rel):
            raise ValidationAppError(
                f'cannot overwrite "{rel}": file has not been read in this turn — '
                "read_file first, or use edit_file for a targeted change"
            )
        previous = None
        if existed:
            try:
                previous = target.read_text(encoding="utf-8", errors="replace")
                # Cap so tool_result / DiffDock stay bounded
                if len(previous) > 200_000:
                    previous = previous[:200_000]
            except OSError:
                previous = None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        mark_fs_observed(rel)
        out: Dict[str, Any] = {
            "ok": True,
            "path": rel,
            "bytes": len(content.encode("utf-8")),
            "created": not existed,
            "kind": "local",
        }
        if previous is not None:
            out["previous"] = previous
        return out

    def _edit_file(
        self,
        cwd: str,
        rel: str,
        old: str,
        new: str,
        *,
        replace_all: bool,
    ) -> Dict[str, Any]:
        target = resolve_under_workspace(cwd, rel)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        if not fs_was_observed(rel):
            raise ValidationAppError(
                f'cannot modify "{rel}": file has not been read in this turn — '
                "read_file, then retry the edit"
            )
        text = target.read_text(encoding="utf-8")
        if old not in text:
            hint = _edit_miss_hint(text, old)
            raise ValidationAppError(
                f'old_string not found in "{rel}". Re-read the file and use an exact unique anchor.'
                + (f" Hint: {hint}" if hint else "")
            )
        count = text.count(old)
        if count > 1 and not replace_all:
            raise ValidationAppError(
                f'old_string found {count} times in "{rel}"; set replace_all=true or provide a more unique old_string'
            )
        updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        target.write_text(updated, encoding="utf-8")
        mark_fs_observed(rel)
        return {"ok": True, "path": rel, "replacements": count if replace_all else 1, "kind": "local"}

    def _todo_write(self, items: Any) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        if not isinstance(items, list):
            raise ValidationAppError("items must be an array")
        in_progress = 0
        for raw in items:
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status") or "pending").strip().lower()
            if status not in {"pending", "in_progress", "completed", "cancelled"}:
                status = "pending"
            if status == "in_progress":
                in_progress += 1
            rows.append(
                {
                    "id": str(raw.get("id") or f"t{len(rows)+1}"),
                    "content": str(raw.get("content") or "").strip(),
                    "status": status,
                }
            )
        if in_progress > 1:
            raise ValidationAppError("at most one todo may be in_progress")
        # Drop empty content rows (DSH-style: content must be meaningful)
        rows = [r for r in rows if r["content"]]
        counts = {
            "pending": sum(1 for r in rows if r["status"] == "pending"),
            "in_progress": sum(1 for r in rows if r["status"] == "in_progress"),
            "completed": sum(1 for r in rows if r["status"] == "completed"),
            "cancelled": sum(1 for r in rows if r["status"] == "cancelled"),
        }
        return {
            "ok": True,
            "items": rows,
            "todos": rows,
            "count": len(rows),
            "counts": counts,
            "summary": (
                f"Updated todo list: {counts['pending']} pending, "
                f"{counts['in_progress']} in progress, {counts['completed']} completed."
            ),
        }

    def _open_canvas(self, cwd: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from src.common.canvas_store import CanvasWriteError, write_canvas_to_workspace

        body = str(arguments.get("body") or "")
        if not body.strip():
            raise ValidationAppError("body is required")
        kind = str(arguments.get("kind") or "markdown").strip().lower() or "markdown"
        allowed = {"markdown", "mermaid", "drawio", "echarts", "table", "delivery"}
        if kind not in allowed:
            kind = "markdown"
        title = str(arguments.get("title") or "").strip() or kind.title()
        persist = arguments.get("persist")
        if persist is None:
            persist = True
        file_name = str(arguments.get("file_name") or "").strip()
        if not file_name:
            safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", title).strip("._") or kind
            ext = ".json" if kind in {"echarts", "table"} else ".md"
            if kind == "drawio":
                ext = ".drawio.xml"
            elif kind == "mermaid":
                ext = ".mmd"
            file_name = f"{safe}{ext}"

        path = ""
        persist_error = ""
        if persist:
            try:
                if kind == "mermaid" and "```" not in body:
                    disk_body = f"# {title}\n\n```mermaid\n{body.strip()}\n```\n"
                elif kind == "echarts" and not body.strip().startswith("```"):
                    disk_body = f"# {title}\n\n```echarts\n{body.strip()}\n```\n"
                elif kind == "drawio" and "<mx" in body and "```" not in body:
                    disk_body = f"# {title}\n\n```drawio\n{body.strip()}\n```\n"
                else:
                    disk_body = body if body.lstrip().startswith("#") else f"# {title}\n\n{body}"
                out = write_canvas_to_workspace(cwd, file_name=file_name, content=disk_body)
                path = str(out.get("path") or "")
            except CanvasWriteError as exc:
                persist_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                persist_error = str(exc)

        return {
            "ok": True,
            "kind": kind,
            "title": title,
            "body": body,
            "path": path,
            "persist_error": persist_error or None,
            "dedupe_key": path or f"open_canvas:{kind}:{title}",
        }

    async def _run_shell(self, cwd: str, command: str, *, timeout: float) -> Dict[str, Any]:
        command = (command or "").strip()
        if not command:
            raise ValidationAppError("command required")
        root = resolve_under_workspace(cwd, ".")
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                "cmd.exe",
                "/c",
                command,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                "/bin/bash",
                "-lc",
                command,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=max(5.0, timeout))
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise PluginError(f"shell timeout after {timeout}s") from exc
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")

        from src.core_kernel.tool_output import truncate_tool_text

        out_s, out_cut = truncate_tool_text(out)
        err_s, err_cut = truncate_tool_text(err)
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "cwd": str(root),
            "stdout": out_s,
            "stderr": err_s,
            "truncated": out_cut or err_cut,
            "kind": "local",
        }

    async def _run_code(self, cwd: str, code: str, *, timeout: float) -> Dict[str, Any]:
        """Run Python snippet in workspace cwd (local process)."""
        import sys
        import tempfile

        code = (code or "").strip()
        if not code:
            raise ValidationAppError("code required")
        if len(code) > 80_000:
            raise ValidationAppError("code too large (max 80k chars)")
        root = resolve_under_workspace(cwd, ".")
        run_dir = root / ".nlm_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        # Write temp script under workspace so relative imports/paths stay sandboxed to cwd.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".py",
            dir=str(run_dir),
            delete=False,
        ) as fh:
            fh.write(code)
            script = fh.name
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                script,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=max(3.0, timeout)
                )
            except asyncio.TimeoutError as exc:
                proc.kill()
                raise PluginError(f"run_code timeout after {timeout}s") from exc
        finally:
            try:
                Path(script).unlink(missing_ok=True)
            except Exception:
                pass

        def _trim(s: str, n: int = 12000) -> str:
            return s if len(s) <= n else s[:n] + "\n…[truncated]"

        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "cwd": str(root),
            "stdout": _trim(out),
            "stderr": _trim(err),
            "kind": "run_code",
            "runtime": "python",
        }

    def _glob(self, cwd: str, pattern: str, rel: str) -> Dict[str, Any]:
        pattern = (pattern or "").strip()
        if not pattern:
            raise ValidationAppError("pattern required")
        root = resolve_under_workspace(cwd, rel or ".")
        if not root.exists():
            raise FileNotFoundError(str(root))
        cwd_root = Path(cwd).resolve()
        hits: List[str] = []
        truncated = False
        if root.is_file():
            rel_path = root.relative_to(cwd_root).as_posix()
            if _glob_match(rel_path, root.name, pattern):
                hits.append(rel_path)
        else:
            for path in _walk_files(root):
                rel_path = path.relative_to(cwd_root).as_posix()
                if not _glob_match(rel_path, path.name, pattern):
                    continue
                hits.append(rel_path)
                if len(hits) >= 200:
                    truncated = True
                    break
        return {"cwd": cwd, "pattern": pattern, "path": rel, "files": hits, "truncated": truncated, "kind": "local"}

    def _grep(
        self,
        cwd: str,
        pattern: str,
        rel: str,
        *,
        glob: str,
        max_matches: int,
    ) -> Dict[str, Any]:
        if not (pattern or "").strip():
            raise ValidationAppError("pattern required")
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            raise ValidationAppError(f"invalid regex: {exc}") from exc
        target = resolve_under_workspace(cwd, rel or ".")
        if not target.exists():
            raise FileNotFoundError(str(target))
        cwd_root = Path(cwd).resolve()
        files = [target] if target.is_file() else list(_walk_files(target))
        matches: List[Dict[str, Any]] = []
        truncated = False
        scanned = 0
        for path in files:
            rel_path = path.relative_to(cwd_root).as_posix()
            if glob and not _glob_match(rel_path, path.name, glob):
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    matches.append({"path": rel_path, "line": i, "text": line[:400]})
                    if len(matches) >= max(1, min(max_matches, 200)):
                        truncated = True
                        break
            if truncated:
                break
        return {
            "cwd": cwd,
            "pattern": pattern,
            "path": rel,
            "matches": matches,
            "match_count": len(matches),
            "files_scanned": scanned,
            "truncated": truncated,
            "kind": "local",
        }


def _walk_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for name in filenames:
            yield Path(dirpath) / name


def _glob_match(rel_path: str, name: str, pattern: str) -> bool:
    pat = pattern.replace("\\", "/").lstrip("./")
    rel = rel_path.replace("\\", "/")
    if "**" in pat:
        # fnmatch does not treat ** as recursive; flatten to * for path match.
        flat = pat.replace("**/", "*").replace("**", "*")
        return fnmatch.fnmatch(rel, flat) or fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat.split("/")[-1])
    return fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)


def workspace_tools_manifest() -> PluginManifest:
    return PluginManifest(
        plugin_id="builtin.workspace",
        name="Workspace",
        kind="inprocess",
        version="1.2.0",
        description="Session workspace tools (local or SSH): glob/grep/list/read/write/edit/run_shell/run_code/ask_user/exit_plan_mode/todo_write/open_canvas.",
        tools=list(TOOLS),
    )
