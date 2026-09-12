"""Wave F: teams mailbox + SDK import smoke."""

import sys
from pathlib import Path

from src.core_kernel.teams import get_team_mailbox


def test_team_mailbox_post_claim():
    box = get_team_mailbox()
    box.clear("t1")
    msg = box.post("t1", from_id="parent", to_id="sa_1", payload={"hello": 1})
    assert msg.id.startswith("tm_")
    claimed = box.claim("t1", "sa_1")
    assert len(claimed) == 1
    assert claimed[0].payload["hello"] == 1
    assert box.claim("t1", "sa_1") == []


def test_nlm_client_importable():
    root = Path(__file__).resolve().parents[1]
    sdk = root / "sdk" / "python"
    sys.path.insert(0, str(sdk))
    from nlm_client import NlmClient  # noqa: WPS433

    c = NlmClient("http://127.0.0.1:9")
    assert c.base_url.endswith("/")
    c.close()
