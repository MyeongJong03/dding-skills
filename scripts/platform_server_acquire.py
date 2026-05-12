#!/usr/bin/env python3
"""Acquire a remote-server lease and create a platform server record."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platform_automation import acquire_platform_server
from ctf_solver_core.resources import default_worker_id
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--adapter", default="generic", choices=["generic", "mock", "local"])
    parser.add_argument("--policy")
    parser.add_argument("--role", default="primary", choices=["primary", "helper"])
    parser.add_argument("--confirm", action="store_true", help="confirm allow_server_create=ask policy")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    worker_id = args.worker_id or default_worker_id()
    result = acquire_platform_server(
        platform=args.platform,
        event=args.event,
        challenge_id=args.challenge_id,
        run_id=args.run_id,
        adapter_name=args.adapter,
        policy_path=args.policy,
        worker_id=worker_id,
        confirmed=args.confirm,
        role=args.role,
    )
    result["worker_id"] = worker_id
    if args.json:
        print(json_dumps(result), end="")
    else:
        if result.get("server_acquired"):
            print(f"server acquired for {args.challenge_id}/{args.run_id}")
            print(f"lease: {result.get('lease_id')}")
        elif result.get("requires_confirmation"):
            print(result.get("reason"))
            print(result.get("suggested_command"))
        else:
            print(f"server acquire failed: {result.get('reason')}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
