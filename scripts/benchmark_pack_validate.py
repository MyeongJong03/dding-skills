#!/usr/bin/env python3
"""Validate a private benchmark pack manifest for schema and public-safety mistakes."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.benchmark_packs import validate_pack_manifest
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_or_pack", help="benchmark_pack.yaml or a pack directory")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = validate_pack_manifest(args.manifest_or_pack)
    if args.json:
        print(json_dumps(result), end="")
    elif result["ok"]:
        print("OK: private benchmark pack manifest is safe")
    else:
        for error in result["errors"]:
            print(error, file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
