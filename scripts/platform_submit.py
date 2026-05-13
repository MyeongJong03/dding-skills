#!/usr/bin/env python3
"""Policy-gated platform flag submission scaffold."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platform_automation import submit_flag
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--flag", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--role", default="primary", choices=["primary", "helper"])
    parser.add_argument("--adapter", default="generic", choices=["generic", "mock", "local", "ctfd", "dreamhack"])
    parser.add_argument("--policy")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = submit_flag(
        platform=args.platform,
        event=args.event,
        challenge_id=args.challenge_id,
        flag=args.flag,
        adapter_name=args.adapter,
        policy_path=args.policy,
        run_id=args.run_id,
        role=args.role,
    )
    if args.json:
        print(json_dumps(result), end="")
    else:
        if result.get("submitted"):
            print(f"submitted {args.challenge_id}: accepted={result.get('accepted')}")
        elif result.get("requires_confirmation"):
            print(f"submission blocked by policy: {result.get('reason')}")
        else:
            print(f"submission not performed: {result.get('reason')}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
