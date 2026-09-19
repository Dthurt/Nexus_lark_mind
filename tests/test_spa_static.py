from pathlib import Path

from starlette.testclient import TestClient

from src.adapters.app import SPAStaticFiles


def test_spa_fallback_serves_index_for_knowledge(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html>nlm</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("ok", encoding="utf-8")
    app = SPAStaticFiles(directory=str(tmp_path), html=True)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/").status_code == 200
    assert "nlm" in client.get("/knowledge").text
    assert "nlm" in client.get("/knowledge/local:default/wiki").text
    assert "nlm" in client.get("/knowledge/local:default/graph").text
    assert "nlm" in client.get("/settings").text
    js = client.get("/assets/app.js")
    assert js.status_code == 200
    assert js.text == "ok"
