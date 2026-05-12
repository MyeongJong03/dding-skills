#!/usr/bin/env python3
"""Dry-run scaffold for manual platform adapter smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--adapter", default="generic")
    parser.add_argument("--profile")
    parser.add_argument("--live", action="store_true", help="reserved for future manual live smoke tests")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = {
        "ok": True,
        "dry_run": not args.live,
        "live_network_performed": False,
        "platform": args.platform,
        "event": args.event,
        "adapter": args.adapter,
        "profile_configured": bool(args.profile),
        "planned_checks": [
            "profile metadata exists",
            "adapter capabilities are importable",
            "discovery can run against a local fixture",
            "server policy requires a lease before create",
            "submission policy is disabled or explicit",
        ],
    }
    if args.live:
        result["ok"] = False
        result["reason"] = "live_smoke_tests_are_manual_future_work"
    if args.json:
        print(json_dumps(result), end="")
    else:
        print("dry-run platform smoke test scaffold")
        for item in result["planned_checks"]:
            print(f"- {item}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
