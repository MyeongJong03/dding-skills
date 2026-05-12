#!/usr/bin/env python3
"""Close a persistent CTF session."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.session_client import close_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("--reason", default="closed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = close_session(args.session_id, reason=args.reason)
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(f"closed {args.session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
