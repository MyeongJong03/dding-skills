#!/usr/bin/env python3
"""Discover challenges through a policy-gated platform adapter scaffold."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platform_automation import discover_challenges
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--adapter", default="generic", choices=["generic", "mock", "local", "ctfd"])
    parser.add_argument("--source")
    parser.add_argument("--base-url")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--policy")
    parser.add_argument("--queue", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = discover_challenges(
        platform=args.platform,
        event=args.event,
        adapter_name=args.adapter,
        source=args.source,
        base_url=args.base_url,
        live=args.live,
        profile=args.profile,
        policy_path=args.policy,
        queue=args.queue,
    )
    if args.profile:
        result["profile"] = args.profile
    if args.json:
        print(json_dumps(result), end="")
    else:
        if result.get("ok"):
            print(f"discovered {result.get('challenge_count', 0)} challenges via {result.get('adapter')}")
            if result.get("queued_count"):
                print(f"queued {result.get('queued_count')} challenges")
        else:
            print(f"platform discovery blocked: {result.get('reason')}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
