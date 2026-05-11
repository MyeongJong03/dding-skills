#!/usr/bin/env python3
"""Add or update a challenge queue item."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.queue import QUEUE_STATES, update_queue_item
from ctf_solver_core.schemas import CATEGORIES, json_dumps


def _bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y", "on"}:
        return True
    if lowered in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--state", choices=QUEUE_STATES, required=True)
    parser.add_argument("--local-capable", type=_bool, required=True)
    parser.add_argument("--remote-required", type=_bool, required=True)
    parser.add_argument("--local-exploit-ready", type=_bool, required=True)
    parser.add_argument("--confidence", type=float, default=0.0)
    parser.add_argument("--destructive-risk", type=float, default=0.0)
    parser.add_argument("--deadline")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    item = update_queue_item(
        challenge_id=args.challenge_id,
        run_id=args.run_id,
        platform=args.platform,
        event=args.event,
        category=args.category,
        state=args.state,
        local_capable=args.local_capable,
        remote_required=args.remote_required,
        local_exploit_ready=args.local_exploit_ready,
        confidence=args.confidence,
        destructive_risk=args.destructive_risk,
        deadline=args.deadline,
    )
    print(json_dumps({"ok": True, "item": item}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
