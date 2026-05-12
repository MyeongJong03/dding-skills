#!/usr/bin/env python3
"""Update private run metrics and public-safe aggregate metrics."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.locks import DirectoryLock
from ctf_solver_core.paths import metrics_root, private_metrics_root, resolve_path
from ctf_solver_core.performance import validate_public_metrics_files
from ctf_solver_core.schemas import (
    CATEGORIES,
    STATUSES,
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_text,
    iso_now,
    json_dumps,
    parse_iso,
    read_json,
    read_jsonl,
    validate_public_record,
)
from ctf_solver_core.verifier import load_verifier_result, verifier_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="private run directory")
    parser.add_argument("--run-id", help="run_id for duplicate prevention when --run-dir is unavailable")
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--challenge-name")
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--flag")
    parser.add_argument("--writeup-generated", action="store_true")
    parser.add_argument("--exploit-included", action="store_true")
    parser.add_argument("--cleanup-bytes-saved", type=int)
    parser.add_argument("--time-to-flag-sec", type=float)
    parser.add_argument("--remote-wait-time-sec", type=int)
    parser.add_argument("--local-prework-time-sec", type=int)
    parser.add_argument("--remote-lease-time-sec", type=int)
    parser.add_argument("--resource-blocked-count", type=int)
    parser.add_argument("--lease-acquire-count", type=int)
    parser.add_argument("--lease-release-count", type=int)
    parser.add_argument("--server-release-count", type=int)
    parser.add_argument("--stale-lease-reclaimed-count", type=int)
    parser.add_argument("--remote-blocked-count", type=int)
    parser.add_argument("--scheduler-wait-count", type=int)
    parser.add_argument("--scheduler-local-work-count", type=int)
    parser.add_argument("--scheduler-helper-join-count", type=int)
    parser.add_argument("--total-remote-wait-time-sec", type=int)
    parser.add_argument("--total-lease-held-sec", type=int)
    parser.add_argument("--shared-remote-used", action="store_true")
    parser.add_argument("--helper-workers-used", type=int)
    parser.add_argument("--local-ready-before-remote", action="store_true")
    parser.add_argument("--session-count", type=int)
    parser.add_argument("--session-bytes-read", type=int)
    parser.add_argument("--session-bytes-written", type=int)
    parser.add_argument("--closed-session-count", type=int)
    parser.add_argument("--browser-session-count", type=int)
    parser.add_argument("--closed-browser-session-count", type=int)
    parser.add_argument("--browser-actions-count", type=int)
    parser.add_argument("--browser-screenshot-count", type=int)
    parser.add_argument("--browser-network-event-count", type=int)
    parser.add_argument("--callback-listener-count", type=int)
    parser.add_argument("--closed-callback-listener-count", type=int)
    parser.add_argument("--callback-hit-count", type=int)
    parser.add_argument("--callback-wait-success", action="store_true")
    parser.add_argument("--callback-wait-duration-sec", type=float)
    parser.add_argument("--web-workflow-count", type=int)
    parser.add_argument("--web-payload-count", type=int)
    parser.add_argument("--web-callback-probe-success", action="store_true")
    parser.add_argument("--web-browser-action-count", type=int)
    parser.add_argument("--web-evidence-collected", action="store_true")
    parser.add_argument("--worker-id-hash")
    parser.add_argument("--worker-count", type=int)
    parser.add_argument("--worker-action-count", type=int)
    parser.add_argument("--worker-wait-count", type=int)
    parser.add_argument("--worker-claim-reclaim-count", type=int)
    parser.add_argument("--auto-finalize-used", action="store_true")
    parser.add_argument("--require-verifier-used", action="store_true")
    parser.add_argument("--platform-discovery-count", type=int)
    parser.add_argument("--downloaded-file-count", type=int)
    parser.add_argument("--downloaded-bytes", type=int)
    parser.add_argument("--ctfd-challenge-count", type=int)
    parser.add_argument("--ctfd-download-count", type=int)
    parser.add_argument("--server-acquire-attempted", action="store_true")
    parser.add_argument("--server-acquire-success", action="store_true")
    parser.add_argument("--submission-attempted", action="store_true")
    parser.add_argument("--ctfd-submit-attempted", action="store_true")
    parser.add_argument("--submission-policy")
    parser.add_argument("--platform-adapter")
    parser.add_argument("--verifier-success", action="store_true")
    parser.add_argument("--verifier-flag-found", action="store_true")
    parser.add_argument("--verifier-target")
    parser.add_argument("--verifier-attempts", type=int)
    parser.add_argument("--verifier-duration-sec", type=float)
    parser.add_argument("--tool-call-counts-json")
    parser.add_argument("--model-tooling-summary")
    parser.add_argument("--ai-usage-id")
    parser.add_argument("--ai-provider")
    parser.add_argument("--ai-model")
    parser.add_argument("--ai-input-tokens", type=int)
    parser.add_argument("--ai-output-tokens", type=int)
    parser.add_argument("--ai-cache-read-tokens", type=int)
    parser.add_argument("--ai-cache-creation-tokens", type=int)
    parser.add_argument("--ai-cost-usd", type=float)
    parser.add_argument("--include-challenge-name", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true", help="validate public metrics without updating")
    parser.add_argument("--force", action="store_true", help="replace an existing public metrics entry for this run_id")
    parser.add_argument("--replace", action="store_true", help="replace an existing public metrics entry for this run_id")
    return parser


def _load_dict(path: Path) -> dict[str, object]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def _duration_sec(challenge: dict[str, object], final: dict[str, object]) -> int | None:
    if isinstance(final.get("duration_sec"), int):
        return int(final["duration_sec"])
    start = parse_iso(str(challenge.get("created_at") or ""))
    end = parse_iso(str(final.get("finalized_at") or final.get("timestamp") or ""))
    if start and end:
        return max(0, int((end - start).total_seconds()))
    return None


def _bool_from_final(final: dict[str, object], key: str) -> bool:
    value = final.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return bool(value.get("generated") or value.get("included"))
    return False


def _public_record(args: argparse.Namespace, run_dir: Path | None) -> tuple[dict[str, object], dict[str, object]]:
    challenge = _load_dict(run_dir / "challenge.json") if run_dir else {}
    final = _load_dict(run_dir / "finalize.json") if run_dir else {}
    if run_dir and not final:
        final = _load_dict(run_dir / "finalization.json")
    cleanup = _load_dict(run_dir / "cleanup.json") if run_dir else {}

    timestamp = str(final.get("finalized_at") or iso_now())
    run_id = str(args.run_id or final.get("run_id") or challenge.get("run_id") or (run_dir.name if run_dir else ""))
    platform = str(args.platform or final.get("platform") or challenge.get("platform") or "unknown")
    event = str(args.event or final.get("event") or challenge.get("event") or "unknown")
    category = str(args.category or final.get("category") or challenge.get("category") or "unknown")
    status = str(args.status or final.get("status") or "manual_stop")
    challenge_name = str(args.challenge_name or final.get("challenge_name") or challenge.get("challenge_name") or "")

    cleanup_bytes = args.cleanup_bytes_saved
    if cleanup_bytes is None and isinstance(cleanup.get("bytes_deleted"), int):
        cleanup_bytes = int(cleanup["bytes_deleted"])

    writeup_generated = bool(args.writeup_generated or _bool_from_final(final, "writeup_generated"))
    exploit_included = bool(args.exploit_included or _bool_from_final(final, "exploit_included"))
    if isinstance(final.get("writeup"), dict):
        writeup_generated = writeup_generated or bool(final["writeup"].get("generated"))
        exploit_included = exploit_included or bool(final["writeup"].get("exploit_included"))
    verifier = final.get("verifier") if isinstance(final.get("verifier"), dict) else None
    if not verifier and run_dir:
        verifier = load_verifier_result(run_dir)
    verifier_info = verifier_summary(verifier)

    record: dict[str, object] = {
        "schema_version": 1,
        "timestamp": timestamp,
        "run_id": run_id,
        "platform": platform,
        "event": event,
        "category": category,
        "status": status,
        "duration_sec": _duration_sec(challenge, final),
        "tool_call_counts": {},
        "cleanup_bytes_saved": cleanup_bytes or 0,
        "writeup_generated": writeup_generated,
        "exploit_included": exploit_included,
    }
    if args.tool_call_counts_json:
        import json

        parsed = json.loads(args.tool_call_counts_json)
        record["tool_call_counts"] = parsed if isinstance(parsed, dict) else {}
    if args.model_tooling_summary:
        record["model_tooling_summary"] = args.model_tooling_summary
    time_to_flag = getattr(args, "time_to_flag_sec", None)
    if time_to_flag is None and isinstance(final.get("time_to_flag_sec"), (int, float)):
        time_to_flag = float(final["time_to_flag_sec"])
    if time_to_flag is not None:
        record["time_to_flag_sec"] = max(0.0, round(float(time_to_flag), 3))
    ai_usage_id = str(getattr(args, "ai_usage_id", "") or final.get("ai_usage_id") or "")
    if ai_usage_id:
        record["ai_usage_id"] = ai_usage_id
    ai_provider = str(getattr(args, "ai_provider", "") or final.get("ai_provider") or "")
    if ai_provider:
        record["ai_provider"] = ai_provider
    ai_model = str(getattr(args, "ai_model", "") or final.get("ai_model") or "")
    if ai_model:
        record["ai_model"] = ai_model
    ai_numeric_fields = {
        "ai_input_tokens": getattr(args, "ai_input_tokens", None),
        "ai_output_tokens": getattr(args, "ai_output_tokens", None),
        "ai_cache_read_tokens": getattr(args, "ai_cache_read_tokens", None),
        "ai_cache_creation_tokens": getattr(args, "ai_cache_creation_tokens", None),
    }
    for key, value in ai_numeric_fields.items():
        if value is None and isinstance(final.get(key), int):
            value = int(final[key])
        if value is not None:
            record[key] = max(0, int(value))
    ai_cost = getattr(args, "ai_cost_usd", None)
    if ai_cost is None and isinstance(final.get("ai_cost_usd"), (int, float)):
        ai_cost = float(final["ai_cost_usd"])
    if ai_cost is not None:
        record["ai_cost_usd"] = max(0.0, round(float(ai_cost), 6))
    if args.include_challenge_name and challenge_name:
        record["challenge_name"] = challenge_name

    has_verifier_args = any(
        [
            getattr(args, "verifier_success", False),
            getattr(args, "verifier_flag_found", False),
            getattr(args, "verifier_target", None),
            getattr(args, "verifier_attempts", None) is not None,
            getattr(args, "verifier_duration_sec", None) is not None,
        ]
    )
    if verifier_info or has_verifier_args:
        record["verifier_success"] = bool(args.verifier_success or verifier_info.get("success"))
        record["verifier_flag_found"] = bool(args.verifier_flag_found or verifier_info.get("flag_found"))
        target = str(args.verifier_target or verifier_info.get("target") or "unknown")
        record["verifier_target"] = target if target in {"local", "remote", "unknown"} else "unknown"
        attempts = args.verifier_attempts
        if attempts is None:
            attempts = int(verifier_info.get("attempts") or 0)
        record["verifier_attempts"] = max(0, int(attempts))
        duration = args.verifier_duration_sec
        if duration is None and isinstance(verifier_info.get("duration_sec"), (int, float)):
            duration = float(verifier_info["duration_sec"])
        record["verifier_duration_sec"] = max(0.0, round(float(duration or 0), 3))

    resource_metrics = final.get("resource_metrics")
    if not isinstance(resource_metrics, dict):
        resource_metrics = {}
    session_metrics = final.get("session_metrics")
    if not isinstance(session_metrics, dict):
        session_metrics = {}
    worker_metrics = final.get("worker_metrics")
    if not isinstance(worker_metrics, dict):
        worker_metrics = {}
    platform_metrics = final.get("platform_metrics")
    if not isinstance(platform_metrics, dict):
        platform_metrics = {}
    browser_metrics = final.get("browser_metrics")
    if not isinstance(browser_metrics, dict):
        browser_metrics = {}
    callback_metrics = final.get("callback_metrics")
    if not isinstance(callback_metrics, dict):
        callback_metrics = {}
    web_metrics = final.get("web_metrics")
    if not isinstance(web_metrics, dict):
        web_metrics = {}

    optional_ints = {
        "remote_wait_time_sec": getattr(args, "remote_wait_time_sec", None),
        "local_prework_time_sec": getattr(args, "local_prework_time_sec", None),
        "remote_lease_time_sec": getattr(args, "remote_lease_time_sec", None),
        "resource_blocked_count": getattr(args, "resource_blocked_count", None),
        "lease_acquire_count": getattr(args, "lease_acquire_count", None),
        "lease_release_count": getattr(args, "lease_release_count", None),
        "server_release_count": getattr(args, "server_release_count", None),
        "stale_lease_reclaimed_count": getattr(args, "stale_lease_reclaimed_count", None),
        "remote_blocked_count": getattr(args, "remote_blocked_count", None),
        "scheduler_wait_count": getattr(args, "scheduler_wait_count", None),
        "scheduler_local_work_count": getattr(args, "scheduler_local_work_count", None),
        "scheduler_helper_join_count": getattr(args, "scheduler_helper_join_count", None),
        "total_remote_wait_time_sec": getattr(args, "total_remote_wait_time_sec", None),
        "total_lease_held_sec": getattr(args, "total_lease_held_sec", None),
        "helper_workers_used": getattr(args, "helper_workers_used", None),
        "session_count": getattr(args, "session_count", None),
        "session_bytes_read": getattr(args, "session_bytes_read", None),
        "session_bytes_written": getattr(args, "session_bytes_written", None),
        "closed_session_count": getattr(args, "closed_session_count", None),
        "browser_session_count": getattr(args, "browser_session_count", None),
        "closed_browser_session_count": getattr(args, "closed_browser_session_count", None),
        "browser_actions_count": getattr(args, "browser_actions_count", None),
        "browser_screenshot_count": getattr(args, "browser_screenshot_count", None),
        "browser_network_event_count": getattr(args, "browser_network_event_count", None),
        "callback_listener_count": getattr(args, "callback_listener_count", None),
        "closed_callback_listener_count": getattr(args, "closed_callback_listener_count", None),
        "callback_hit_count": getattr(args, "callback_hit_count", None),
        "web_workflow_count": getattr(args, "web_workflow_count", None),
        "web_payload_count": getattr(args, "web_payload_count", None),
        "web_browser_action_count": getattr(args, "web_browser_action_count", None),
        "worker_count": getattr(args, "worker_count", None),
        "worker_action_count": getattr(args, "worker_action_count", None),
        "worker_wait_count": getattr(args, "worker_wait_count", None),
        "worker_claim_reclaim_count": getattr(args, "worker_claim_reclaim_count", None),
        "platform_discovery_count": getattr(args, "platform_discovery_count", None),
        "downloaded_file_count": getattr(args, "downloaded_file_count", None),
        "downloaded_bytes": getattr(args, "downloaded_bytes", None),
        "ctfd_challenge_count": getattr(args, "ctfd_challenge_count", None),
        "ctfd_download_count": getattr(args, "ctfd_download_count", None),
    }
    for key, value in optional_ints.items():
        if value is None and isinstance(resource_metrics.get(key), int):
            value = int(resource_metrics[key])
        if value is None and isinstance(session_metrics.get(key), int):
            value = int(session_metrics[key])
        if value is None and isinstance(browser_metrics.get(key), int):
            value = int(browser_metrics[key])
        if value is None and isinstance(callback_metrics.get(key), int):
            value = int(callback_metrics[key])
        if value is None and isinstance(web_metrics.get(key), int):
            value = int(web_metrics[key])
        if value is None and isinstance(worker_metrics.get(key), int):
            value = int(worker_metrics[key])
        if value is None and isinstance(platform_metrics.get(key), int):
            value = int(platform_metrics[key])
        if value is not None:
            record[key] = max(0, int(value))

    shared_remote_used = bool(getattr(args, "shared_remote_used", False) or resource_metrics.get("shared_remote_used"))
    local_ready_before_remote = bool(
        getattr(args, "local_ready_before_remote", False) or resource_metrics.get("local_ready_before_remote")
    )
    if shared_remote_used:
        record["shared_remote_used"] = True
    if local_ready_before_remote:
        record["local_ready_before_remote"] = True
    worker_id_hash = str(getattr(args, "worker_id_hash", "") or worker_metrics.get("worker_id_hash") or "")
    if worker_id_hash:
        record["worker_id_hash"] = worker_id_hash
    auto_finalize_used = bool(getattr(args, "auto_finalize_used", False) or worker_metrics.get("auto_finalize_used"))
    require_verifier_used = bool(
        getattr(args, "require_verifier_used", False) or worker_metrics.get("require_verifier_used")
    )
    if auto_finalize_used:
        record["auto_finalize_used"] = True
    if require_verifier_used:
        record["require_verifier_used"] = True
    callback_wait_success = bool(
        getattr(args, "callback_wait_success", False) or callback_metrics.get("callback_wait_success")
    )
    if callback_wait_success:
        record["callback_wait_success"] = True
    callback_wait_duration = getattr(args, "callback_wait_duration_sec", None)
    if callback_wait_duration is None and isinstance(callback_metrics.get("callback_wait_duration_sec"), (int, float)):
        callback_wait_duration = float(callback_metrics["callback_wait_duration_sec"])
    if callback_wait_duration is not None:
        record["callback_wait_duration_sec"] = max(0.0, round(float(callback_wait_duration), 3))
    web_callback_probe_success = bool(
        getattr(args, "web_callback_probe_success", False) or web_metrics.get("web_callback_probe_success")
    )
    if web_callback_probe_success:
        record["web_callback_probe_success"] = True
    web_evidence_collected = bool(
        getattr(args, "web_evidence_collected", False) or web_metrics.get("web_evidence_collected")
    )
    if web_evidence_collected:
        record["web_evidence_collected"] = True
    server_acquire_attempted = bool(
        getattr(args, "server_acquire_attempted", False) or platform_metrics.get("server_acquire_attempted")
    )
    server_acquire_success = bool(
        getattr(args, "server_acquire_success", False) or platform_metrics.get("server_acquire_success")
    )
    submission_attempted = bool(
        getattr(args, "submission_attempted", False) or platform_metrics.get("submission_attempted")
    )
    ctfd_submit_attempted = bool(
        getattr(args, "ctfd_submit_attempted", False) or platform_metrics.get("ctfd_submit_attempted")
    )
    if server_acquire_attempted:
        record["server_acquire_attempted"] = True
    if server_acquire_success:
        record["server_acquire_success"] = True
    if submission_attempted:
        record["submission_attempted"] = True
    if ctfd_submit_attempted:
        record["ctfd_submit_attempted"] = True
    submission_policy = str(getattr(args, "submission_policy", "") or platform_metrics.get("submission_policy") or "")
    if submission_policy:
        record["submission_policy"] = submission_policy
    platform_adapter = str(getattr(args, "platform_adapter", "") or platform_metrics.get("platform_adapter") or "")
    if platform_adapter:
        record["platform_adapter"] = platform_adapter

    private = {
        "updated_at": iso_now(),
        "finalized": bool(final.get("finalized") or final.get("finalized_at")),
        "status": status,
        "finalized_at": timestamp,
        "run_id": run_id,
        "challenge": challenge,
        "finalization": final,
        "flag": args.flag or final.get("flag"),
        "public_record": record,
    }
    return record, private


def _render_dashboard(records: list[dict[str, object]]) -> str:
    total = len(records)
    solved = sum(1 for record in records if record.get("status") == "solved")
    abandoned = sum(
        1
        for record in records
        if record.get("status") in {"abandoned", "skipped", "timeout", "budget_exhausted", "manual_stop"}
    )
    solve_rate = (solved / total * 100.0) if total else 0.0
    writeups = sum(1 for record in records if record.get("writeup_generated"))
    exploits = sum(1 for record in records if record.get("exploit_included"))
    cleanup_total = sum(int(record.get("cleanup_bytes_saved") or 0) for record in records)

    by_category: dict[str, Counter[str]] = defaultdict(Counter)
    by_event: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        status = str(record.get("status") or "unknown")
        category = str(record.get("category") or "unknown")
        platform = str(record.get("platform") or "unknown")
        event = str(record.get("event") or "unknown")
        by_category[category][status] += 1
        by_event[f"{platform}/{event}"][status] += 1

    lines = [
        "# CTF Solver Metrics Dashboard",
        "",
        f"- Last updated: `{iso_now()}`",
        f"- Total attempts: `{total}`",
        f"- Solved count: `{solved}`",
        f"- Abandoned/skipped count: `{abandoned}`",
        f"- Solve rate: `{solve_rate:.1f}%`",
        f"- Writeups generated: `{writeups}`",
        f"- Exploits included in local writeups: `{exploits}`",
        f"- Cleanup bytes saved total: `{cleanup_total}`",
        "",
        "## By Category",
        "",
        "| Category | Attempts | Solved | Other |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category, counts in sorted(by_category.items()):
        attempts = sum(counts.values())
        solved_count = counts.get("solved", 0)
        lines.append(f"| `{category}` | {attempts} | {solved_count} | {attempts - solved_count} |")

    lines.extend(
        [
            "",
            "## By Platform/Event",
            "",
            "| Platform/Event | Attempts | Solved | Other |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for event, counts in sorted(by_event.items()):
        attempts = sum(counts.values())
        solved_count = counts.get("solved", 0)
        lines.append(f"| `{event}` | {attempts} | {solved_count} | {attempts - solved_count} |")

    lines.append("")
    return "\n".join(lines)


def check_public_metrics() -> list[str]:
    return validate_public_metrics_files(metrics_root())


def update_metrics(args: argparse.Namespace) -> dict[str, object]:
    run_dir = resolve_path(args.run_dir) if args.run_dir else None
    record, private = _public_record(args, run_dir)
    errors = validate_public_record(record)
    if errors:
        raise ValueError("public metrics record is not safe: " + "; ".join(errors))

    mode = os.environ.get("CTF_METRICS_MODE", "public").strip().lower()
    public_enabled = mode not in {"off", "private-only", "private_only"}
    if public_enabled and not str(record.get("run_id") or ""):
        raise ValueError("public metrics updates require --run-dir or --run-id for duplicate prevention")
    result: dict[str, object] = {
        "public_enabled": public_enabled,
        "dry_run": args.dry_run,
        "record": record,
        "private_run_updated": False,
        "private_metrics_updated": False,
        "public_summary_updated": False,
        "duplicate_skipped": False,
        "replaced_existing": False,
    }

    if run_dir and not args.dry_run:
        atomic_write_json(run_dir / "run.json", private)
        result["private_run_updated"] = True

    private_run_id = str(record.get("run_id") or "")
    if private_run_id and not args.dry_run:
        private_path = private_metrics_root() / f"{private_run_id}.json"
        with DirectoryLock("private-metrics-update", "private metrics update"):
            atomic_write_json(private_path, private)
        result["private_metrics_updated"] = True
        result["private_metrics_path"] = str(private_path)

    if not public_enabled:
        return result

    with DirectoryLock("metrics-update", "public metrics update"):
        root = metrics_root()
        summary = root / "summary.jsonl"
        dashboard = root / "dashboard.md"
        records = read_jsonl(summary)
        run_id = str(record.get("run_id") or "")
        existing_count = sum(1 for item in records if run_id and item.get("run_id") == run_id)
        replace = bool(args.replace or args.force)
        if existing_count and not replace:
            result["duplicate_skipped"] = True
            result["public_summary_updated"] = False
            result["existing_count"] = existing_count
            result["summary_path"] = str(summary)
            return result
        if existing_count and replace:
            records = [item for item in records if item.get("run_id") != run_id]
            result["replaced_existing"] = True
            result["existing_count"] = existing_count
        records.append(record)
        if not args.dry_run:
            root.mkdir(parents=True, exist_ok=True)
            atomic_write_jsonl(summary, records)
            atomic_write_text(dashboard, _render_dashboard(records))
            result["public_summary_updated"] = True
        result["summary_path"] = str(summary)
    return result


def main() -> int:
    args = build_parser().parse_args()
    if args.check:
        errors = check_public_metrics()
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print("OK: public metrics are safe")
        return 0
    result = update_metrics(args)
    print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
