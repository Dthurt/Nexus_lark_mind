"""Session / agent presets — saved model + tools + thinking bundles (Pi-inspired).

Layout:
  <cwd>/.nlm/presets/<name>.json
  ~/.nlm/presets/<name>.json
  plugins_volume/presets/<name>.json

JSON shape:
  {
    "name": "code-review",
    "description": "Read-only review",
    "model": "glm-4.7-flash",
    "provider": "glm",
    "permission_preset": "read-only",
    "reasoning_effort": "high",
    "active_tools": ["read_file", "grep", "glob", "list_dir", "kb_search"],
    "system_prompt_append": "Focus on defects…"
  }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    path: str
    data: Dict[str, Any]

    @property
    def active_tools(self) -> Optional[List[str]]:
        tools = self.data.get("active_tools")
        if isinstance(tools, list):
            return [str(t) for t in tools if str(t).strip()]
        return None

    @property
    def permission_preset(self) -> Optional[str]:
        v = self.data.get("permission_preset")
        return str(v) if v else None

    @property
    def reasoning_effort(self) -> Optional[str]:
        v = self.data.get("reasoning_effort")
        return str(v) if v else None

    @property
    def system_prompt_append(self) -> str:
        return str(self.data.get("system_prompt_append") or "")

    @property
    def model(self) -> Optional[str]:
        v = self.data.get("model")
        return str(v) if v else None

    @property
    def provider(self) -> Optional[str]:
        v = self.data.get("provider")
        return str(v) if v else None


def _preset_dirs(cwd: Optional[str] = None) -> List[Path]:
    paths: List[Path] = []
    if cwd:
        paths.append(Path(cwd) / ".nlm" / "presets")
    home = Path.home() / ".nlm" / "presets"
    paths.append(home)
    paths.append(Path("plugins_volume") / "presets")
    root = Path(__file__).resolve().parents[2]
    paths.append(root / "plugins_volume" / "presets")
    return paths


def discover_presets(cwd: Optional[str] = None, *, max_presets: int = 40) -> List[Preset]:
    found: Dict[str, Preset] = {}
    for base in _preset_dirs(cwd):
        if not base.is_dir():
            continue
        try:
            files = sorted(base.glob("*.json"))
        except OSError:
            continue
        for path in files:
            if len(found) >= max_presets:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            name = str(data.get("name") or path.stem).strip()
            if not name or name in found:
                continue
            desc = str(data.get("description") or name).strip()
            found[name] = Preset(
                name=name,
                description=desc[:240],
                path=str(path).replace("\\", "/"),
                data=data,
            )
    return list(found.values())


def resolve_preset(cwd: Optional[str], name: str) -> Optional[Preset]:
    key = (name or "").strip()
    if not key:
        return None
    for p in discover_presets(cwd):
        if p.name == key or p.name.lower() == key.lower():
            return p
    return None


def apply_preset_to_session_patch(preset: Preset) -> Dict[str, Any]:
    """Fields suitable for Redis session update / interaction patch."""
    patch: Dict[str, Any] = {"preset_name": preset.name}
    if preset.permission_preset:
        patch["permission_preset"] = preset.permission_preset
    if preset.reasoning_effort:
        patch["reasoning_effort"] = preset.reasoning_effort
    if preset.model:
        patch["model_name"] = preset.model
    if preset.provider:
        patch["model_provider"] = preset.provider
    if preset.active_tools is not None:
        patch["active_tools"] = list(preset.active_tools)
    if preset.system_prompt_append:
        patch["system_prompt_append"] = preset.system_prompt_append
    return patch


def list_presets_public(cwd: Optional[str] = None) -> List[dict]:
    out = []
    for p in discover_presets(cwd):
        out.append(
            {
                "name": p.name,
                "description": p.description,
                "path": p.path,
                "permission_preset": p.permission_preset,
                "reasoning_effort": p.reasoning_effort,
                "active_tools": p.active_tools,
                "model": p.model,
                "provider": p.provider,
            }
        )
    return out
