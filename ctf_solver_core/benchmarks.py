"""Benchmark definition and result helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from .locks import DirectoryLock
from .paths import metrics_root, private_benchmark_root, public_benchmark_root, resolve_path
from .schemas import (
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_text,
    iso_now,
    parse_iso,
    read_json,
    read_jsonl,
    slugify,
    validate_public_record,
)
from .verifier import load_verifier_result, verifier_summary


BENCHMARK_STATUSES = ("solved", "abandoned", "skipped", "timeout", "failed", "manual_stop")
TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise ValueError(f"expected true/false, got {value!r}")


def _load_dict(path: Path) -> dict[str, object]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def _duration_sec(challenge: dict[str, object], final: dict[str, object]) -> float | None:
    value = final.get("duration_sec")
    if isinstance(value, (int, float)):
        return max(0.0, round(float(value), 3))
    start = parse_iso(str(challenge.get("created_at") or ""))
    end = parse_iso(str(final.get("finalized_at") or final.get("timestamp") or ""))
    if start and end:
        return max(0.0, round((end - start).total_seconds(), 3))
    return None


def _nonnegative_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return default


def _nonnegative_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, round(float(value), 3))
    return default


def _counts_from(final: dict[str, object], key: str) -> dict[str, int]:
    value = final.get(key)
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for name, count in value.items():
        if isinstance(name, str) and isinstance(count, (int, float)):
            counts[name] = max(0, int(count))
    return counts


def create_benchmark_definition(
    *,
    benchmark_id: str,
    platform: str,
    event: str,
    category: str,
    difficulty: str = "",
    local_capable: bool,
    remote_required: bool,
    timeout_sec: int,
    private: bool = False,
    challenge_id: str = "",
    expected_status: str = "",
    flag_regex: str = "",
    verifier_required: bool = False,
    notes: str = "",
    tags: list[str] | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": 1,
        "benchmark_id": benchmark_id,
        "challenge_id": challenge_id or benchmark_id,
        "platform": platform,
        "event": event,
        "category": category,
        "difficulty": difficulty or None,
        "local_capable": bool(local_capable),
        "remote_required": bool(remote_required),
        "expected_status": expected_status or None,
        "success_oracle": {
            "flag_regex": flag_regex or None,
            "verifier_required": bool(verifier_required),
        },
        "timeout_sec": max(1, int(timeout_sec)),
        "notes": notes,
        "tags": tags or [],
        "created_at": iso_now(),
    }
    errors = validate_public_record(record)
    if errors:
        raise ValueError("benchmark definition is not public-safe: " + "; ".join(errors))

    root = private_benchmark_root() if private else public_benchmark_root()
    path = root / f"{slugify(benchmark_id, fallback='benchmark', max_length=120)}.json"
    with DirectoryLock("benchmark-definition-update", "benchmark definition update"):
        atomic_write_json(path, record)
    return {"definition": record, "path": str(path), "private": private}


def build_benchmark_result(
    *,
    benchmark_id: str,
    run_id: str,
    attempt_index: int,
    status: str,
    run_dir: Path | None = None,
    category: str = "",
    platform: str = "",
    event: str = "",
    duration_sec: float | None = None,
    time_to_flag_sec: float | None = None,
    verifier_success: bool | None = None,
    verifier_flag_found: bool | None = None,
    ai_usage_id: str = "",
) -> dict[str, object]:
    challenge = _load_dict(run_dir / "challenge.json") if run_dir else {}
    final = _load_dict(run_dir / "finalize.json") if run_dir else {}
    if run_dir and not final:
        final = _load_dict(run_dir / "finalization.json")

    verifier = final.get("verifier") if isinstance(final.get("verifier"), dict) else None
    if not verifier and run_dir:
        verifier = load_verifier_result(run_dir)
    verifier_info = verifier_summary(verifier)

    resource_metrics = final.get("resource_metrics") if isinstance(final.get("resource_metrics"), dict) else {}
    session_metrics = final.get("session_metrics") if isinstance(final.get("session_metrics"), dict) else {}
    browser_metrics = final.get("browser_metrics") if isinstance(final.get("browser_metrics"), dict) else {}
    callback_metrics = final.get("callback_metrics") if isinstance(final.get("callback_metrics"), dict) else {}
    worker_metrics = final.get("worker_metrics") if isinstance(final.get("worker_metrics"), dict) else {}

    if duration_sec is None:
        duration_sec = _duration_sec(challenge, final)
    if time_to_flag_sec is None and isinstance(final.get("time_to_flag_sec"), (int, float)):
        time_to_flag_sec = float(final["time_to_flag_sec"])

    record: dict[str, object] = {
        "schema_version": 1,
        "benchmark_id": benchmark_id,
        "run_id": run_id or str(final.get("run_id") or challenge.get("run_id") or (run_dir.name if run_dir else "")),
        "attempt_index": max(1, int(attempt_index)),
        "status": status,
        "verifier_success": bool(verifier_success if verifier_success is not None else verifier_info.get("success")),
        "verifier_flag_found": bool(
            verifier_flag_found if verifier_flag_found is not None else verifier_info.get("flag_found")
        ),
        "duration_sec": _nonnegative_float(duration_sec, 0.0),
        "tool_counts": _counts_from(final, "tool_call_counts"),
        "session_counts": {
            "session_count": _nonnegative_int(session_metrics.get("session_count")),
            "closed_session_count": _nonnegative_int(session_metrics.get("closed_session_count")),
        },
        "browser_action_count": _nonnegative_int(browser_metrics.get("browser_actions_count")),
        "callback_hit_count": _nonnegative_int(callback_metrics.get("callback_hit_count")),
        "worker_action_count": _nonnegative_int(worker_metrics.get("worker_action_count")),
        "remote_wait_time_sec": _nonnegative_float(resource_metrics.get("remote_wait_time_sec"), 0.0),
        "cleanup_bytes_saved": _nonnegative_int(
            (final.get("cleanup") if isinstance(final.get("cleanup"), dict) else {}).get("bytes_deleted")
        ),
        "created_at": iso_now(),
    }
    category_value = category or str(final.get("category") or challenge.get("category") or "")
    platform_value = platform or str(final.get("platform") or challenge.get("platform") or "")
    event_value = event or str(final.get("event") or challenge.get("event") or "")
    if category_value:
        record["category"] = category_value
    if platform_value:
        record["platform"] = platform_value
    if event_value:
        record["event"] = event_value
    if time_to_flag_sec is not None:
        record["time_to_flag_sec"] = _nonnegative_float(time_to_flag_sec)
    if ai_usage_id:
        record["ai_usage_id"] = ai_usage_id

    errors = validate_public_record(record)
    if errors:
        raise ValueError("benchmark result is not public-safe: " + "; ".join(errors))
    return record


def record_benchmark_result(record: dict[str, object], *, replace: bool = False, dry_run: bool = False) -> dict[str, object]:
    path = metrics_root() / "benchmark_summary.jsonl"
    with DirectoryLock("benchmark-result-update", "benchmark result update"):
        records = read_jsonl(path)
        key = (
            str(record.get("benchmark_id") or ""),
            str(record.get("run_id") or ""),
            int(record.get("attempt_index") or 0),
        )
        existing_count = sum(
            1
            for item in records
            if (
                str(item.get("benchmark_id") or ""),
                str(item.get("run_id") or ""),
                int(item.get("attempt_index") or 0),
            )
            == key
        )
        result: dict[str, object] = {
            "summary_path": str(path),
            "duplicate_skipped": False,
            "replaced_existing": False,
            "public_summary_updated": False,
            "record": record,
        }
        if existing_count and not replace:
            result["duplicate_skipped"] = True
            result["existing_count"] = existing_count
            return result
        if existing_count and replace:
            records = [
                item
                for item in records
                if (
                    str(item.get("benchmark_id") or ""),
                    str(item.get("run_id") or ""),
                    int(item.get("attempt_index") or 0),
                )
                != key
            ]
            result["replaced_existing"] = True
            result["existing_count"] = existing_count
        records.append(record)
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_jsonl(path, records)
            result["public_summary_updated"] = True
    return result


def _rate(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100.0), 1) if denominator else 0.0


def summarize_benchmarks(records: list[dict[str, object]]) -> dict[str, object]:
    attempts = len(records)
    status_counts = Counter(str(record.get("status") or "unknown") for record in records)
    by_benchmark: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        by_benchmark[str(record.get("benchmark_id") or "unknown")].append(record)

    def solved_within(items: list[dict[str, object]], limit: int) -> bool:
        return any(str(item.get("status")) == "solved" and int(item.get("attempt_index") or 0) <= limit for item in items)

    benchmark_count = len(by_benchmark)
    pass1 = sum(1 for items in by_benchmark.values() if solved_within(items, 1))
    pass3 = sum(1 for items in by_benchmark.values() if solved_within(items, 3))
    time_values = [
        float(record["time_to_flag_sec"])
        for record in records
        if record.get("status") == "solved" and isinstance(record.get("time_to_flag_sec"), (int, float))
    ]
    verifier_records = [record for record in records if "verifier_success" in record]
    verifier_success = sum(1 for record in verifier_records if record.get("verifier_success"))

    by_category: dict[str, Counter[str]] = defaultdict(Counter)
    by_platform_event: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        status = str(record.get("status") or "unknown")
        by_category[str(record.get("category") or "unknown")][status] += 1
        by_platform_event[f"{record.get('platform') or 'unknown'}/{record.get('event') or 'unknown'}"][status] += 1

    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "attempt_count": attempts,
        "benchmark_count": benchmark_count,
        "status_counts": dict(sorted(status_counts.items())),
        "pass_at_1": _rate(pass1, benchmark_count),
        "pass_at_3": _rate(pass3, benchmark_count),
        "solve_rate": _rate(status_counts.get("solved", 0), attempts),
        "abandon_rate": _rate(status_counts.get("abandoned", 0) + status_counts.get("manual_stop", 0), attempts),
        "timeout_rate": _rate(status_counts.get("timeout", 0), attempts),
        "median_time_to_flag_sec": round(float(median(time_values)), 3) if time_values else None,
        "avg_time_to_flag_sec": round(float(mean(time_values)), 3) if time_values else None,
        "verifier_success_rate": _rate(verifier_success, len(verifier_records)),
        "by_category": {key: dict(value) for key, value in sorted(by_category.items())},
        "by_platform_event": {key: dict(value) for key, value in sorted(by_platform_event.items())},
    }


def _table(counter_map: dict[str, dict[str, int]], label: str) -> list[str]:
    lines = [f"## By {label}", "", f"| {label} | Attempts | Solved | Abandoned | Timeout | Other |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, counts in sorted(counter_map.items()):
        attempts = sum(int(value) for value in counts.values())
        solved = int(counts.get("solved", 0))
        abandoned = int(counts.get("abandoned", 0)) + int(counts.get("manual_stop", 0))
        timeout = int(counts.get("timeout", 0))
        other = attempts - solved - abandoned - timeout
        lines.append(f"| `{name}` | {attempts} | {solved} | {abandoned} | {timeout} | {other} |")
    return lines


def render_benchmark_dashboard(summary: dict[str, object]) -> str:
    lines = [
        "# Benchmark Dashboard",
        "",
        f"- Last updated: `{summary.get('updated_at')}`",
        f"- Benchmark items: `{summary.get('benchmark_count')}`",
        f"- Attempts: `{summary.get('attempt_count')}`",
        f"- pass@1: `{summary.get('pass_at_1'):.1f}%`",
        f"- pass@3: `{summary.get('pass_at_3'):.1f}%`",
        f"- Solve rate: `{summary.get('solve_rate'):.1f}%`",
        f"- Abandon rate: `{summary.get('abandon_rate'):.1f}%`",
        f"- Timeout rate: `{summary.get('timeout_rate'):.1f}%`",
        f"- Median time to flag: `{summary.get('median_time_to_flag_sec')}`",
        f"- Average time to flag: `{summary.get('avg_time_to_flag_sec')}`",
        f"- Verifier success rate: `{summary.get('verifier_success_rate'):.1f}%`",
        "",
    ]
    lines.extend(_table(summary.get("by_category", {}), "Category"))  # type: ignore[arg-type]
    lines.append("")
    lines.extend(_table(summary.get("by_platform_event", {}), "Platform/Event"))  # type: ignore[arg-type]
    lines.append("")
    return "\n".join(lines)


def generate_benchmark_report(*, dry_run: bool = False) -> dict[str, object]:
    root = metrics_root()
    summary_path = root / "benchmark_summary.jsonl"
    dashboard_path = root / "benchmark_dashboard.md"
    records = read_jsonl(summary_path)
    summary = summarize_benchmarks(records)
    errors = validate_public_record(summary)
    if errors:
        raise ValueError("benchmark aggregate is not public-safe: " + "; ".join(errors))
    dashboard = render_benchmark_dashboard(summary)
    with DirectoryLock("benchmark-report-update", "benchmark report update"):
        if not dry_run:
            root.mkdir(parents=True, exist_ok=True)
            atomic_write_text(dashboard_path, dashboard)
    return {"summary": summary, "dashboard_path": str(dashboard_path), "record_count": len(records)}

