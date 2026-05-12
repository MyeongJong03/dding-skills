#!/usr/bin/env python3
"""Write data to a persistent CTF session."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.session_client import write_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument("data")
    parser.add_argument("--no-newline", action="store_true")
    parser.add_argument("--encoding", choices=("text", "base64"), default="text")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = write_session(
        args.session_id,
        args.data,
        newline=not args.no_newline,
        encoding=args.encoding,
    )
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(f"wrote {result.get('bytes_written')} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
