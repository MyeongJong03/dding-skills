#!/usr/bin/env python3
"""Show public-safe worker, claim, queue, and lease status."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.worker import worker_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show-claims", action="store_true")
    parser.add_argument("--show-leases", action="store_true")
    parser.add_argument("--show-queue", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    status = worker_status(platform=args.platform, event=args.event)
    if not args.show_claims:
        status.pop("claims", None)
    if args.json:
        print(json_dumps(status), end="")
        return 0

    print(f"worker_root: {status.get('worker_root')}")
    print(f"active_claims: {status.get('active_claims_count')}")
    print(f"stale_claims: {status.get('stale_claims_count')}")
    print(f"active_leases: {status.get('active_leases_count')}")
    print(f"stale_leases: {status.get('stale_leases_count')}")
    print(f"queue_items: {status.get('queue_items_count')}")
    if args.show_queue:
        print("queue_by_state:")
        for state, count in dict(status.get("queue_by_state") or {}).items():
            print(f"- {state}: {count}")
    if args.show_claims:
        print("claims:")
        for claim in status.get("claims") or []:
            if isinstance(claim, dict):
                marker = "stale" if claim.get("stale") else "active"
                print(
                    f"- {marker} {claim.get('challenge_id')} {claim.get('run_id')} "
                    f"{claim.get('action')} worker={claim.get('worker_id_hash')}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
