#!/usr/bin/env python3
"""Release platform resource leases."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = release_lease(
        lease_id=args.lease_id,
        run_id=args.run_id,
        platform=args.platform,
        event=args.event,
        include_helpers=True,
    )
    print(json_dumps(result), end="")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
