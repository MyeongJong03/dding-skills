#!/usr/bin/env python3
"""Run one bounded command in a GDB debug session."""

from __future__ import annotations

import argparse

from _gdb_cli import add_common_io_args, emit
from ctf_solver_core.gdb_session import run_gdb_cmd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdb-session-id", required=True)
    parser.add_argument("--cmd", required=True)
    add_common_io_args(parser)
    args = parser.parse_args()
    result = run_gdb_cmd(args.gdb_session_id, args.cmd, timeout_ms=args.timeout_ms, max_bytes=args.max_bytes)
    emit(result, json_output=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
