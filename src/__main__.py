"""CLI entry: `python -m src` / `nlm` — web launcher + headless chat (Wave F)."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _open_when_ready(url: str, *, delay: float = 1.8) -> None:
    def _run() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def _ensure_sdk_path() -> None:
    root = Path(__file__).resolve().parents[1]
    sdk = root / "sdk" / "python"
    if sdk.is_dir() and str(sdk) not in sys.path:
        sys.path.insert(0, str(sdk))


def _cmd_web(args: argparse.Namespace) -> int:
    from src.common.config import get_settings
    from src.entry_local import run

    settings = get_settings()
    port = int(getattr(args, "port", None) or settings.adapters_port)
    url = f"http://127.0.0.1:{port}/"
    if getattr(args, "open", False):
        _open_when_ready(url)
        print(f"[nlm] opening {url} when ready…", flush=True)
    else:
        print(f"[nlm] workbench at {url}", flush=True)
        print("[nlm] tip: python -m src web --open", flush=True)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[nlm] stopped", flush=True)
        return 0
    return 0


def _cmd_chat(args: argparse.Namespace) -> int:
    _ensure_sdk_path()
    from nlm_client import NlmClient, NlmClientError

    base = (args.base_url or "http://127.0.0.1:8000").rstrip("/")
    prompt = " ".join(args.prompt or []).strip()
    if not prompt:
        print("usage: nlm chat [--cwd PATH] [--session ID] PROMPT…", file=sys.stderr)
        return 2
    try:
        with NlmClient(base) as client:
            result = client.chat(
                prompt,
                session_id=args.session,
                cwd=args.cwd,
                print_deltas=True,
                auto_accept=bool(args.auto_accept),
                tools_enabled=not bool(args.no_tools),
            )
    except NlmClientError as exc:
        print(f"[nlm] error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[nlm] failed: {exc}", file=sys.stderr)
        print("[nlm] is the stack running? try: python -m src web", file=sys.stderr)
        return 1
    if result.get("error"):
        print(f"\n[nlm] failed: {result['error']}", file=sys.stderr)
        return 1
    print(f"\n[nlm] session={result.get('session_id')}", flush=True)
    return 0


def _cmd_session_new(args: argparse.Namespace) -> int:
    _ensure_sdk_path()
    from nlm_client import NlmClient, NlmClientError

    base = (args.base_url or "http://127.0.0.1:8000").rstrip("/")
    try:
        with NlmClient(base) as client:
            sess = client.create_session(cwd=args.cwd)
    except Exception as exc:
        print(f"[nlm] failed: {exc}", file=sys.stderr)
        return 1
    sid = ""
    if isinstance(sess, dict):
        sid = str(sess.get("session_id") or sess.get("id") or "")
    print(sid or sess)
    return 0 if sid else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nlm",
        description="Nexus Lark Mind — local web stack + headless chat SDK",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_web = sub.add_parser("web", help="Start all-in-one local services (default)")
    p_web.add_argument("--open", action="store_true", help="Open workbench in browser")
    p_web.add_argument("--port", type=int, default=None)

    p_chat = sub.add_parser("chat", help="Headless one-shot chat (requires running adapters)")
    p_chat.add_argument("prompt", nargs="*", help="User message")
    p_chat.add_argument("--base-url", default="http://127.0.0.1:8000")
    p_chat.add_argument("--session", default=None, help="Reuse session id")
    p_chat.add_argument("--cwd", default=None, help="Bind workspace cwd")
    p_chat.add_argument("--auto-accept", action="store_true")
    p_chat.add_argument("--no-tools", action="store_true")

    p_sess = sub.add_parser("session", help="Session helpers")
    p_sess_sub = p_sess.add_subparsers(dest="session_cmd")
    p_new = p_sess_sub.add_parser("new", help="Create a session and print id")
    p_new.add_argument("--base-url", default="http://127.0.0.1:8000")
    p_new.add_argument("--cwd", default=None)

    # Bare `python -m src --open` also works
    parser.add_argument("--open", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    cmd = args.cmd or "web"

    if cmd == "web":
        return _cmd_web(args)
    if cmd == "chat":
        return _cmd_chat(args)
    if cmd == "session":
        if getattr(args, "session_cmd", None) == "new":
            return _cmd_session_new(args)
        parser.parse_args(["session", "-h"])
        return 2

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
