#!/usr/bin/env python3
"""Generate the public-safe AI usage dashboard."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.ai_usage import generate_ai_usage_report
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = generate_ai_usage_report(dry_run=args.dry_run)
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(result["dashboard_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
