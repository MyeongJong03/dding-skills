#!/usr/bin/env python3
"""Heartbeat a remote-resource lease once or periodically."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.resources import heartbeat_lease
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lease-id")
    group.add_argument("--run-id")
    parser.add_argument("--worker-id")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int)
    parser.add_argument("--duration", type=int)
    parser.add_argument("--json", action="store_true")
    return parser


def _print_result(result: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json_dumps(result), end="")
        return
    status = "ok" if result.get("ok") else "failed"
    print(f"{status}: {result.get('reason')} updated={result.get('updated_count', 0)}")


def main() -> int:
    args = build_parser().parse_args()
    interval = args.interval if args.interval is not None else 0
    once = args.once or interval <= 0
    started = time.monotonic()
    results: list[dict[str, object]] = []

    while True:
        result = heartbeat_lease(lease_id=args.lease_id, run_id=args.run_id, worker_id=args.worker_id)
        results.append(result)
        _print_result(result, args.json)
        if once:
            return 0 if result.get("ok") else 1
        if args.duration is not None and time.monotonic() - started >= args.duration:
            return 0 if any(item.get("ok") for item in results) else 1
        time.sleep(max(1, interval))


if __name__ == "__main__":
    raise SystemExit(main())
