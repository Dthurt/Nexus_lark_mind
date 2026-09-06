#!/usr/bin/env python3
"""Sample CLI plugin — echo JSON stdin as structured result."""
import json
import sys

def main() -> None:
    raw = sys.stdin.read().strip() or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}
    print(json.dumps({"ok": True, "echo": data}, ensure_ascii=False))

if __name__ == "__main__":
    main()
