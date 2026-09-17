"""Prompt templates — slash-command expansion (Pi-inspired).

Layout:
  <cwd>/.nlm/prompts/<name>.md
  plugins_volume/prompts/<name>.md

Front matter:
  ---
  name: review
  description: Code review checklist
  variables: FILE,FOCUS
  ---
  Review `$FILE` focusing on $FOCUS …
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_VAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    description: str
    path: str
    body: str
    variables: Tuple[str, ...] = ()


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


def _prompt_dirs(cwd: Optional[str] = None) -> List[Path]:
    paths: List[Path] = []
    if cwd:
        paths.append(Path(cwd) / ".nlm" / "prompts")
    paths.append(Path("plugins_volume") / "prompts")
    root = Path(__file__).resolve().parents[2]
    paths.append(root / "plugins_volume" / "prompts")
    return paths


def discover_prompt_templates(cwd: Optional[str] = None, *, max_templates: int = 60) -> List[PromptTemplate]:
    found: Dict[str, PromptTemplate] = {}
    for base in _prompt_dirs(cwd):
        if not base.is_dir():
            continue
        try:
            files = sorted(base.glob("*.md"))
        except OSError:
            continue
        for path in files:
            if len(found) >= max_templates:
                break
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta, body = _parse_front_matter(raw)
            name = (meta.get("name") or path.stem).strip()
            if not name or name in found:
                continue
            desc = (meta.get("description") or name).strip()
            vars_raw = meta.get("variables") or ""
            variables = tuple(
                v.strip() for v in re.split(r"[,|\s]+", vars_raw) if v.strip()
            )
            # Auto-detect $VARS in body if not declared
            if not variables:
                variables = tuple(sorted(set(_VAR.findall(body))))
            try:
                rel = str(path)
                if cwd:
                    try:
                        rel = str(path.relative_to(Path(cwd))).replace("\\", "/")
                    except ValueError:
                        pass
            except Exception:
                rel = str(path)
            found[name] = PromptTemplate(
                name=name,
                description=desc[:240],
                path=rel.replace("\\", "/"),
                body=body,
                variables=variables,
            )
    return list(found.values())


def resolve_prompt_template(cwd: Optional[str], name: str) -> Optional[PromptTemplate]:
    key = (name or "").strip().lstrip("/")
    if not key:
        return None
    for t in discover_prompt_templates(cwd):
        if t.name == key or t.name.lower() == key.lower():
            return t
    return None


def expand_prompt_template(
    template: PromptTemplate,
    variables: Optional[Dict[str, str]] = None,
    *,
    positional: Optional[List[str]] = None,
) -> str:
    """Replace $VAR placeholders. Positional args fill declared variables in order."""
    vals = dict(variables or {})
    if positional and template.variables:
        for i, key in enumerate(template.variables):
            if i < len(positional) and key not in vals:
                vals[key] = positional[i]
    # Also map common aliases: first positional → $FILE / $ARG0
    if positional:
        if "FILE" not in vals and positional:
            vals["FILE"] = positional[0]
        if "ARGS" not in vals:
            vals["ARGS"] = " ".join(positional)
        for i, p in enumerate(positional):
            vals.setdefault(f"ARG{i}", p)

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return vals.get(key, m.group(0))

    return _VAR.sub(repl, template.body)


def expand_slash_command(cwd: Optional[str], text: str) -> Optional[Dict[str, str]]:
    """If text starts with /name …, expand to prompt body.

    Returns {name, prompt, original} or None if not a template slash.
    """
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    # /skill: is owned by skills
    if raw.lower().startswith("/skill:"):
        return None
    parts = raw.split(None, 1)
    cmd = parts[0][1:].strip()
    rest = parts[1] if len(parts) > 1 else ""
    if not cmd or ":" in cmd:
        return None
    tmpl = resolve_prompt_template(cwd, cmd)
    if not tmpl:
        from src.core_kernel.extension_runtime import apply_extension_slash_command

        return apply_extension_slash_command(raw)
    positional = rest.split() if rest else []
    # Also support KEY=value pairs
    named: Dict[str, str] = {}
    pos_only: List[str] = []
    for tok in positional:
        if "=" in tok and not tok.startswith("="):
            k, _, v = tok.partition("=")
            named[k.strip().upper()] = v.strip()
        else:
            pos_only.append(tok)
    prompt = expand_prompt_template(tmpl, named, positional=pos_only)
    return {"name": tmpl.name, "prompt": prompt, "original": raw, "description": tmpl.description}


def list_prompt_templates_public(cwd: Optional[str] = None) -> List[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "path": t.path,
            "variables": list(t.variables),
            "slash": f"/{t.name}",
        }
        for t in discover_prompt_templates(cwd)
    ]
