#!/usr/bin/env python3
"""List persistent CTF sessions tracked by the local daemon."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.session_client import list_sessions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--challenge-id")
    parser.add_argument("--include-closed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = list_sessions(
        run_id=args.run_id,
        challenge_id=args.challenge_id,
        include_closed=args.include_closed,
    )
    if args.json:
        print(json_dumps(result), end="")
    else:
        for item in result.get("sessions") or []:
            print(
                f"{item.get('session_id')} {item.get('status')} {item.get('kind')} "
                f"run={item.get('run_id') or '-'} pid={item.get('pid') or '-'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
