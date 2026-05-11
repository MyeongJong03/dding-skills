#!/usr/bin/env python3
"""Show public-safe queue and scheduler event history."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.queue import list_queue_events
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--challenge-id")
    parser.add_argument("--run-id")
    parser.add_argument("--tail", type=int)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    records = list_queue_events(
        platform=args.platform,
        event=args.event,
        challenge_id=args.challenge_id,
        run_id=args.run_id,
        tail=args.tail,
    )
    if args.json:
        print(json_dumps({"ok": True, "events": records, "count": len(records)}), end="")
        return 0

    for record in records:
        timestamp = record.get("timestamp") or ""
        event_type = record.get("event_type") or ""
        platform = record.get("platform") or ""
        event = record.get("event") or ""
        challenge_id = record.get("challenge_id") or ""
        run_id = record.get("run_id") or ""
        old_state = record.get("old_state") or ""
        new_state = record.get("new_state") or ""
        reason = record.get("reason") or ""
        state = f" {old_state}->{new_state}" if old_state or new_state else ""
        print(f"{timestamp} {event_type} {platform}/{event} {challenge_id} {run_id}{state} {reason}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
