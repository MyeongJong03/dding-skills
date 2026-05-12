"""Shared CLI implementation for browser action scripts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.browser_client import (
    browser_click,
    browser_close,
    browser_console,
    browser_cookies,
    browser_eval,
    browser_fill,
    browser_goto,
    browser_list,
    browser_network,
    browser_screenshot,
    browser_start,
    browser_upload,
)
from ctf_solver_core.schemas import json_dumps


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def _session_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--browser-session-id", required=True)


def build_parser(action: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Browser action: {action}")
    _add_common(parser)
    if action == "start":
        parser.add_argument("--run-id")
        parser.add_argument("--challenge-id")
        parser.add_argument("--worker-id")
        parser.add_argument("--platform", help="platform for resolving browser_state profile metadata")
        parser.add_argument("--event", help="event for resolving browser_state profile metadata")
        parser.add_argument("--profile")
        parser.add_argument("--storage-state")
        parser.add_argument("--browser-type", default="chromium")
        parser.add_argument("--headed", action="store_true", help="run headed; default is headless")
    elif action == "goto":
        _session_arg(parser)
        parser.add_argument("--url", required=True)
        parser.add_argument("--timeout-ms", type=int, default=10_000)
        parser.add_argument("--wait-until", default="load")
    elif action in {"click", "fill", "upload"}:
        _session_arg(parser)
        parser.add_argument("--selector", required=True)
        parser.add_argument("--timeout-ms", type=int, default=10_000)
        if action == "fill":
            parser.add_argument("--value")
            parser.add_argument("--text")
        if action == "upload":
            parser.add_argument("--file", action="append", required=True)
    elif action == "eval":
        _session_arg(parser)
        parser.add_argument("--expression", required=True)
        parser.add_argument("--timeout-ms", type=int, default=10_000)
        parser.add_argument("--max-bytes", type=int, default=4000)
    elif action == "screenshot":
        _session_arg(parser)
        parser.add_argument("--name")
        parser.add_argument("--full-page", action="store_true")
    elif action in {"console", "network"}:
        _session_arg(parser)
        parser.add_argument("--limit", type=int, default=50)
    elif action == "cookies":
        _session_arg(parser)
    elif action == "close":
        _session_arg(parser)
        parser.add_argument("--reason", default="closed")
    elif action == "list":
        parser.add_argument("--run-id")
        parser.add_argument("--challenge-id")
        parser.add_argument("--include-closed", action="store_true")
    else:
        raise ValueError(f"unsupported browser action: {action}")
    return parser


def run_action(action: str, args: argparse.Namespace) -> dict[str, object]:
    if action == "start":
        return browser_start(
            run_id=args.run_id,
            challenge_id=args.challenge_id,
            worker_id=args.worker_id,
            platform=args.platform,
            event=args.event,
            profile=args.profile,
            storage_state=args.storage_state,
            browser_type=args.browser_type,
            headless=not args.headed,
        )
    if action == "goto":
        return browser_goto(
            args.browser_session_id,
            url=args.url,
            timeout_ms=args.timeout_ms,
            wait_until=args.wait_until,
        )
    if action == "click":
        return browser_click(args.browser_session_id, selector=args.selector, timeout_ms=args.timeout_ms)
    if action == "fill":
        return browser_fill(
            args.browser_session_id,
            selector=args.selector,
            value=args.value if args.value is not None else str(args.text or ""),
            timeout_ms=args.timeout_ms,
        )
    if action == "upload":
        return browser_upload(args.browser_session_id, selector=args.selector, files=args.file, timeout_ms=args.timeout_ms)
    if action == "eval":
        return browser_eval(
            args.browser_session_id,
            expression=args.expression,
            timeout_ms=args.timeout_ms,
            max_bytes=args.max_bytes,
        )
    if action == "screenshot":
        return browser_screenshot(args.browser_session_id, name=args.name, full_page=args.full_page)
    if action == "console":
        return browser_console(args.browser_session_id, limit=args.limit)
    if action == "network":
        return browser_network(args.browser_session_id, limit=args.limit)
    if action == "cookies":
        return browser_cookies(args.browser_session_id)
    if action == "close":
        return browser_close(args.browser_session_id, reason=args.reason)
    if action == "list":
        return browser_list(run_id=args.run_id, challenge_id=args.challenge_id, include_closed=args.include_closed)
    raise ValueError(f"unsupported browser action: {action}")


def _print_human(action: str, result: dict[str, object]) -> None:
    if action == "start" and result.get("ok") and isinstance(result.get("session"), dict):
        print(result["session"]["browser_session_id"])
        return
    if action == "list":
        for item in result.get("sessions") or []:
            if isinstance(item, dict):
                print(
                    f"{item.get('browser_session_id')} {item.get('status')} "
                    f"run={item.get('run_id') or '-'} pages={item.get('pages_count') or 0}"
                )
        return
    print(json_dumps(result), end="")


def main(action: str) -> int:
    args = build_parser(action).parse_args()
    result = run_action(action, args)
    if args.json:
        print(json_dumps(result), end="")
    else:
        _print_human(action, result)
    return 0 if result.get("ok", True) else 1
