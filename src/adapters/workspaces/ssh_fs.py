"""Async SSH/SFTP helpers for remote coding workspaces."""

from __future__ import annotations

import logging
import posixpath
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from pathlib import Path

from src.adapters.workspaces.ssh_config import ssh_config_path
from src.adapters.workspaces.ssh_store import SshHostRecord, get_ssh_host_store
from src.common.errors import UpstreamError, ValidationAppError

logger = logging.getLogger(__name__)


def _posix_join(root: str, rel: str) -> str:
    root = root or "/"
    rel = (rel or ".").strip() or "."
    if rel.startswith("/"):
        candidate = posixpath.normpath(rel)
    else:
        candidate = posixpath.normpath(posixpath.join(root, rel))
    # Escape guard
    root_n = posixpath.normpath(root)
    if root_n != "/" and not (candidate == root_n or candidate.startswith(root_n.rstrip("/") + "/")):
        raise PermissionError(f"path escapes workspace: {candidate}")
    if root_n == "/" and not candidate.startswith("/"):
        raise PermissionError(f"path escapes workspace: {candidate}")
    return candidate


async def _connect_options(host: SshHostRecord) -> Dict[str, Any]:
    if host.source == "ssh_config" and host.ssh_config_alias:
        cfg = ssh_config_path()
        if not cfg.exists():
            raise ValidationAppError(f"ssh config not found: {cfg}")
        return {
            "host": host.ssh_config_alias,
            "config": str(cfg),
            "known_hosts": None,
            "login_timeout": 20,
        }

    opts: Dict[str, Any] = {
        "host": host.host,
        "port": int(host.port or 22),
        "username": host.username,
        "known_hosts": None,
        "login_timeout": 20,
    }
    if host.auth_type in {"key", "agent"} or (host.private_key and not host.password):
        key = (host.private_key or "").strip()
        if key:
            if "BEGIN" in key:
                opts["client_keys"] = [asyncssh_import_key(key, host.private_key_passphrase)]
            else:
                p = Path(key).expanduser()
                if p.exists():
                    opts["client_keys"] = [str(p)]
                else:
                    opts["client_keys"] = [key]
                if host.private_key_passphrase:
                    opts["passphrase"] = host.private_key_passphrase
        elif host.auth_type == "agent":
            # rely on ssh-agent / default keys
            pass
        else:
            raise ValidationAppError("private_key required for key auth")
    else:
        if not host.password:
            raise ValidationAppError("password required for password auth")
        opts["password"] = host.password
    return opts


def asyncssh_import_key(pem: str, passphrase: str = ""):
    import asyncssh

    return asyncssh.import_private_key(pem, passphrase=passphrase or None)


@asynccontextmanager
async def ssh_connection(host: SshHostRecord) -> AsyncIterator[Any]:
    try:
        import asyncssh
    except ImportError as exc:
        raise UpstreamError("asyncssh not installed; pip install asyncssh") from exc
    opts = await _connect_options(host)
    try:
        conn = await asyncssh.connect(**opts)
    except Exception as exc:
        raise UpstreamError(f"SSH connect failed: {exc}") from exc
    try:
        yield conn
    finally:
        conn.close()
        await conn.wait_closed()


async def test_ssh_host(host: SshHostRecord) -> Dict[str, Any]:
    async with ssh_connection(host) as conn:
        result = await conn.run("pwd && whoami && uname -a", check=False)
        out = (result.stdout or "").strip()
        return {
            "ok": result.exit_status == 0,
            "exit_status": result.exit_status,
            "message": "SSH 连通成功" if result.exit_status == 0 else "SSH 已连接但探测命令失败",
            "output": out[:800],
            "display": f"{host.username}@{host.host}:{host.port}",
        }


async def expand_remote_path(conn: Any, path: str) -> str:
    raw = (path or "~").strip() or "~"
    if raw == "~" or raw.startswith("~/"):
        result = await conn.run("printf %s \"$HOME\"", check=False)
        home = (result.stdout or "").strip()
        if not home:
            raise UpstreamError("cannot resolve remote HOME")
        if raw == "~":
            return home
        return posixpath.normpath(posixpath.join(home, raw[2:]))
    return posixpath.normpath(raw)


