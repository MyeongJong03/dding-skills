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
from ctf_solver_core.platform_automation import release_local_server_records_for_run
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
from ctf_solver_core.browser_client import close_browser_sessions_for_run
from ctf_solver_core.session_client import close_sessions_for_run
from ctf_solver_core.verifier import load_verifier_result, verifier_summary
from ctf_solver_core.worker import release_claim
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
    parser.add_argument("--keep-server", action="store_true", help="do not release active platform server records for this run")
    parser.add_argument("--keep-sessions", action="store_true", help="do not close persistent sessions for this run")
    parser.add_argument(
        "--keep-browser-sessions",
        action="store_true",
        help="do not close browser action sessions for this run",
    )
    parser.add_argument(
        "--require-verifier",
        action="store_true",
        help="fail solved finalization unless <run_dir>/verifier.json is successful",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing finalization for this run")
    parser.add_argument("--auto-finalize-used", action="store_true", help="record worker auto-finalize usage in metrics")
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
    verifier = load_verifier_result(run_dir)
    verifier_info = verifier_summary(verifier, include_preview=True)
    verifier_warnings: list[str] = []
    verifier_success = bool(verifier_info.get("success"))
    if args.status == "solved":
        if not verifier_success:
            warning = "status=solved without successful verifier"
            verifier_warnings.append(warning)
            if args.require_verifier and not args.force:
                raise RuntimeError(f"{warning}; use --force to override")

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
            claim_release_result = {"released_count": 0, "reason": "already_finalized"}
            if not args.dry_run:
                claim_release_result = release_claim(run_id=run_id, reason="already_finalized")
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
                "sessions": existing.get("sessions") or {},
                "browser_sessions": existing.get("browser_sessions") or {},
                "verifier": existing.get("verifier") or {},
                "warnings": existing.get("warnings") or [],
                "platform_server_release": existing.get("platform_server_release") or {},
                "resource_release": existing.get("resource_release") or {},
                "queue": existing.get("queue") or {},
                "worker_claim_release": claim_release_result,
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

        session_result: dict[str, object] | None = None
        if getattr(args, "keep_sessions", False):
            session_result = {
                "ok": True,
                "reason": "kept_by_request",
                "session_count": 0,
                "closed_session_count": 0,
                "session_bytes_read": 0,
                "session_bytes_written": 0,
                "errors": [],
            }
        elif args.dry_run:
            session_result = {
                "ok": True,
                "reason": "dry_run",
                "session_count": 0,
                "closed_session_count": 0,
                "session_bytes_read": 0,
                "session_bytes_written": 0,
                "errors": [],
            }
        else:
            try:
                session_result = {"ok": True, **close_sessions_for_run(run_id)}
            except Exception as exc:
                session_result = {
                    "ok": False,
                    "reason": "session_close_failed",
                    "warning": str(exc),
                    "session_count": 0,
                    "closed_session_count": 0,
                    "session_bytes_read": 0,
                    "session_bytes_written": 0,
                    "errors": [str(exc)],
                }

        browser_session_result: dict[str, object] | None = None
        if getattr(args, "keep_browser_sessions", False):
            browser_session_result = {
                "ok": True,
                "reason": "kept_by_request",
                "session_count": 0,
                "closed_browser_session_count": 0,
                "browser_actions_count": 0,
                "browser_screenshot_count": 0,
                "browser_network_event_count": 0,
                "errors": [],
            }
        elif args.dry_run:
            browser_session_result = {
                "ok": True,
                "reason": "dry_run",
                "session_count": 0,
                "closed_browser_session_count": 0,
                "browser_actions_count": 0,
                "browser_screenshot_count": 0,
                "browser_network_event_count": 0,
                "errors": [],
            }
        else:
            try:
                browser_session_result = {"ok": True, **close_browser_sessions_for_run(run_id)}
            except Exception as exc:
                browser_session_result = {
                    "ok": False,
                    "reason": "browser_session_close_failed",
                    "warning": str(exc),
                    "session_count": 0,
                    "closed_browser_session_count": 0,
                    "browser_actions_count": 0,
                    "browser_screenshot_count": 0,
                    "browser_network_event_count": 0,
                    "errors": [str(exc)],
                }

        platform_server_release_result: dict[str, object] | None = None
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
        if getattr(args, "keep_server", False) or getattr(args, "keep_lease", False):
            platform_server_release_result = {"ok": True, "reason": "kept_by_request", "released": [], "released_count": 0}
        elif args.dry_run:
            platform_server_release_result = {"ok": True, "reason": "dry_run", "released": [], "released_count": 0}
        else:
            try:
                platform_server_release_result = release_local_server_records_for_run(
                    platform=platform,
                    event=event,
                    run_id=run_id,
                    reason="finalized",
                )
                for released in platform_server_release_result.get("released") or []:
                    if isinstance(released, dict):
                        append_queue_event(
                            event_type="platform_server_released",
                            challenge_id=str(released.get("challenge_id") or challenge_id),
                            run_id=str(released.get("run_id") or run_id),
                            platform=platform,
                            event=event,
                            reason="finalized",
                            public_safe_metadata={
                                "server_id": released.get("server_id"),
                                "lease_id": released.get("lease_id"),
                            },
                        )
            except Exception as exc:
                platform_server_release_result = {
                    "ok": False,
                    "reason": "server_release_failed",
                    "warning": str(exc),
                    "released": [],
                    "released_count": 0,
                }

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

        worker_claim_release: dict[str, object] | None = None
        if args.dry_run:
            worker_claim_release = {"released_count": 0, "reason": "dry_run"}
        else:
            try:
                worker_claim_release = release_claim(run_id=run_id, reason="finalized")
            except Exception as exc:
                worker_claim_release = {
                    "released_count": 0,
                    "reason": "claim_release_failed",
                    "warning": str(exc),
                }

        resource_metrics = {
            "lease_release_count": int((lease_release_result or {}).get("released_count") or 0),
            "server_release_count": int((platform_server_release_result or {}).get("released_count") or 0),
            "stale_lease_reclaimed_count": 0,
            "total_lease_held_sec": int((lease_release_result or {}).get("total_lease_held_sec") or 0),
        }
        session_metrics = {
            "session_count": int((session_result or {}).get("session_count") or 0),
            "closed_session_count": int((session_result or {}).get("closed_session_count") or 0),
            "session_bytes_read": int((session_result or {}).get("session_bytes_read") or 0),
            "session_bytes_written": int((session_result or {}).get("session_bytes_written") or 0),
        }
        browser_metrics = {
            "browser_session_count": int((browser_session_result or {}).get("session_count") or 0),
            "closed_browser_session_count": int((browser_session_result or {}).get("closed_browser_session_count") or 0),
            "browser_actions_count": int((browser_session_result or {}).get("browser_actions_count") or 0),
            "browser_screenshot_count": int((browser_session_result or {}).get("browser_screenshot_count") or 0),
            "browser_network_event_count": int((browser_session_result or {}).get("browser_network_event_count") or 0),
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
            "sessions": session_result or {},
            "session_metrics": session_metrics,
            "closed_session_count": session_metrics["closed_session_count"],
            "browser_sessions": browser_session_result or {},
            "browser_metrics": browser_metrics,
            "closed_browser_session_count": browser_metrics["closed_browser_session_count"],
            "verifier": verifier_info,
            "verifier_success": verifier_success,
            "verifier_flag_found": bool(verifier_info.get("flag_found")),
            "verifier_target": str(verifier_info.get("target") or "unknown"),
            "verifier_id": str(verifier_info.get("verifier_id") or ""),
            "warnings": verifier_warnings,
            "platform_server_release": platform_server_release_result or {},
            "platform_server_release_summary": {
                "server_release_count": resource_metrics["server_release_count"],
                "reason": (platform_server_release_result or {}).get("reason", ""),
            },
            "resource_release": lease_release_result or {},
            "resource_warnings": resource_warnings,
            "resource_metrics": resource_metrics,
            "queue": queue_result or {},
            "worker_claim_release": worker_claim_release or {},
            "worker_metrics": {
                "auto_finalize_used": bool(getattr(args, "auto_finalize_used", False)),
                "require_verifier_used": bool(getattr(args, "require_verifier", False)),
                "worker_claim_reclaim_count": 0,
            },
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
                server_release_count=resource_metrics["server_release_count"],
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
                session_count=session_metrics["session_count"],
                session_bytes_read=session_metrics["session_bytes_read"],
                session_bytes_written=session_metrics["session_bytes_written"],
                closed_session_count=session_metrics["closed_session_count"],
                browser_session_count=browser_metrics["browser_session_count"],
                closed_browser_session_count=browser_metrics["closed_browser_session_count"],
                browser_actions_count=browser_metrics["browser_actions_count"],
                browser_screenshot_count=browser_metrics["browser_screenshot_count"],
                browser_network_event_count=browser_metrics["browser_network_event_count"],
                worker_id_hash=None,
                worker_count=None,
                worker_action_count=None,
                worker_wait_count=None,
                worker_claim_reclaim_count=0,
                auto_finalize_used=bool(getattr(args, "auto_finalize_used", False)),
                require_verifier_used=bool(getattr(args, "require_verifier", False)),
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
        "sessions": session_result,
        "browser_sessions": browser_session_result,
        "verifier": verifier_info,
        "warnings": verifier_warnings,
        "platform_server_release": platform_server_release_result,
        "resource_release": lease_release_result,
        "queue": queue_result,
        "worker_claim_release": worker_claim_release,
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
