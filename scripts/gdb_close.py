#!/usr/bin/env python3
"""Close a GDB debug session and its backing process/container."""

from __future__ import annotations

import argparse

from _gdb_cli import emit
from ctf_solver_core.gdb_session import close_gdb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdb-session-id", required=True)
    parser.add_argument("--reason", default="closed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = close_gdb(args.gdb_session_id, reason=args.reason)
    emit(result, json_output=args.json, text_key="status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
