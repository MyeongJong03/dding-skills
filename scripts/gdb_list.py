#!/usr/bin/env python3
"""List GDB debug sessions without raw logs or transcripts."""

from __future__ import annotations

import argparse

from _gdb_cli import emit
from ctf_solver_core.gdb_session import list_gdb_sessions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--challenge-id")
    parser.add_argument("--include-closed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = list_gdb_sessions(
        run_id=args.run_id,
        challenge_id=args.challenge_id,
        include_closed=args.include_closed,
    )
    emit(result, json_output=args.json, text_key="sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
