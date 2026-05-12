#!/usr/bin/env python3
"""Create a public or private benchmark definition template."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.benchmarks import create_benchmark_definition, parse_bool
from ctf_solver_core.schemas import CATEGORIES, json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--challenge-id", default="")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--difficulty", default="")
    parser.add_argument("--local-capable", type=parse_bool, required=True)
    parser.add_argument("--remote-required", type=parse_bool, required=True)
    parser.add_argument("--expected-status", default="")
    parser.add_argument("--flag-regex", default="")
    parser.add_argument("--verifier-required", type=parse_bool, default=False)
    parser.add_argument("--timeout-sec", type=int, required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--tags", default="", help="comma-separated public-safe tags")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    tags = [item.strip() for item in args.tags.split(",") if item.strip()]
    result = create_benchmark_definition(
        benchmark_id=args.benchmark_id,
        challenge_id=args.challenge_id,
        platform=args.platform,
        event=args.event,
        category=args.category,
        difficulty=args.difficulty,
        local_capable=args.local_capable,
        remote_required=args.remote_required,
        expected_status=args.expected_status,
        flag_regex=args.flag_regex,
        verifier_required=args.verifier_required,
        timeout_sec=args.timeout_sec,
        notes=args.notes,
        tags=tags,
        private=args.private,
    )
    if not args.private and (" " in args.benchmark_id or args.challenge_id):
        print("warning: public benchmark identifiers can reveal challenge names", file=sys.stderr)
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(result["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
