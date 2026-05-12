#!/usr/bin/env python3
"""Run pwndbg telescope or a bounded x/gx fallback."""

from __future__ import annotations

import argparse

from _gdb_cli import add_common_io_args, emit
from ctf_solver_core.gdb_session import telescope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdb-session-id", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--count", type=int, default=8)
    add_common_io_args(parser)
    args = parser.parse_args()
    result = telescope(
        args.gdb_session_id,
        address=args.address,
        count=args.count,
        timeout_ms=args.timeout_ms,
        max_bytes=args.max_bytes,
    )
    emit(result, json_output=args.json, text_key="telescope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
