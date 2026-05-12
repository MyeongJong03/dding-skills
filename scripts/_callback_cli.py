"""Shared CLI implementation for callback listener scripts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.callback_client import (
    callback_close,
    callback_hits,
    callback_list,
    callback_start,
    callback_url,
    callback_wait,
    web_payload_helper,
)
from ctf_solver_core.schemas import json_dumps


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def build_parser(action: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Callback listener: {action}")
    _add_common(parser)
    if action == "start":
        parser.add_argument("--run-id")
        parser.add_argument("--challenge-id")
        parser.add_argument("--worker-id")
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port")
        parser.add_argument("--external-base-url")
        parser.add_argument("--token-path")
        parser.add_argument("--allow-public-bind", action="store_true")
    elif action == "url":
        parser.add_argument("--listener-id", required=True)
        parser.add_argument("--external", action="store_true")
        parser.add_argument("--path")
    elif action == "hits":
        parser.add_argument("--listener-id", required=True)
        parser.add_argument("--since-hit-id")
        parser.add_argument("--limit", type=int, default=20)
    elif action == "wait":
        parser.add_argument("--listener-id", required=True)
        parser.add_argument("--timeout-sec", type=float, required=True)
        parser.add_argument("--pattern")
        parser.add_argument("--min-hits", type=int, default=1)
    elif action == "close":
        parser.add_argument("--listener-id", required=True)
        parser.add_argument("--reason", default="closed")
    elif action == "list":
        parser.add_argument("--run-id")
        parser.add_argument("--challenge-id")
        parser.add_argument("--include-closed", action="store_true")
    elif action == "payload":
        parser.add_argument("--callback-url", required=True)
    else:
        raise ValueError(f"unsupported callback action: {action}")
    return parser


def run_action(action: str, args: argparse.Namespace) -> dict[str, object]:
    if action == "start":
        return callback_start(
            run_id=args.run_id,
            challenge_id=args.challenge_id,
            worker_id=args.worker_id,
            host=args.host,
            port=args.port,
            external_base_url=args.external_base_url,
            token_path=args.token_path,
            allow_public_bind=args.allow_public_bind,
        )
    if action == "url":
        return callback_url(args.listener_id, external=args.external, path=args.path)
    if action == "hits":
        return callback_hits(args.listener_id, since_hit_id=args.since_hit_id, limit=args.limit)
    if action == "wait":
        return callback_wait(
            args.listener_id,
            timeout_sec=args.timeout_sec,
            pattern=args.pattern,
            min_hits=args.min_hits,
        )
    if action == "close":
        return callback_close(args.listener_id, reason=args.reason)
    if action == "list":
        return callback_list(run_id=args.run_id, challenge_id=args.challenge_id, include_closed=args.include_closed)
    if action == "payload":
        return web_payload_helper(args.callback_url)
    raise ValueError(f"unsupported callback action: {action}")


def _print_human(action: str, result: dict[str, object]) -> None:
    if action == "start":
        print(f"{result.get('listener_id')} {result.get('local_url')}")
        external = str(result.get("external_url") or "")
        if external:
            print(external)
        return
    if action == "url":
        print(result.get("url") or "")
        return
    if action == "list":
        for item in result.get("listeners") or []:
            if isinstance(item, dict):
                print(
                    f"{item.get('listener_id')} {item.get('status')} "
                    f"run={item.get('run_id') or '-'} hits={item.get('hit_count') or 0}"
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
    return 0 if result.get("ok", True) or action in {"start", "url", "hits", "list", "payload"} else 1