async def browse_remote(host: SshHostRecord, path: str = "") -> Dict[str, Any]:
    async with ssh_connection(host) as conn:
        async with conn.start_sftp_client() as sftp:
            root = await expand_remote_path(conn, path or host.default_path or "~")
            try:
                names = await sftp.listdir(root)
            except Exception as exc:
                raise UpstreamError(f"cannot list {root}: {exc}") from exc
            entries: List[Dict[str, Any]] = []
            for name in sorted(names, key=lambda n: (not str(n).startswith("."), str(n).lower()))[:200]:
                if name in {".", ".."}:
                    continue
                full = posixpath.join(root, name)
                is_dir = False
                is_file = False
                try:
                    attrs = await sftp.stat(full)
                    from asyncssh import S_ISDIR, S_ISREG

                    mode = attrs.permissions or 0
                    is_dir = bool(S_ISDIR(mode))
                    is_file = bool(S_ISREG(mode))
                except Exception:
                    pass
                entries.append(
                    {
                        "name": name,
                        "path": full,
                        "is_dir": is_dir,
                        "is_file": is_file,
                    }
                )
            parent = posixpath.dirname(root.rstrip("/")) or "/"
            if parent == root:
                parent = None
            return {
                "path": root,
                "parent": parent,
                "entries": entries,
                "title": posixpath.basename(root.rstrip("/")) or root,
                "ssh_host_id": host.id,
                "kind": "ssh",
            }


async def ensure_remote_dir(host: SshHostRecord, path: str) -> str:
    async with ssh_connection(host) as conn:
        async with conn.start_sftp_client() as sftp:
            root = await expand_remote_path(conn, path)
            try:
                attrs = await sftp.stat(root)
            except Exception as exc:
                raise FileNotFoundError(f"path does not exist: {root}") from exc
            from asyncssh import S_ISDIR

            if not S_ISDIR(attrs.permissions or 0):
                raise NotADirectoryError(f"not a directory: {root}")
            return root


