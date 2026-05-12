#!/usr/bin/env python3
"""Run one queue worker orchestration step."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ctf_solver_core.platforms import get_platform_policy
from ctf_solver_core.queue import append_queue_event
from ctf_solver_core.resources import acquire_remote_server
from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.worker import choose_worker_action, make_worker_id, release_claim, resolve_run_dir_for_item
from challenge_finalize import finalize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--worker-id")
    parser.add_argument("--policy", help="platform policy YAML path")
    parser.add_argument("--require-verifier", action="store_true")
    parser.add_argument("--auto-acquire-remote", action="store_true")
    parser.add_argument("--auto-finalize", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _item_from_decision(decision: dict[str, object]) -> dict[str, object]:
    return {
        "challenge_id": decision.get("challenge_id") or "",
        "run_id": decision.get("run_id") or "",
        "platform": decision.get("platform") or "",
        "event": decision.get("event") or "",
        "state": decision.get("status") or "",
        "queue_id": decision.get("queue_id") or "",
    }


def _run_auto_acquire(policy, decision: dict[str, object], worker_id: str, *, dry_run: bool) -> dict[str, object]:
    challenge_id = str(decision.get("challenge_id") or "")
    run_id = str(decision.get("run_id") or "")
    mode = "helper" if decision.get("action") == "join_remote_as_helper" else "primary"
    if dry_run:
        return {"ok": True, "dry_run": True, "reason": "dry_run", "mode": mode}
    result = acquire_remote_server(policy, challenge_id, run_id, worker_id=worker_id, mode=mode)
    append_queue_event(
        event_type="worker_auto_acquire_remote",
        challenge_id=challenge_id,
        run_id=run_id,
        platform=policy.platform,
        event=policy.event,
        worker_id=worker_id,
        reason=str(result.get("reason") or ""),
        public_safe_metadata={
            "ok": bool(result.get("ok")),
            "mode": mode,
        },
    )
    return result


def _run_auto_finalize(policy, decision: dict[str, object], *, require_verifier: bool, dry_run: bool) -> dict[str, object]:
    item = _item_from_decision(decision)
    run_dir = resolve_run_dir_for_item(item)
    if not run_dir:
        return {"ok": False, "reason": "run_dir_not_found"}
    status = str(decision.get("status") or "manual_stop")
    args = argparse.Namespace(
        run_dir=str(run_dir),
        status=status,
        reason="worker_auto_finalize",
        platform=None,
        event=None,
        challenge_name=None,
        category=None,
        flag=None,
        exploit=[],
        workspace=None,
        generate_writeup=False,
        cleanup=False,
        update_metrics=False,
        git_sync=False,
        no_push=True,
        keep_lease=False,
        keep_sessions=False,
        require_verifier=require_verifier,
        auto_finalize_used=True,
        force=False,
        dry_run=dry_run,
    )
    result = finalize(args)
    append_queue_event(
        event_type="worker_auto_finalize",
        challenge_id=str(result.get("challenge_id") or decision.get("challenge_id") or ""),
        run_id=str(result.get("run_id") or decision.get("run_id") or ""),
        platform=policy.platform,
        event=policy.event,
        reason=status,
        public_safe_metadata={
            "status": status,
            "dry_run": dry_run,
            "require_verifier_used": require_verifier,
        },
    )
    if not dry_run:
        release_claim(run_id=str(result.get("run_id") or ""), reason="auto_finalized")
    return {"ok": True, "reason": "finalized", "finalize": result}


def run_once(args: argparse.Namespace) -> dict[str, object]:
    worker_id = args.worker_id or make_worker_id()
    policy = get_platform_policy(args.platform, args.event, args.policy)
    decision = choose_worker_action(
        policy,
        worker_id=worker_id,
        allow_helper=True,
        require_verifier=bool(args.require_verifier),
        claim=not bool(args.dry_run),
    )
    action = str(decision.get("action") or "wait")
    execution: dict[str, object]

    if action in {"acquire_remote", "join_remote_as_helper"}:
        if args.auto_acquire_remote:
            execution = _run_auto_acquire(policy, decision, worker_id, dry_run=bool(args.dry_run))
        else:
            execution = {
                "ok": True,
                "reason": "manual_action_required",
                "suggested_command": decision.get("suggested_command"),
            }
    elif action == "finalize_challenge":
        if args.auto_finalize:
            execution = _run_auto_finalize(
                policy,
                decision,
                require_verifier=bool(args.require_verifier),
                dry_run=bool(args.dry_run),
            )
        else:
            execution = {
                "ok": True,
                "reason": "manual_action_required",
                "suggested_command": decision.get("suggested_command"),
            }
    elif action == "verify_solution":
        execution = {
            "ok": True,
            "reason": "verifier_command_required",
            "suggested_command": decision.get("suggested_command"),
        }
    elif action == "do_local_work":
        execution = {
            "ok": True,
            "reason": "claimed_for_local_work",
            "suggested_next_steps": [
                "inspect local artifacts",
                "update queue state after local proof or blocker",
                "do not invoke Codex or Claude from this worker scaffold",
            ],
        }
    else:
        execution = {"ok": True, "reason": decision.get("reason") or action}

    return {
        "ok": bool(execution.get("ok", True)),
        "worker_id": worker_id,
        "decision": decision,
        "execution": execution,
        "dry_run": bool(args.dry_run),
    }


def main() -> int:
    args = build_parser().parse_args()
    result = run_once(args)
    if args.json:
        print(json_dumps(result), end="")
    else:
        decision = result["decision"]
        execution = result["execution"]
        print(
            f"{decision.get('action')} {decision.get('challenge_id') or ''} "
            f"{decision.get('run_id') or ''}: {decision.get('reason')}"
        )
        if execution.get("suggested_command"):
            print(execution["suggested_command"])
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
