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
from ctf_solver_core.paths import metrics_root, resolve_path
from ctf_solver_core.schemas import (
    CATEGORIES,
    PLATFORMS,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="private run directory")
    parser.add_argument("--run-id", help="run_id for duplicate prevention when --run-dir is unavailable")
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--platform", choices=PLATFORMS)
    parser.add_argument("--event")
    parser.add_argument("--challenge-name")
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--flag")
    parser.add_argument("--writeup-generated", action="store_true")
    parser.add_argument("--exploit-included", action="store_true")
    parser.add_argument("--cleanup-bytes-saved", type=int)
    parser.add_argument("--tool-call-counts-json")
    parser.add_argument("--model-tooling-summary")
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
    if args.include_challenge_name and challenge_name:
        record["challenge_name"] = challenge_name

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
    summary = metrics_root() / "summary.jsonl"
    errors: list[str] = []
    for index, record in enumerate(read_jsonl(summary), start=1):
        errors.extend(f"summary.jsonl:{index}: {error}" for error in validate_public_record(record))
    return errors


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
        "public_summary_updated": False,
        "duplicate_skipped": False,
        "replaced_existing": False,
    }

    if run_dir and not args.dry_run:
        atomic_write_json(run_dir / "run.json", private)
        result["private_run_updated"] = True

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
