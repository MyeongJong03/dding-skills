#!/usr/bin/env python3
"""Start a local-only GDB debug session for a challenge binary."""

from __future__ import annotations

import argparse

from _gdb_cli import emit
from ctf_solver_core.gdb_session import GDB_MODES, start_gdb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--mode", choices=GDB_MODES, default="docker")
    parser.add_argument("--workspace")
    parser.add_argument("--run-id")
    parser.add_argument("--challenge-id")
    parser.add_argument("--worker-id")
    parser.add_argument("--args")
    parser.add_argument("--breakpoint", action="append", default=[])
    parser.add_argument("--image", default="ctf-pwn:latest")
    parser.add_argument("--timeout-ms", type=int, default=2000)
    parser.add_argument("--max-bytes", type=int, default=8000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = start_gdb(
        binary_path=args.binary,
        mode=args.mode,
        workspace=args.workspace,
        run_id=args.run_id,
        challenge_id=args.challenge_id,
        worker_id=args.worker_id,
        args=args.args,
        breakpoint=args.breakpoint,
        image=args.image,
        timeout_ms=args.timeout_ms,
        max_bytes=args.max_bytes,
    )
    if args.json:
        emit(result, json_output=True)
    else:
        print(str(result["gdb_session"]["gdb_session_id"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
