# Headless CLI & Python SDK (Wave F)

Talk to a **running** Nexus Lark Mind adapters process (`:8000`) without the Web UI.

## Prerequisites

```bat
python -m src web
```

## CLI

```bat
scripts\nlm.cmd chat --cwd E:\proj "Summarize README.md"
python -m src chat --session sess_xxx "follow-up"
python -m src session new --cwd E:\proj
```

Flags: `--base-url`, `--auto-accept`, `--no-tools`.

## Python SDK

Package path: `sdk/python/nlm_client` (add to `PYTHONPATH` or install editable later).

```python
from nlm_client import NlmClient

with NlmClient("http://127.0.0.1:8000") as client:
    result = client.chat("list top-level files", cwd=r"E:\proj", print_deltas=True)
    print(result["session_id"], result["content"][:200])
```

Core methods: `create_session`, `send`, `stream_events`, `cancel_task` / `cancel_session`, `push_inbox`, `chat`.

Local-only for v0 (no auth). Approvals still require Web/Feishu HITL unless `--auto-accept` / danger preset.

See also: [local-start.md](./local-start.md), [agent-teams.md](./agent-teams.md).
