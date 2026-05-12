#!/usr/bin/env python3
"""Collect a bounded public-safe backtrace summary from GDB."""

from __future__ import annotations

import argparse

from _gdb_cli import add_common_io_args, emit
from ctf_solver_core.gdb_session import backtrace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdb-session-id", required=True)
    add_common_io_args(parser)
    args = parser.parse_args()
    result = backtrace(args.gdb_session_id, timeout_ms=args.timeout_ms, max_bytes=args.max_bytes)
    emit(result, json_output=args.json, text_key="backtrace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
