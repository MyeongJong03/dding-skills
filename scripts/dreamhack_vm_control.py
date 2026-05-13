#!/usr/bin/env python3
"""Control a Dreamhack VM through the platform adapter and resource lease policy."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platform_automation import control_dreamhack_vm
from ctf_solver_core.resources import default_worker_id
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default="dreamhack")
    parser.add_argument("--event", default="dreamhackWargame")
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--action", required=True, choices=["start", "stop", "restart", "status"])
    parser.add_argument("--adapter", default="dreamhack", choices=["dreamhack"])
    parser.add_argument("--policy")
    parser.add_argument("--worker-id")
    parser.add_argument("--role", default="primary", choices=["primary", "helper"])
    parser.add_argument("--confirm", action="store_true", help="confirm allow_server_create=ask policy")
    parser.add_argument("--live", action="store_true", help="allow the Dreamhack live VM request")
    parser.add_argument("--base-url")
    parser.add_argument("--session-id", help="local-only Dreamhack session value; prefer env/file for shell history")
    parser.add_argument("--csrf-token", dest="csrf_value", help="local-only CSRF value; prefer env/file for shell history")
    parser.add_argument("--session-id-file", help="repo-external file containing the Dreamhack session value")
    parser.add_argument("--csrf-token-file", dest="csrf_value_file", help="repo-external file containing the CSRF value")
    parser.add_argument("--lease-id")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    worker_id = args.worker_id or default_worker_id()
    result = control_dreamhack_vm(
        platform=args.platform,
        event=args.event,
        challenge_id=args.challenge_id,
        run_id=args.run_id,
        action=args.action,
        adapter_name=args.adapter,
        policy_path=args.policy,
        worker_id=worker_id,
        confirmed=args.confirm,
        role=args.role,
        live=args.live,
        session_id=args.session_id,
        csrf_value=args.csrf_value,
        session_id_file=args.session_id_file,
        csrf_value_file=args.csrf_value_file,
        base_url=args.base_url,
        lease_id=args.lease_id,
    )
    result["worker_id"] = worker_id
    if args.json:
        print(json_dumps(result), end="")
    else:
        if result.get("ok"):
            vm_action = result.get("vm_action") if isinstance(result.get("vm_action"), dict) else {}
            print(
                f"Dreamhack VM {args.action}: "
                f"status={vm_action.get('status')} state={vm_action.get('vm_state')}"
            )
            if result.get("lease_id"):
                print(f"lease: {result.get('lease_id')}")
        elif result.get("requires_confirmation"):
            print(result.get("reason"))
            print(result.get("suggested_command"))
        else:
            print(f"Dreamhack VM action failed: {result.get('reason')}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
