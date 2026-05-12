"""Public-safe performance aggregate reporting."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from .locks import DirectoryLock
from .paths import metrics_root
from .schemas import atomic_write_json, atomic_write_text, iso_now, read_json, read_jsonl, validate_public_record


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return default


def _as_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, round(float(value), 3))
    return default


def _rate(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100.0), 1) if denominator else 0.0


def validate_public_metrics_files(root: Path | None = None) -> list[str]:
    base = root or metrics_root()
    errors: list[str] = []
    for path in sorted(base.rglob("*.jsonl")):
        for index, record in enumerate(read_jsonl(path), start=1):
            rel = path.relative_to(base).as_posix()
            errors.extend(f"{rel}:{index}: {error}" for error in validate_public_record(record))
    for path in sorted(base.rglob("*.json")):
        rel = path.relative_to(base).as_posix()
        data = read_json(path, default={})
        if isinstance(data, list):
            for index, record in enumerate(data, start=1):
                if isinstance(record, dict):
                    errors.extend(f"{rel}:{index}: {error}" for error in validate_public_record(record))
                else:
                    errors.append(f"{rel}:{index}: expected JSON object")
        elif isinstance(data, dict):
            errors.extend(f"{rel}: {error}" for error in validate_public_record(data))
        else:
            errors.append(f"{rel}: expected JSON object or array")
    return errors


def _attempt_key(record: dict[str, object]) -> str:
    run_id = str(record.get("run_id") or "")
    if run_id:
        return run_id
    return "|".join(
        [
            str(record.get("benchmark_id") or ""),
            str(record.get("attempt_index") or ""),
            str(record.get("created_at") or record.get("timestamp") or ""),
        ]
    )


def _combined_attempts(summary_records: list[dict[str, object]], benchmark_records: list[dict[str, object]]) -> list[dict[str, object]]:
    combined: dict[str, dict[str, object]] = {}
    for record in summary_records:
        combined[_attempt_key(record)] = dict(record)
    for record in benchmark_records:
        key = _attempt_key(record)
        if key in combined:
            merged = dict(record)
            merged.update(combined[key])
            combined[key] = merged
        else:
            combined[key] = dict(record)
    return list(combined.values())


def summarize_performance(
    summary_records: list[dict[str, object]],
    benchmark_records: list[dict[str, object]],
    ai_usage_records: list[dict[str, object]],
) -> dict[str, object]:
    attempts = _combined_attempts(summary_records, benchmark_records)
    status_counts = Counter(str(record.get("status") or "unknown") for record in attempts)
    solved = status_counts.get("solved", 0)
    abandoned = (
        status_counts.get("abandoned", 0)
        + status_counts.get("manual_stop", 0)
        + status_counts.get("skipped", 0)
        + status_counts.get("failed", 0)
    )
    timeout = status_counts.get("timeout", 0)
    time_values = [
        float(record["time_to_flag_sec"])
        for record in attempts
        if record.get("status") == "solved" and isinstance(record.get("time_to_flag_sec"), (int, float))
    ]
    verifier_records = [record for record in attempts if "verifier_success" in record]
    verifier_success = sum(1 for record in verifier_records if record.get("verifier_success"))

    tool_counts: Counter[str] = Counter()
    session_count = 0
    closed_session_count = 0
    browser_action_count = 0
    callback_hit_count = 0
    worker_action_count = 0
    cleanup_bytes_saved = 0
    remote_wait_time_sec = 0.0
    local_prework_time_sec = 0.0
    for record in attempts:
        counts = record.get("tool_call_counts") or record.get("tool_counts")
        if isinstance(counts, dict):
            for name, count in counts.items():
                tool_counts[str(name)] += _as_int(count)
        session_counts = record.get("session_counts")
        if isinstance(session_counts, dict):
            session_count += _as_int(session_counts.get("session_count"))
            closed_session_count += _as_int(session_counts.get("closed_session_count"))
        session_count += _as_int(record.get("session_count"))
        closed_session_count += _as_int(record.get("closed_session_count"))
        browser_action_count += _as_int(record.get("browser_actions_count")) + _as_int(record.get("browser_action_count"))
        callback_hit_count += _as_int(record.get("callback_hit_count"))
        worker_action_count += _as_int(record.get("worker_action_count"))
        cleanup_bytes_saved += _as_int(record.get("cleanup_bytes_saved"))
        remote_wait_time_sec += _as_float(record.get("remote_wait_time_sec")) + _as_float(record.get("total_remote_wait_time_sec"))
        local_prework_time_sec += _as_float(record.get("local_prework_time_sec"))

    ai_totals = {
        "total_input_tokens": sum(_as_int(record.get("total_input_tokens")) for record in ai_usage_records),
        "total_output_tokens": sum(_as_int(record.get("total_output_tokens")) for record in ai_usage_records),
        "total_cache_read_tokens": sum(_as_int(record.get("total_cache_read_tokens")) for record in ai_usage_records),
        "total_cache_creation_tokens": sum(_as_int(record.get("total_cache_creation_tokens")) for record in ai_usage_records),
        "total_cost_usd": round(sum(_as_float(record.get("total_cost_usd")) for record in ai_usage_records), 6),
        "run_count": sum(_as_int(record.get("run_count")) for record in ai_usage_records),
    }
    by_model_provider: Counter[str] = Counter()
    for record in ai_usage_records:
        by_model_provider[f"{record.get('provider') or 'unknown'}/{record.get('model') or 'unknown'}"] += _as_int(
            record.get("run_count")
        )

    by_category: dict[str, Counter[str]] = {}
    by_platform_event: dict[str, Counter[str]] = {}
    for record in attempts:
        category = str(record.get("category") or "unknown")
        event = f"{record.get('platform') or 'unknown'}/{record.get('event') or 'unknown'}"
        by_category.setdefault(category, Counter())[str(record.get("status") or "unknown")] += 1
        by_platform_event.setdefault(event, Counter())[str(record.get("status") or "unknown")] += 1

    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "total_attempts": len(attempts),
        "status_counts": dict(sorted(status_counts.items())),
        "solved_count": solved,
        "abandoned_count": abandoned,
        "timeout_count": timeout,
        "solve_rate": _rate(solved, len(attempts)),
        "abandon_rate": _rate(abandoned, len(attempts)),
        "timeout_rate": _rate(timeout, len(attempts)),
        "verifier_success_rate": _rate(verifier_success, len(verifier_records)),
        "median_time_to_flag_sec": round(float(median(time_values)), 3) if time_values else None,
        "tool_usage_top": dict(tool_counts.most_common(10)),
        "session_count": session_count,
        "closed_session_count": closed_session_count,
        "browser_action_count": browser_action_count,
        "callback_hit_count": callback_hit_count,
        "worker_action_count": worker_action_count,
        "remote_wait_time_sec": round(remote_wait_time_sec, 3),
        "local_prework_time_sec": round(local_prework_time_sec, 3),
        "cleanup_bytes_saved": cleanup_bytes_saved,
        "ai_usage": ai_totals,
        "ai_by_provider_model": dict(sorted(by_model_provider.items())),
        "by_category": {key: dict(value) for key, value in sorted(by_category.items())},
        "by_platform_event": {key: dict(value) for key, value in sorted(by_platform_event.items())},
        "source_records": {
            "summary": len(summary_records),
            "benchmark": len(benchmark_records),
            "ai_usage": len(ai_usage_records),
        },
    }


def _status_table(title: str, rows: dict[str, dict[str, int]]) -> list[str]:
    lines = [f"## {title}", "", "| Name | Attempts | Solved | Abandoned | Timeout | Other |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, counts in sorted(rows.items()):
        attempts = sum(_as_int(value) for value in counts.values())
        solved = _as_int(counts.get("solved"))
        abandoned = _as_int(counts.get("abandoned")) + _as_int(counts.get("manual_stop")) + _as_int(counts.get("skipped"))
        timeout = _as_int(counts.get("timeout"))
        other = attempts - solved - abandoned - timeout
        lines.append(f"| `{name}` | {attempts} | {solved} | {abandoned} | {timeout} | {other} |")
    return lines


def render_performance_dashboard(summary: dict[str, object]) -> str:
    ai_usage = summary.get("ai_usage") if isinstance(summary.get("ai_usage"), dict) else {}
    lines = [
        "# Performance Dashboard",
        "",
        f"- Last updated: `{summary.get('updated_at')}`",
        f"- Total attempts: `{summary.get('total_attempts')}`",
        f"- Solved: `{summary.get('solved_count')}`",
        f"- Abandoned/skipped/failed: `{summary.get('abandoned_count')}`",
        f"- Timeout: `{summary.get('timeout_count')}`",
        f"- Solve rate: `{summary.get('solve_rate'):.1f}%`",
        f"- Verifier success rate: `{summary.get('verifier_success_rate'):.1f}%`",
        f"- Median time to flag: `{summary.get('median_time_to_flag_sec')}`",
        f"- Remote wait seconds: `{summary.get('remote_wait_time_sec')}`",
        f"- Local prework seconds: `{summary.get('local_prework_time_sec')}`",
        f"- Cleanup bytes saved: `{summary.get('cleanup_bytes_saved')}`",
        f"- AI input tokens: `{ai_usage.get('total_input_tokens', 0)}`",
        f"- AI output tokens: `{ai_usage.get('total_output_tokens', 0)}`",
        f"- AI total cost USD: `{ai_usage.get('total_cost_usd', 0)}`",
        "",
        "## Tool Usage Top 10",
        "",
        "| Tool | Calls |",
        "| --- | ---: |",
    ]
    tool_usage = summary.get("tool_usage_top") if isinstance(summary.get("tool_usage_top"), dict) else {}
    for name, count in tool_usage.items():
        lines.append(f"| `{name}` | {count} |")
    lines.extend(
        [
            "",
            "## Runtime Counters",
            "",
            f"- Sessions opened: `{summary.get('session_count')}`",
            f"- Sessions closed: `{summary.get('closed_session_count')}`",
            f"- Browser actions: `{summary.get('browser_action_count')}`",
            f"- Callback hits: `{summary.get('callback_hit_count')}`",
            f"- Worker actions: `{summary.get('worker_action_count')}`",
            "",
        ]
    )
    lines.extend(_status_table("By Category", summary.get("by_category", {})))  # type: ignore[arg-type]
    lines.append("")
    lines.extend(_status_table("By Platform/Event", summary.get("by_platform_event", {})))  # type: ignore[arg-type]
    lines.append("")
    return "\n".join(lines)


def generate_performance_report(*, dry_run: bool = False) -> dict[str, object]:
    root = metrics_root()
    summary_records = read_jsonl(root / "summary.jsonl")
    benchmark_records = read_jsonl(root / "benchmark_summary.jsonl")
    ai_usage_records = read_jsonl(root / "ai_usage_summary.jsonl")
    summary = summarize_performance(summary_records, benchmark_records, ai_usage_records)
    errors = validate_public_record(summary)
    if errors:
        raise ValueError("performance summary is not public-safe: " + "; ".join(errors))
    dashboard = render_performance_dashboard(summary)
    with DirectoryLock("performance-report-update", "performance report update"):
        if not dry_run:
            root.mkdir(parents=True, exist_ok=True)
            atomic_write_json(root / "performance_summary.json", summary)
            atomic_write_text(root / "performance_dashboard.md", dashboard)
    return {
        "summary": summary,
        "summary_path": str(root / "performance_summary.json"),
        "dashboard_path": str(root / "performance_dashboard.md"),
    }
