"""Lightweight team DAG scheduler (dependency-ready nodes).

Not a full workflow engine — tracks node readiness for Agent Teams UI / tools.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class DagNode:
    id: str
    label: str = ""
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"  # pending | ready | running | done | failed
    meta: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DagNode":
        return cls(
            id=str(data.get("id") or ""),
            label=str(data.get("label") or ""),
            depends_on=list(data.get("depends_on") or []),
            status=str(data.get("status") or "pending"),
            meta=dict(data.get("meta") or {}),
            updated_at=float(data.get("updated_at") or time.time()),
        )


def _dag_path(team_id: str) -> Path:
    root = Path("data") / "teams"
    root.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in team_id)[:80]
    return root / f"{safe}.dag.json"


class TeamDag:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._graphs: Dict[str, Dict[str, DagNode]] = {}

    def _load(self, team_id: str) -> None:
        if team_id in self._graphs:
            return
        path = _dag_path(team_id)
        nodes: Dict[str, DagNode] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for row in raw.get("nodes") or []:
                    if isinstance(row, dict) and row.get("id"):
                        n = DagNode.from_dict(row)
                        nodes[n.id] = n
            except Exception:
                nodes = {}
        self._graphs[team_id] = nodes
        self._recompute(team_id)

    def _save(self, team_id: str) -> None:
        with self._lock:
            nodes = list(self._graphs.get(team_id, {}).values())
        payload = {"nodes": [n.to_dict() for n in nodes], "updated_at": time.time()}
        try:
            _dag_path(team_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _recompute(self, team_id: str) -> None:
        nodes = self._graphs.setdefault(team_id, {})
        done: Set[str] = {nid for nid, n in nodes.items() if n.status == "done"}
        for n in nodes.values():
            if n.status in {"done", "failed", "running"}:
                continue
            deps = set(n.depends_on or [])
            n.status = "ready" if deps.issubset(done) else "pending"
            n.updated_at = time.time()

    def add_node(
        self,
        team_id: str,
        *,
        label: str = "",
        depends_on: Optional[List[str]] = None,
        node_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> DagNode:
        self._load(team_id)
        nid = node_id or f"dn_{uuid.uuid4().hex[:10]}"
        node = DagNode(
            id=nid,
            label=label or nid,
            depends_on=list(depends_on or []),
            meta=dict(meta or {}),
        )
        with self._lock:
            self._graphs.setdefault(team_id, {})[nid] = node
            self._recompute(team_id)
        self._save(team_id)
        return node

    def mark(self, team_id: str, node_id: str, status: str) -> Optional[DagNode]:
        self._load(team_id)
        with self._lock:
            node = self._graphs.get(team_id, {}).get(node_id)
            if not node:
                return None
            node.status = status
            node.updated_at = time.time()
            self._recompute(team_id)
        self._save(team_id)
        return node

    def ready(self, team_id: str) -> List[DagNode]:
        self._load(team_id)
        with self._lock:
            return [n for n in self._graphs.get(team_id, {}).values() if n.status == "ready"]

    def snapshot(self, team_id: str) -> Dict[str, Any]:
        self._load(team_id)
        with self._lock:
            nodes = [n.to_dict() for n in self._graphs.get(team_id, {}).values()]
        return {
            "team_id": team_id,
            "nodes": nodes,
            "ready": [n["id"] for n in nodes if n.get("status") == "ready"],
        }


_DAG: Optional[TeamDag] = None
_LOCK = threading.Lock()


def get_team_dag() -> TeamDag:
    global _DAG
    with _LOCK:
        if _DAG is None:
            _DAG = TeamDag()
        return _DAG
