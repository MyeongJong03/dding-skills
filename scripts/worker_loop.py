#!/usr/bin/env python3
"""Run the queue worker scaffold loop."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.worker import heartbeat_claim, make_worker_id
from worker_run_once import run_once


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--policy", help="platform policy YAML path")
    parser.add_argument("--interval-sec", type=float, default=10.0)
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--require-verifier", action="store_true")
    parser.add_argument("--auto-acquire-remote", action="store_true")
    parser.add_argument("--auto-finalize", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    worker_id = args.worker_id or make_worker_id()
    args.worker_id = worker_id
    iterations = 0
    try:
        while True:
            if not args.dry_run:
                heartbeat_claim(worker_id=worker_id)
            result = run_once(args)
            iterations += 1
            if args.json:
                print(json_dumps({"iteration": iterations, **result}), end="")
            else:
                decision = result["decision"]
                print(
                    f"[{iterations}] {decision.get('action')} "
                    f"{decision.get('challenge_id') or ''} {decision.get('reason')}"
                )
                execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
                if execution.get("suggested_command"):
                    print(execution["suggested_command"])
            if args.max_iterations is not None and iterations >= args.max_iterations:
                break
            time.sleep(max(0.1, float(args.interval_sec)))
    except KeyboardInterrupt:
        if args.json:
            print(json_dumps({"ok": True, "worker_id": worker_id, "stopped": "keyboard_interrupt"}), end="")
        else:
            print("worker loop stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