class RemoteWorkspaceFs:
    """SFTP + remote shell scoped to a remote workspace root."""

    def __init__(self, host: SshHostRecord, root: str) -> None:
        self.host = host
        self.root = posixpath.normpath(root)

    def resolve(self, rel: str = ".") -> str:
        return _posix_join(self.root, rel)

    async def list_dir(self, rel: str = ".") -> Dict[str, Any]:
        target = self.resolve(rel)
        async with ssh_connection(self.host) as conn:
            async with conn.start_sftp_client() as sftp:
                names = await sftp.listdir(target)
                entries = []
                for name in sorted(names, key=lambda n: str(n).lower())[:200]:
                    if name in {".", ".."}:
                        continue
                    full = posixpath.join(target, name)
                    is_dir = False
                    size = None
                    try:
                        attrs = await sftp.stat(full)
                        from asyncssh import S_ISDIR

                        is_dir = bool(S_ISDIR(attrs.permissions or 0))
                        size = attrs.size if not is_dir else None
                    except Exception:
                        pass
                    rel_path = posixpath.relpath(full, self.root)
                    entries.append({"name": name, "path": rel_path, "is_dir": is_dir, "size": size})
                return {"cwd": self.root, "path": rel, "entries": entries, "kind": "ssh"}

    async def read_file(self, rel: str, *, offset: int = 1, limit: int = 200) -> Dict[str, Any]:
        target = self.resolve(rel)
        async with ssh_connection(self.host) as conn:
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(target, "r") as f:
                    raw = await f.read()
                if isinstance(raw, bytes):
                    text = raw.decode("utf-8", errors="replace")
                else:
                    text = str(raw)
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
            "kind": "ssh",
        }

    async def write_file(self, rel: str, content: str) -> Dict[str, Any]:
        target = self.resolve(rel)
        parent = posixpath.dirname(target)
        async with ssh_connection(self.host) as conn:
            async with conn.start_sftp_client() as sftp:
                if parent and parent != "/":
                    await self._mkdir_p(sftp, parent)
                async with sftp.open(target, "w") as f:
                    await f.write(content)
        return {"ok": True, "path": rel, "bytes": len(content.encode("utf-8")), "kind": "ssh"}

    async def edit_file(
        self,
        rel: str,
        old: str,
        new: str,
        *,
        replace_all: bool,
    ) -> Dict[str, Any]:
        target = self.resolve(rel)
        async with ssh_connection(self.host) as conn:
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(target, "r") as f:
                    raw = await f.read()
                text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                if old not in text:
                    raise ValidationAppError("old_string not found in file")
                count = text.count(old)
                if count > 1 and not replace_all:
                    raise ValidationAppError(f"old_string found {count} times; set replace_all or make it unique")
                updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
                async with sftp.open(target, "w") as f:
                    await f.write(updated)
        return {"ok": True, "path": rel, "replacements": count if replace_all else 1, "kind": "ssh"}

    async def run_shell(self, command: str, *, timeout: float = 60) -> Dict[str, Any]:
        command = (command or "").strip()
        if not command:
            raise ValidationAppError("command required")
        # Quote remote cwd for bash
        root = self.root.replace("'", "'\"'\"'")
        wrapped = f"cd '{root}' && {command}"
        async with ssh_connection(self.host) as conn:
            try:
                result = await conn.run(wrapped, check=False, timeout=max(5.0, timeout))
            except Exception as exc:
                raise UpstreamError(f"remote shell failed: {exc}") from exc

        def _trim(s: str, n: int = 12000) -> str:
            s = s or ""
            return s if len(s) <= n else s[:n] + "\n…[truncated]"

        return {
            "ok": result.exit_status == 0,
            "exit_code": result.exit_status,
            "cwd": self.root,
            "stdout": _trim(result.stdout or ""),
            "stderr": _trim(result.stderr or ""),
            "kind": "ssh",
        }

    async def glob_files(self, pattern: str, rel: str = ".") -> Dict[str, Any]:
        pattern = (pattern or "").strip()
        if not pattern:
            raise ValidationAppError("pattern required")
        target = self.resolve(rel or ".")
        quoted_pat = pattern.replace("'", "'\"'\"'")
        quoted_root = target.replace("'", "'\"'\"'")
        cmd = (
            f"cd '{quoted_root}' && "
            f"(rg --files -g '{quoted_pat}' --glob '!node_modules' --glob '!.git' --glob '!__pycache__' 2>/dev/null "
            f"|| find . -name '{quoted_pat}' -not -path '*/node_modules/*' -not -path '*/.git/*' | head -n 200)"
        )
        data = await self.run_shell(cmd, timeout=30)
        files = []
        for line in (data.get("stdout") or "").splitlines():
            line = line.strip().lstrip("./")
            if line:
                files.append(line if rel in {".", ""} else posixpath.join(rel, line).replace("\\", "/"))
            if len(files) >= 200:
                break
        return {
            "cwd": self.root,
            "pattern": pattern,
            "path": rel,
            "files": files,
            "truncated": len(files) >= 200,
            "kind": "ssh",
        }

    async def grep(self, pattern: str, rel: str = ".", *, glob: str = "", max_matches: int = 80) -> Dict[str, Any]:
        pattern = (pattern or "").strip()
        if not pattern:
            raise ValidationAppError("pattern required")
        target = self.resolve(rel or ".")
        q_pat = pattern.replace("'", "'\"'\"'")
        q_target = target.replace("'", "'\"'\"'")
        extra = f" -g '{glob.replace(chr(39), '')}'" if glob else ""
        limit = max(1, min(int(max_matches or 80), 200))
        cmd = (
            f"rg -n --no-heading -S --glob '!node_modules' --glob '!.git'{extra} '{q_pat}' '{q_target}' 2>/dev/null "
            f"| head -n {limit}"
        )
        data = await self.run_shell(cmd, timeout=40)
        matches = []
        stdout = data.get("stdout") or ""
        if not stdout.strip() and data.get("exit_code") not in (0, 1):
            # fallback grep
            data = await self.run_shell(
                f"grep -RIn --exclude-dir=node_modules --exclude-dir=.git '{q_pat}' '{q_target}' | head -n {limit}",
                timeout=40,
            )
            stdout = data.get("stdout") or ""
        for line in stdout.splitlines():
            # path:line:text
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            path, ln, text = parts[0], parts[1], parts[2]
            try:
                lineno = int(ln)
            except ValueError:
                continue
            rel_path = path
            if path.startswith(self.root):
                rel_path = posixpath.relpath(path, self.root)
            matches.append({"path": rel_path, "line": lineno, "text": text[:400]})
        return {
            "cwd": self.root,
            "pattern": pattern,
            "path": rel,
            "matches": matches,
            "match_count": len(matches),
            "truncated": len(matches) >= limit,
            "kind": "ssh",
        }

    async def _mkdir_p(self, sftp: Any, path: str) -> None:
        parts = []
        cur = path
        while cur and cur != "/":
            parts.append(cur)
            parent = posixpath.dirname(cur)
            if parent == cur:
                break
            cur = parent
        for p in reversed(parts):
            try:
                await sftp.stat(p)
            except Exception:
                try:
                    await sftp.mkdir(p)
                except Exception:
                    pass


def get_remote_fs(ssh_host_id: str, root: str) -> RemoteWorkspaceFs:
    host = get_ssh_host_store().get(ssh_host_id)
    if not host:
        raise ValidationAppError(f"ssh host not found: {ssh_host_id}")
    return RemoteWorkspaceFs(host, root)
