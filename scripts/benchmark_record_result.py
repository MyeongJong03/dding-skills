#!/usr/bin/env python3
"""Record one public-safe benchmark result."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.benchmarks import BENCHMARK_STATUSES, build_benchmark_result, parse_bool, record_benchmark_result
from ctf_solver_core.paths import resolve_path
from ctf_solver_core.schemas import CATEGORIES, json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--run-dir")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", choices=BENCHMARK_STATUSES, required=True)
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--attempt-index", type=int, default=1)
    parser.add_argument("--duration-sec", type=float)
    parser.add_argument("--time-to-flag-sec", type=float)
    parser.add_argument("--verifier-success", type=parse_bool)
    parser.add_argument("--verifier-flag-found", type=parse_bool)
    parser.add_argument("--ai-usage-id", default="")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_dir = resolve_path(args.run_dir) if args.run_dir else None
    record = build_benchmark_result(
        benchmark_id=args.benchmark_id,
        run_id=args.run_id,
        attempt_index=args.attempt_index,
        status=args.status,
        run_dir=run_dir,
        category=args.category or "",
        platform=args.platform or "",
        event=args.event or "",
        duration_sec=args.duration_sec,
        time_to_flag_sec=args.time_to_flag_sec,
        verifier_success=args.verifier_success,
        verifier_flag_found=args.verifier_flag_found,
        ai_usage_id=args.ai_usage_id,
    )
    result = record_benchmark_result(record, replace=args.replace, dry_run=args.dry_run)
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(result["summary_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
