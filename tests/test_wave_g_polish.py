"""Teams durable mailbox + DAG + plugin package + backends."""

import json
from pathlib import Path

from src.common.plugin_package import install_from_directory, load_manifest, sign_manifest
from src.core_kernel.subagent.backend import get_subagent_backend, list_subagent_backends
from src.core_kernel.teams import get_team_dag, get_team_mailbox


def test_durable_mailbox_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    box = get_team_mailbox()
    box.clear("dur1")
    box.post("dur1", from_id="a", to_id="b", payload={"x": 1})
    path = Path("data/teams/dur1.json")
    assert path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["messages"][0]["payload"]["x"] == 1


def test_team_dag_ready_chain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dag = get_team_dag()
    n1 = dag.add_node("g1", label="A")
    n2 = dag.add_node("g1", label="B", depends_on=[n1.id])
    ready = {n.id for n in dag.ready("g1")}
    assert n1.id in ready
    assert n2.id not in ready
    dag.mark("g1", n1.id, "done")
    ready2 = {n.id for n in dag.ready("g1")}
    assert n2.id in ready2


def test_plugin_package_install(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "myplug"
    pkg.mkdir()
    (pkg / "entry.py").write_text("print('hi')\n", encoding="utf-8")
    manifest = {
        "id": "demo_pack",
        "version": "0.1.0",
        "kind": "cli",
        "entry": "entry.py",
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = install_from_directory(pkg)
    assert out["id"] == "demo_pack"
    assert Path(out["path"]).is_dir()
    assert load_manifest(Path(out["path"]) / "manifest.json")["version"] == "0.1.0"


def test_sign_manifest_roundtrip():
    m = {"id": "x", "version": "1", "kind": "cli"}
    sig = sign_manifest(m, "secret")
    m2 = {**m, "signature": sig}
    assert sign_manifest(m2, "secret") == sig


def test_inprocess_backend_listed():
    assert "inprocess" in list_subagent_backends()
    be = get_subagent_backend("inprocess")
    assert be.name == "inprocess"
