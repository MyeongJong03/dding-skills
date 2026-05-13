#!/usr/bin/env python3
"""Release a platform server record and matching remote-server lease."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platform_automation import release_platform_server
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--challenge-id")
    parser.add_argument("--run-id")
    parser.add_argument("--lease-id")
    parser.add_argument("--server-id")
    parser.add_argument("--reason", default="manual_release")
    parser.add_argument("--role", default="primary", choices=["primary", "helper"])
    parser.add_argument("--adapter", default="generic", choices=["generic", "mock", "local", "ctfd", "dreamhack"])
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = release_platform_server(
        platform=args.platform,
        event=args.event,
        adapter_name=args.adapter,
        challenge_id=args.challenge_id,
        run_id=args.run_id,
        lease_id=args.lease_id,
        server_id=args.server_id,
        reason=args.reason,
        role=args.role,
    )
    if args.json:
        print(json_dumps(result), end="")
    else:
        if result.get("ok"):
            print(
                f"released servers={result.get('server_release_count', 0)} "
                f"leases={result.get('lease_release_count', 0)}"
            )
        else:
            print(f"server release failed: {result.get('reason')}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
