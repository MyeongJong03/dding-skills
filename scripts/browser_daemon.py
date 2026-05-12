#!/usr/bin/env python3
"""Run or stop the loopback-only browser action daemon."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.browser_client import status, stop_daemon
from ctf_solver_core.browser_daemon import serve_forever
from ctf_solver_core.schemas import json_dumps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("serve", "stop", "status"), default="serve")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "serve":
        return serve_forever()
    result = stop_daemon() if args.command == "stop" else status()
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
