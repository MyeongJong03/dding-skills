#!/usr/bin/env python3
"""Compare public-safe before/after benchmark result files or report snapshots."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.benchmark_packs import compare_benchmark_snapshots
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--output", help="public-safe comparison JSON; defaults to metrics/comparisons")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = compare_benchmark_snapshots(before_path=args.before, after_path=args.after, output_path=args.output)
    except Exception as exc:
        print(f"benchmark compare failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(result["output_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
