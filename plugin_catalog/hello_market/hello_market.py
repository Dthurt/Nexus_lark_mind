#!/usr/bin/env python3
"""Sample marketplace CLI plugin — echoes input."""

from __future__ import annotations

import json
import sys


def main() -> None:
    raw = sys.stdin.read() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}
    print(
        json.dumps(
            {"ok": True, "plugin": "cli.hello_market", "echo": data},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
