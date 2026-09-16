"""Skills — progressive disclosure of task playbooks (Pi-inspired).

Layout (first match wins per skill name):
  <cwd>/.nlm/skills/<name>/SKILL.md
  <cwd>/.agents/skills/<name>/SKILL.md

SKILL.md front matter (optional YAML between ---):
  ---
  name: verify-change
  description: Run focused tests after code edits
  ---
  # body (full instructions; model reads via read_file when needed)

System prompt only lists name + description so large playbooks stay out of
the default context window.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: str
    body: str = ""


_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    body = text
    m = _FRONT_MATTER.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
        body = text[m.end() :]
    return meta, body.strip()


def _first_heading(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return re.sub(r"^#+\s*", "", s).strip()
    return ""


def discover_skills(cwd: str, *, max_skills: int = 40) -> List[SkillInfo]:
    """Scan skill directories under cwd; later dirs do not override earlier names."""
    root = Path(cwd)
    if not root.is_dir():
        return []
    found: dict[str, SkillInfo] = {}
    search_roots = [
        root / ".nlm" / "skills",
        root / ".agents" / "skills",
    ]
    for base in search_roots:
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in children:
            if len(found) >= max_skills:
                break
            skill_md = child / "SKILL.md" if child.is_dir() else None
            if child.is_file() and child.name.lower() == "skill.md":
                skill_md = child
                child = child.parent
            if skill_md is None or not skill_md.is_file():
                continue
            try:
                raw = skill_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta, body = _parse_front_matter(raw)
            name = (meta.get("name") or child.name).strip()
            if not name or name in found:
                continue
            desc = (meta.get("description") or _first_heading(body) or name).strip()
            if len(desc) > 240:
                desc = desc[:237] + "…"
            try:
                rel = str(skill_md.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = str(skill_md)
            found[name] = SkillInfo(name=name, description=desc, path=rel, body=body)
    return list(found.values())


def skills_prompt_block(cwd: str, *, max_skills: int = 40) -> str:
    skills = discover_skills(cwd, max_skills=max_skills)
    if not skills:
        return ""
    lines = [
        "## Available skills (progressive disclosure)",
        "These are optional playbooks. The catalog below is only name + description —",
        "do **not** assume full instructions are loaded. When a skill matches the task,",
        "call `read_file` on its path, follow it, then continue.",
        "",
    ]
    for s in skills:
        lines.append(f"- `{s.name}` — {s.description}")
        lines.append(f"  path: `{s.path}`")
    lines.append("")
    lines.append(
        "User may invoke a skill with `/skill:<name>` in their message; treat that as "
        "a request to load and follow that skill."
    )
    return "\n".join(lines)


def list_skills_public(cwd: str) -> List[dict]:
    return [
        {"name": s.name, "description": s.description, "path": s.path}
        for s in discover_skills(cwd)
    ]


def resolve_skill(cwd: str, name: str) -> Optional[SkillInfo]:
    key = (name or "").strip()
    if not key:
        return None
    for s in discover_skills(cwd):
        if s.name == key or s.name.lower() == key.lower():
            return s
    return None
