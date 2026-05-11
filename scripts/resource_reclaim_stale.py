#!/usr/bin/env python3
"""Detect and optionally reclaim stale resource leases."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.paths import display_path, is_inside_repo, lease_root
from ctf_solver_core.queue import append_queue_event
from ctf_solver_core.resources import REMOTE_SERVER, reclaim_stale_leases
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--resource", default=REMOTE_SERVER, choices=[REMOTE_SERVER])
    parser.add_argument("--dry-run", dest="apply", action="store_false", default=False)
    parser.add_argument("--apply", dest="apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _record_events(result: dict[str, object], applied: bool) -> None:
    for stale in result.get("stale_leases") or []:
        if not isinstance(stale, dict):
            continue
        append_queue_event(
            event_type="lease_stale_detected",
            challenge_id=str(stale.get("challenge_id") or ""),
            run_id=str(stale.get("run_id") or ""),
            platform=str(stale.get("platform") or ""),
            event=str(stale.get("event") or ""),
            reason=str(stale.get("stale_reason") or "stale"),
            public_safe_metadata={
                "lease_id": stale.get("lease_id"),
                "resource_type": stale.get("resource_type"),
                "role": stale.get("role"),
            },
        )
    if not applied:
        return
    for reclaimed in result.get("reclaimed") or []:
        if not isinstance(reclaimed, dict):
            continue
        append_queue_event(
            event_type="lease_stale_reclaimed",
            challenge_id=str(reclaimed.get("challenge_id") or ""),
            run_id=str(reclaimed.get("run_id") or ""),
            platform=str(reclaimed.get("platform") or ""),
            event=str(reclaimed.get("event") or ""),
            reason=str(reclaimed.get("release_reason") or "stale_reclaimed"),
            public_safe_metadata={
                "lease_id": reclaimed.get("lease_id"),
                "resource_type": reclaimed.get("resource_type"),
                "role": reclaimed.get("role"),
                "held_sec": reclaimed.get("held_sec"),
            },
        )


def main() -> int:
    args = build_parser().parse_args()
    root = lease_root()
    if is_inside_repo(root):
        result = {
            "ok": False,
            "reason": "lease_root_inside_repo_refused",
            "lease_root": display_path(root),
        }
        print(json_dumps(result), end="")
        return 1

    result = reclaim_stale_leases(
        platform=args.platform,
        event=args.event,
        resource_type=args.resource,
        dry_run=not args.apply,
    )
    result["lease_root"] = display_path(root)
    try:
        _record_events(result, applied=args.apply)
    except Exception as exc:
        result["event_log_warning"] = str(exc)

    if args.json:
        print(json_dumps(result), end="")
    else:
        mode = "apply" if args.apply else "dry-run"
        print(
            f"{mode}: stale={result.get('stale_count', 0)} "
            f"reclaimed={result.get('reclaimed_count', 0)} lease_root={display_path(root)}"
        )
        for stale in result.get("stale_leases") or []:
            if isinstance(stale, dict):
                print(
                    f"- {stale.get('lease_id')} {stale.get('platform')}/{stale.get('event')} "
                    f"{stale.get('challenge_id')} reason={stale.get('stale_reason')}"
                )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
