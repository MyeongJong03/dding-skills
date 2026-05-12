#!/usr/bin/env python3
"""Select and claim the next queue worker action."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platforms import get_platform_policy
from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.worker import choose_worker_action, make_worker_id


def _bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y", "on"}:
        return True
    if lowered in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--policy", help="platform policy YAML path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-helper", type=_bool, default=True)
    parser.add_argument("--require-verifier", type=_bool, default=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    worker_id = args.worker_id or make_worker_id()
    policy = get_platform_policy(args.platform, args.event, args.policy)
    result = choose_worker_action(
        policy,
        worker_id=worker_id,
        allow_helper=args.allow_helper,
        require_verifier=args.require_verifier,
        claim=True,
    )
    print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
