#!/usr/bin/env python3
"""Manage the local-only callback listener daemon."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.callback_client import status as daemon_status
from ctf_solver_core.callback_client import stop_daemon
from ctf_solver_core.callback_daemon import serve_forever
from ctf_solver_core.schemas import json_dumps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "status", "stop"), nargs="?", default="status")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "serve":
        return serve_forever()
    if args.command == "stop":
        result = stop_daemon()
    else:
        result = daemon_status()

    if args.json:
        print(json_dumps(result), end="")
    else:
        if result.get("running"):
            print(f"callback daemon running pid={result.get('pid')} {result.get('host')}:{result.get('port')}")
        else:
            print("callback daemon not running")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
