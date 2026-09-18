"""Best-effort local git snapshot for the agent prompt (Pi harness analogue)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict


def workspace_git_snapshot(cwd: str, *, timeout: float = 2.5) -> Dict[str, Any]:
    root = Path((cwd or "").strip())
    empty: Dict[str, Any] = {
        "is_repo": False,
        "branch": "",
        "dirty": False,
        "insertions": 0,
        "deletions": 0,
        "changed_files": 0,
    }
    if not cwd or not root.is_dir():
        return empty

    def _git(*args: str) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            return ""
        return (proc.stdout or "").strip()

    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        if not branch:
            return empty
        short = _git("diff", "--shortstat", "HEAD")
        porcelain = _git("status", "--porcelain")
    except Exception:
        return empty

    insertions = deletions = 0
    import re

    m_ins = re.search(r"(\d+)\s+insertion", short)
    m_del = re.search(r"(\d+)\s+deletion", short)
    if m_ins:
        insertions = int(m_ins.group(1))
    if m_del:
        deletions = int(m_del.group(1))
    changed = len([ln for ln in porcelain.splitlines() if ln.strip()]) if porcelain else 0
    return {
        "is_repo": True,
        "branch": branch,
        "dirty": bool(changed or insertions or deletions),
        "insertions": insertions,
        "deletions": deletions,
        "changed_files": changed,
    }


def format_git_prompt_block(snap: Dict[str, Any]) -> str:
    if not snap.get("is_repo"):
        return ""
    branch = snap.get("branch") or "?"
    lines = [f"## Git", f"- branch: `{branch}`"]
    if snap.get("dirty"):
        lines.append(
            f"- working tree: dirty ({snap.get('changed_files') or 0} files, "
            f"+{snap.get('insertions') or 0}/-{snap.get('deletions') or 0})"
        )
    else:
        lines.append("- working tree: clean")
    return "\n".join(lines)
