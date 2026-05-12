#!/usr/bin/env python3
"""Export private benchmark run results into public-safe benchmark records."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.benchmark_packs import export_private_benchmark_results
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="private benchmark result JSON or JSONL")
    parser.add_argument("--output", help="public-safe JSONL output; defaults to metrics/benchmark_exports/<input>.jsonl")
    parser.add_argument("--summary-output", help="public-safe JSON summary output")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = export_private_benchmark_results(
            input_path=args.input,
            output_path=args.output,
            summary_output_path=args.summary_output,
        )
    except Exception as exc:
        print(f"benchmark export failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(result["output_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
