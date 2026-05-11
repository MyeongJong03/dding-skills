#!/usr/bin/env python3
"""Finalize one challenge run: writeup, cleanup, metrics, and optional git sync."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ctf_solver_core.locks import DirectoryLock
from ctf_solver_core.paths import display_path, resolve_path, work_root
from ctf_solver_core.queue import append_queue_event, mark_finalized
from ctf_solver_core.resources import REMOTE_SERVER, detect_stale_leases, release_lease
from ctf_solver_core.schemas import (
    CATEGORIES,
    STATUSES,
    atomic_write_json,
    iso_now,
    json_dumps,
    make_challenge_id,
    parse_iso,
    read_json,
)
from cleanup_challenge import cleanup
from generate_writeup import generate_writeup
from git_sync_metrics import git_sync
from update_metrics import update_metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--status", choices=STATUSES, required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--challenge-name")
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--flag")
    parser.add_argument("--exploit", action="append", default=[])
    parser.add_argument("--workspace")
    parser.add_argument("--generate-writeup", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--update-metrics", action="store_true")
    parser.add_argument("--git-sync", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--keep-lease", action="store_true", help="do not release active resource leases for this run")
    parser.add_argument("--force", action="store_true", help="replace an existing finalization for this run")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _load_challenge(run_dir: Path) -> dict[str, object]:
    data = read_json(run_dir / "challenge.json", default={})
    return data if isinstance(data, dict) else {}


def _load_finalization(run_dir: Path) -> dict[str, object]:
    for name in ("finalization.json", "finalize.json"):
        data = read_json(run_dir / name, default={})
        if isinstance(data, dict) and data:
            return data
    run = read_json(run_dir / "run.json", default={})
    if isinstance(run, dict) and isinstance(run.get("finalization"), dict):
        return run["finalization"]
    return {}


def _duration(challenge: dict[str, object], finalized_at: str) -> int | None:
    start = parse_iso(str(challenge.get("created_at") or ""))
    end = parse_iso(finalized_at)
    if not start or not end:
        return None
    return max(0, int((end - start).total_seconds()))


def _collect_exploits(run_dir: Path, explicit: list[str]) -> list[Path]:
    paths = [resolve_path(path) for path in explicit]
    if paths:
        return paths
    exploit_dir = run_dir / "exploit"
    if not exploit_dir.is_dir():
        return []
    return [path for path in sorted(exploit_dir.iterdir()) if path.is_file()]


def _archive_exploits(run_dir: Path, exploits: list[Path], dry_run: bool) -> list[str]:
    archive_dir = run_dir / "exploit"
    archived: list[str] = []
    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)
    for exploit in exploits:
        if not exploit.is_file():
            raise FileNotFoundError(f"exploit file not found: {exploit}")
        destination = archive_dir / exploit.name
        if destination.exists() and destination.resolve() != exploit.resolve():
            index = 2
            while True:
                candidate = archive_dir / f"{exploit.stem}_{index}{exploit.suffix}"
                if not candidate.exists():
                    destination = candidate
                    break
                index += 1
        if destination.resolve() != exploit.resolve() and not dry_run:
            shutil.copy2(exploit, destination)
        archived.append(str(destination))
    return archived


def finalize(args: argparse.Namespace) -> dict[str, object]:
    run_dir = resolve_path(args.run_dir)
    challenge = _load_challenge(run_dir)
    platform = str(args.platform or challenge.get("platform") or "unknown")
    event = str(args.event or challenge.get("event") or "unknown")
    challenge_name = str(args.challenge_name or challenge.get("challenge_name") or "unknown")
    category = str(args.category or challenge.get("category") or "unknown")
    challenge_id = str(
        challenge.get("challenge_id") or make_challenge_id(platform, event, challenge_name, category)
    )
    run_id = str(challenge.get("run_id") or run_dir.name)
    workspace = resolve_path(args.workspace) if args.workspace else resolve_path(
        str(challenge.get("workspace") or (work_root() / challenge_id))
    )
    finalized_at = iso_now()
    exploits = _collect_exploits(run_dir, args.exploit)

    with DirectoryLock(f"finalize-{challenge_id}-{run_id}", "challenge finalization", wait_seconds=120):
        existing = _load_finalization(run_dir)
        existing_finalized = bool(existing.get("finalized") or existing.get("finalized_at"))
        existing_status = str(existing.get("status") or "")
        if existing_finalized and existing_status != args.status and not args.force:
            raise RuntimeError(
                f"run already finalized as {existing_status!r}; "
                f"use --force to replace it with {args.status!r}"
            )
        if existing_finalized and existing_status == args.status and not args.force:
            return {
                "challenge_id": challenge_id,
                "run_id": run_id,
                "status": args.status,
                "already_finalized": True,
                "finalized_at": existing.get("finalized_at"),
                "display_run_dir": display_path(run_dir),
                "display_workspace": display_path(workspace),
                "archived_exploits": existing.get("archived_exploits") or [],
                "writeup": existing.get("writeup") or {},
                "cleanup": existing.get("cleanup") or {},
                "resource_release": existing.get("resource_release") or {},
                "queue": existing.get("queue") or {},
                "metrics": {"duplicate_skipped": True, "reason": "already finalized"},
                "git_sync": None,
                "dry_run": args.dry_run,
            }

        archived_exploits = _archive_exploits(run_dir, exploits, args.dry_run)

        writeup_result: dict[str, object] | None = None
        if args.generate_writeup:
            writeup_args = argparse.Namespace(
                run_dir=str(run_dir),
                platform=platform,
                event=event,
                challenge_name=challenge_name,
                category=category,
                flag=args.flag,
                exclude_flag=False,
                exploit=[str(path) for path in exploits],
                workspace=str(workspace),
                dry_run=args.dry_run,
            )
            writeup_result = generate_writeup(writeup_args)

        cleanup_result: dict[str, object] | None = None
        if args.cleanup:
            cleanup_args = argparse.Namespace(
                workspace=str(workspace) if workspace.exists() else None,
                run_dir=str(run_dir),
                apply=not args.dry_run,
                dry_run=args.dry_run,
            )
            cleanup_result = cleanup(cleanup_args)

        lease_release_result: dict[str, object] | None = None
        queue_result: dict[str, object] | None = None
        resource_warnings: list[dict[str, object]] = []
        stale_leases = detect_stale_leases(
            platform=platform,
            event=event,
            resource_type=REMOTE_SERVER,
            run_id=run_id,
        )
        if stale_leases:
            resource_warnings.append(
                {
                    "type": "stale_leases_present",
                    "count": len(stale_leases),
                    "lease_ids": [item.get("lease_id") for item in stale_leases],
                }
            )
            if not args.dry_run:
                for stale in stale_leases:
                    append_queue_event(
                        event_type="lease_stale_detected",
                        challenge_id=challenge_id,
                        run_id=run_id,
                        platform=platform,
                        event=event,
                        reason=str(stale.get("stale_reason") or "stale"),
                        public_safe_metadata={
                            "lease_id": stale.get("lease_id"),
                            "resource_type": stale.get("resource_type"),
                            "role": stale.get("role"),
                        },
                    )
        if getattr(args, "keep_lease", False):
            lease_release_result = {"ok": True, "reason": "kept_by_request", "released": []}
            if not args.dry_run:
                append_queue_event(
                    event_type="keep_lease",
                    challenge_id=challenge_id,
                    run_id=run_id,
                    platform=platform,
                    event=event,
                    reason=args.reason or "keep_lease_requested",
                )
        elif args.dry_run:
            lease_release_result = {"ok": True, "reason": "dry_run", "released": []}
        else:
            try:
                lease_release_result = release_lease(
                    run_id=run_id,
                    platform=platform,
                    event=event,
                    release_reason="finalized",
                )
                for released in lease_release_result.get("released_records") or []:
                    if isinstance(released, dict):
                        append_queue_event(
                            event_type="lease_released",
                            challenge_id=str(released.get("challenge_id") or challenge_id),
                            run_id=str(released.get("run_id") or run_id),
                            platform=str(released.get("platform") or platform),
                            event=str(released.get("event") or event),
                            reason="finalized",
                            public_safe_metadata={
                                "lease_id": released.get("lease_id"),
                                "resource_type": released.get("resource_type"),
                                "role": released.get("role"),
                                "held_sec": released.get("held_sec"),
                            },
                        )
            except Exception as exc:
                lease_release_result = {"ok": False, "reason": "release_failed", "warning": str(exc), "released": []}

        if args.dry_run:
            queue_result = {"updated": False, "reason": "dry_run"}
        else:
            try:
                queue_result = mark_finalized(
                    challenge_id=challenge_id,
                    run_id=run_id,
                    reason=args.reason or args.status,
                )
                if not queue_result.get("updated"):
                    append_queue_event(
                        event_type="finalized",
                        challenge_id=challenge_id,
                        run_id=run_id,
                        platform=platform,
                        event=event,
                        reason=args.reason or args.status,
                    )
            except Exception as exc:
                queue_result = {"updated": False, "reason": "queue_update_failed", "warning": str(exc)}

        resource_metrics = {
            "lease_release_count": int((lease_release_result or {}).get("released_count") or 0),
            "stale_lease_reclaimed_count": 0,
            "total_lease_held_sec": int((lease_release_result or {}).get("total_lease_held_sec") or 0),
        }

        final_record = {
            "schema_version": 1,
            "finalized": True,
            "finalized_at": finalized_at,
            "challenge_id": challenge_id,
            "run_id": run_id,
            "platform": platform,
            "event": event,
            "challenge_name": challenge_name,
            "category": category,
            "status": args.status,
            "reason": args.reason,
            "flag": args.flag,
            "duration_sec": _duration(challenge, finalized_at),
            "workspace": str(workspace),
            "run_dir": str(run_dir),
            "archived_exploits": archived_exploits,
            "writeup": writeup_result or {},
            "writeup_generated": bool(writeup_result and writeup_result.get("generated")),
            "exploit_included": bool(writeup_result and writeup_result.get("exploit_included")),
            "cleanup": cleanup_result or {},
            "resource_release": lease_release_result or {},
            "resource_warnings": resource_warnings,
            "resource_metrics": resource_metrics,
            "queue": queue_result or {},
            "forced": bool(args.force),
            "previous_status": existing_status if existing_finalized else "",
        }
        if not args.dry_run:
            run_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(run_dir / "finalize.json", final_record)
            atomic_write_json(run_dir / "finalization.json", final_record)
            atomic_write_json(
                run_dir / "run.json",
                {
                    "schema_version": 1,
                    "updated_at": iso_now(),
                    "finalized": True,
                    "status": args.status,
                    "challenge": challenge,
                    "finalization": final_record,
                    "flag": args.flag,
                },
            )

        metrics_result: dict[str, object] | None = None
        if args.update_metrics:
            metrics_args = argparse.Namespace(
                run_dir=str(run_dir),
                status=args.status,
                platform=platform,
                event=event,
                challenge_name=challenge_name,
                category=category,
                flag=args.flag,
                writeup_generated=bool(writeup_result and writeup_result.get("generated")),
                exploit_included=bool(writeup_result and writeup_result.get("exploit_included")),
                cleanup_bytes_saved=int((cleanup_result or {}).get("bytes_deleted") or 0),
                remote_wait_time_sec=None,
                local_prework_time_sec=None,
                remote_lease_time_sec=None,
                resource_blocked_count=None,
                lease_acquire_count=None,
                lease_release_count=resource_metrics["lease_release_count"],
                stale_lease_reclaimed_count=resource_metrics["stale_lease_reclaimed_count"],
                remote_blocked_count=None,
                scheduler_wait_count=None,
                scheduler_local_work_count=None,
                scheduler_helper_join_count=None,
                total_remote_wait_time_sec=None,
                total_lease_held_sec=resource_metrics["total_lease_held_sec"],
                shared_remote_used=False,
                helper_workers_used=None,
                local_ready_before_remote=False,
                tool_call_counts_json=None,
                model_tooling_summary=None,
                include_challenge_name=False,
                run_id=run_id,
                force=args.force,
                replace=args.force,
                dry_run=args.dry_run,
            )
            metrics_result = update_metrics(metrics_args)

        git_result: dict[str, object] | None = None
        if args.git_sync:
            git_args = argparse.Namespace(
                commit_message="Update public CTF solver metrics",
                push=False,
                no_push=args.no_push,
                dry_run=args.dry_run,
            )
            git_result = git_sync(git_args)

    return {
        "challenge_id": challenge_id,
        "run_id": run_id,
        "status": args.status,
        "flag_present": bool(args.flag),
        "display_run_dir": display_path(run_dir),
        "display_workspace": display_path(workspace),
        "archived_exploits": archived_exploits,
        "writeup": writeup_result,
        "cleanup": cleanup_result,
        "resource_release": lease_release_result,
        "queue": queue_result,
        "metrics": metrics_result,
        "git_sync": git_result,
        "dry_run": args.dry_run,
    }


def main() -> int:
    args = build_parser().parse_args()
    result = finalize(args)
    print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
