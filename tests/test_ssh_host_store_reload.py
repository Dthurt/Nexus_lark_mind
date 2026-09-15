"""SSH host store reloads when the on-disk JSON changes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import src.adapters.workspaces.ssh_store as ssh_store


def test_get_ssh_host_store_reloads_on_mtime(tmp_path: Path, monkeypatch):
    path = tmp_path / "ssh_hosts.json"
    path.write_text(json.dumps({"hosts": []}), encoding="utf-8")
    monkeypatch.setattr(ssh_store, "STORE_PATH", path)
    ssh_store._store = None
    ssh_store._store_mtime = 0.0

    first = ssh_store.get_ssh_host_store()
    assert first.hosts == {}

    host = {
        "id": "ssh_test",
        "label": "t",
        "host": "127.0.0.1",
        "port": 22,
        "username": "u",
        "auth_type": "password",
        "source": "direct",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps({"hosts": [host]}), encoding="utf-8")
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 2))

    second = ssh_store.get_ssh_host_store()
    assert second is not first
    assert "ssh_test" in second.hosts

    third = ssh_store.get_ssh_host_store()
    assert third is second
