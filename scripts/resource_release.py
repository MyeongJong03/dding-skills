#!/usr/bin/env python3
"""Release platform resource leases."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.queue import append_queue_event
from ctf_solver_core.resources import release_lease
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lease-id")
    group.add_argument("--run-id")
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--all-for-run", action="store_true", help="accepted for explicit finalize-hook calls")
    parser.add_argument("--release-reason", default="manual_release")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = release_lease(
        lease_id=args.lease_id,
        run_id=args.run_id,
        platform=args.platform,
        event=args.event,
        include_helpers=True,
        release_reason=args.release_reason,
    )
    try:
        for released in result.get("released_records") or []:
            if isinstance(released, dict):
                append_queue_event(
                    event_type="lease_released",
                    challenge_id=str(released.get("challenge_id") or ""),
                    run_id=str(released.get("run_id") or ""),
                    platform=str(released.get("platform") or args.platform or ""),
                    event=str(released.get("event") or args.event or ""),
                    reason=args.release_reason,
                    public_safe_metadata={
                        "lease_id": released.get("lease_id"),
                        "resource_type": released.get("resource_type"),
                        "role": released.get("role"),
                        "held_sec": released.get("held_sec"),
                    },
                )
    except Exception as exc:
        result["event_log_warning"] = str(exc)
    print(json_dumps(result), end="")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
