#!/usr/bin/env python3
"""Return the next local-first queue scheduling decision."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platforms import get_platform_policy
from ctf_solver_core.queue import select_next
from ctf_solver_core.resources import default_worker_id
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--policy", help="platform policy YAML path")
    parser.add_argument("--worker-id")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    worker_id = args.worker_id or default_worker_id()
    policy = get_platform_policy(args.platform, args.event, args.policy)
    result = select_next(policy, worker_id=worker_id)
    result["worker_id"] = worker_id
    print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
