#!/usr/bin/env python3
"""Acquire a platform remote-resource lease."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platforms import get_platform_policy
from ctf_solver_core.resources import REMOTE_SERVER, acquire_remote_server, default_worker_id
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--resource", default=REMOTE_SERVER, choices=[REMOTE_SERVER])
    parser.add_argument("--mode", default="primary", choices=["primary", "helper"])
    parser.add_argument("--policy", help="platform policy YAML path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    worker_id = args.worker_id or default_worker_id()
    policy = get_platform_policy(args.platform, args.event, args.policy)
    result = acquire_remote_server(
        policy,
        challenge_id=args.challenge_id,
        run_id=args.run_id,
        worker_id=worker_id,
        mode=args.mode,
    )
    result["worker_id"] = worker_id
    print(json_dumps(result), end="")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
