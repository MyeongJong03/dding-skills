#!/usr/bin/env python3
"""Create a private benchmark pack skeleton outside the repo."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.benchmark_packs import create_pack_skeleton
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", help="pack directory; defaults to CTF_BENCHMARK_ROOT/<pack-id>")
    parser.add_argument("--allow-repo-output", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = create_pack_skeleton(
            pack_id=args.pack_id,
            name=args.name,
            output=args.output,
            allow_repo_output=args.allow_repo_output,
        )
    except Exception as exc:
        print(f"benchmark pack init failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(result["manifest_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
