#!/usr/bin/env python3
"""Show public-safe platform server and lease status."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platform_automation import server_status
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--challenge-id")
    parser.add_argument("--run-id")
    parser.add_argument("--lease-id")
    parser.add_argument("--adapter", default="generic", choices=["generic", "mock", "local"])
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = server_status(
        platform=args.platform,
        event=args.event,
        adapter_name=args.adapter,
        challenge_id=args.challenge_id,
        run_id=args.run_id,
        lease_id=args.lease_id,
    )
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(f"servers: {result.get('server_count', 0)}")
        print(f"active leases: {result.get('active_lease_count', 0)}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
