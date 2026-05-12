#!/usr/bin/env python3
"""Read from a persistent CTF session until one pattern appears or timeout expires."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.session_client import expect_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("patterns", nargs="+")
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--max-bytes", type=int, default=8000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = expect_session(
        args.session_id,
        args.patterns,
        timeout_ms=args.timeout_ms,
        max_bytes=args.max_bytes,
    )
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(str(result.get("output") or ""), end="")
    return 0 if result.get("matched") else 1


if __name__ == "__main__":
    raise SystemExit(main())
