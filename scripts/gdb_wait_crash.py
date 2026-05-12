#!/usr/bin/env python3
"""Continue a GDB session and wait for a crash or timeout."""

from __future__ import annotations

import argparse

from _gdb_cli import emit
from ctf_solver_core.gdb_session import wait_crash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdb-session-id", required=True)
    parser.add_argument("--timeout-ms", type=int, default=5000)
    parser.add_argument("--max-bytes", type=int, default=8000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = wait_crash(args.gdb_session_id, timeout_ms=args.timeout_ms, max_bytes=args.max_bytes)
    emit(result, json_output=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
