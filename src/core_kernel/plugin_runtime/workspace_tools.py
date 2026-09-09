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
from src.core_kernel.plugin_runtime.invoke_context import get_workspace_cwd, get_workspace_meta
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
        "description": "Read a UTF-8 text file from the session workspace (truncated if large).",
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
        "description": "Create or overwrite a UTF-8 text file inside the workspace.",
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
        "description": "Replace an exact substring in a workspace file (old_string must be unique unless replace_all).",
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
            "Run a shell command with cwd=session workspace "
            "(local or remote SSH). Prefer small, non-interactive commands."
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
        "name": "ask_user",
        "description": (
            "Ask the human clarifying questions via an interactive form. "
            "Use when requirements are ambiguous (especially in plan mode). "
            "Supports multiple questions, single/multi select, and optional custom text."
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
        "name": "glob",
        "description": (
            "Find files in the workspace by glob pattern (e.g. **/*.py, src/**/*.vue). "
            "Skips node_modules, .git, venv. Use this before blindly listing directories."
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
            "Search file contents in the workspace with a regex. "
            "Returns path:line:text matches. Prefer grep over reading every file."
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
        if tool_name == "ask_user":
            raise PluginError("ask_user is handled by the agent runner, not invoked directly")
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
            return await fs.read_file(
                str(arguments.get("path") or ""),
                offset=int(arguments.get("offset") or 1),
                limit=int(arguments.get("limit") or 200),
            )
        if tool_name == "write_file":
            return await fs.write_file(str(arguments.get("path") or ""), str(arguments.get("content") or ""))
        if tool_name == "edit_file":
            return await fs.edit_file(
                str(arguments.get("path") or ""),
                str(arguments.get("old_string") or ""),
                str(arguments.get("new_string") or ""),
                replace_all=bool(arguments.get("replace_all")),
            )
        if tool_name == "run_shell":
            return await fs.run_shell(
                str(arguments.get("command") or ""),
                timeout=float(arguments.get("timeout_seconds") or 60),
            )
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
        return {
            "path": rel,
            "total_lines": len(lines),
            "offset": start + 1,
            "limit": end - start,
            "content": numbered,
            "truncated": end < len(lines),
            "kind": "local",
        }

    def _write_file(self, cwd: str, rel: str, content: str) -> Dict[str, Any]:
        target = resolve_under_workspace(cwd, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": rel, "bytes": len(content.encode("utf-8")), "kind": "local"}

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
        text = target.read_text(encoding="utf-8")
        if old not in text:
            raise ValidationAppError("old_string not found in file")
        count = text.count(old)
        if count > 1 and not replace_all:
            raise ValidationAppError(f"old_string found {count} times; set replace_all or make it unique")
        updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        target.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": rel, "replacements": count if replace_all else 1, "kind": "local"}

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

        def _trim(s: str, n: int = 12000) -> str:
            return s if len(s) <= n else s[:n] + "\n…[truncated]"

        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "cwd": str(root),
            "stdout": _trim(out),
            "stderr": _trim(err),
            "kind": "local",
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
        description="Session workspace tools (local or SSH): glob/grep/list/read/write/edit/run_shell/ask_user.",
        tools=list(TOOLS),
    )
