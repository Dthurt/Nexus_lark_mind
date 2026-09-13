"""Local marketplace catalog tests."""

from src.common.plugin_marketplace import build_marketplace


def test_marketplace_lists_catalog_hello_pack():
    data = build_marketplace(installed_ids=set())
    assert "items" in data
    ids = {row["id"] for row in data["items"]}
    assert "cli.hello_market" in ids
    hello = next(r for r in data["items"] if r["id"] == "cli.hello_market")
    assert hello["source"] == "catalog"
    assert hello["installable"] is True
    assert hello["installed"] is False


def test_marketplace_marks_installed():
    data = build_marketplace(installed_ids={"cli.hello_market", "cli.web_search"})
    hello = next(r for r in data["items"] if r["id"] == "cli.hello_market")
    assert hello["installed"] is True
