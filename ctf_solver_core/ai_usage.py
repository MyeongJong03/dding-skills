"""Private AI usage records and public-safe aggregate summaries."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any
import uuid

from .locks import DirectoryLock
from .paths import ai_usage_root, metrics_root, resolve_path
from .schemas import (
    atomic_write_jsonl,
    atomic_write_text,
    iso_now,
    parse_iso,
    read_json,
    read_jsonl,
    validate_public_record,
)


PROVIDERS = {"codex", "claude", "openai", "anthropic", "manual", "unknown"}
SOURCES = {"manual", "imported"}
_SENSITIVE_METADATA_KEYS = {
    "".join(("oauth", "account")),
    "".join(("email", "address")),
    "".join(("account", "uuid")),
    "".join(("organization", "uuid")),
    "".join(("referral", "_", "link")),
    "".join(("anonymous", "id")),
    "".join(("billing", "type")),
    "".join(("subscription", "created", "at")),
}


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str) and value.strip().isdigit():
        return max(0, int(value.strip()))
    return default


def _as_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, round(float(value), 6))
    try:
        return max(0.0, round(float(str(value)), 6))
    except (TypeError, ValueError):
        return default


def _provider(value: str | None) -> str:
    lowered = (value or "unknown").strip().lower()
    return lowered if lowered in PROVIDERS else "unknown"


def _usage_id() -> str:
    return f"aiu-{uuid.uuid4().hex[:16]}"


def _date_from(value: str | None) -> str:
    parsed = parse_iso(value or "")
    if parsed:
        return parsed.date().isoformat()
    return iso_now().split("T", 1)[0]


def build_ai_usage_record(
    *,
    run_id: str,
    provider: str,
    model: str = "",
    challenge_id: str = "",
    session_id: str = "",
    started_at: str = "",
    ended_at: str = "",
    duration_sec: float | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    web_search_requests: int | None = None,
    cost_usd: float | None = None,
    tool_duration_ms: int | None = None,
    api_duration_ms: int | None = None,
    source: str = "manual",
    source_file: str = "",
    notes: str = "",
    category: str = "",
    platform: str = "",
    event: str = "",
    status: str = "",
) -> dict[str, object]:
    started = started_at or iso_now()
    record: dict[str, object] = {
        "schema_version": 1,
        "ai_usage_id": _usage_id(),
        "run_id": run_id,
        "provider": _provider(provider),
        "model": model or "unknown",
        "challenge_id": challenge_id or None,
        "session_id": session_id or None,
        "started_at": started,
        "ended_at": ended_at or None,
        "duration_sec": _as_float(duration_sec, 0.0) if duration_sec is not None else None,
        "input_tokens": _as_int(input_tokens),
        "output_tokens": _as_int(output_tokens),
        "cache_creation_input_tokens": _as_int(cache_creation_input_tokens),
        "cache_read_input_tokens": _as_int(cache_read_input_tokens),
        "web_search_requests": _as_int(web_search_requests) if web_search_requests is not None else None,
        "cost_usd": _as_float(cost_usd, 0.0) if cost_usd is not None else 0.0,
        "tool_duration_ms": _as_int(tool_duration_ms) if tool_duration_ms is not None else None,
        "api_duration_ms": _as_int(api_duration_ms) if api_duration_ms is not None else None,
        "source": source if source in SOURCES else "manual",
        "source_file": Path(source_file).name if source_file else None,
        "notes": notes,
        "category": category or None,
        "platform": platform or None,
        "event": event or None,
        "status": status or None,
        "created_at": iso_now(),
    }
    return {key: value for key, value in record.items() if value is not None}


def public_ai_usage_summary(record: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider": str(record.get("provider") or "unknown"),
        "model": str(record.get("model") or "unknown"),
        "date": _date_from(str(record.get("started_at") or "")),
        "category": str(record.get("category") or "unknown"),
        "platform": str(record.get("platform") or "unknown"),
        "event": str(record.get("event") or "unknown"),
        "total_input_tokens": _as_int(record.get("input_tokens")),
        "total_output_tokens": _as_int(record.get("output_tokens")),
        "total_cache_read_tokens": _as_int(record.get("cache_read_input_tokens")),
        "total_cache_creation_tokens": _as_int(record.get("cache_creation_input_tokens")),
        "total_cost_usd": _as_float(record.get("cost_usd")),
        "run_count": 1,
        "solved_count": 1 if record.get("status") == "solved" else 0,
        "updated_at": iso_now(),
    }


def _merge_public_ai_usage(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, str, str], dict[str, object]] = {}
    for record in records:
        key = (
            str(record.get("provider") or "unknown"),
            str(record.get("model") or "unknown"),
            str(record.get("date") or "unknown"),
            str(record.get("category") or "unknown"),
            str(record.get("platform") or "unknown"),
            str(record.get("event") or "unknown"),
        )
        if key not in grouped:
            grouped[key] = {
                "schema_version": 1,
                "provider": key[0],
                "model": key[1],
                "date": key[2],
                "category": key[3],
                "platform": key[4],
                "event": key[5],
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cache_read_tokens": 0,
                "total_cache_creation_tokens": 0,
                "total_cost_usd": 0.0,
                "run_count": 0,
                "solved_count": 0,
                "updated_at": iso_now(),
            }
        target = grouped[key]
        for field in (
            "total_input_tokens",
            "total_output_tokens",
            "total_cache_read_tokens",
            "total_cache_creation_tokens",
            "run_count",
            "solved_count",
        ):
            target[field] = _as_int(target.get(field)) + _as_int(record.get(field))
        target["total_cost_usd"] = round(_as_float(target.get("total_cost_usd")) + _as_float(record.get("total_cost_usd")), 6)
        target["updated_at"] = iso_now()
    return [grouped[key] for key in sorted(grouped)]


def record_ai_usage(record: dict[str, object], *, dry_run: bool = False) -> dict[str, object]:
    private_path = ai_usage_root() / "usage.jsonl"
    public_path = metrics_root() / "ai_usage_summary.jsonl"
    public_record = public_ai_usage_summary(record)
    errors = validate_public_record(public_record)
    if errors:
        raise ValueError("public AI usage summary is not safe: " + "; ".join(errors))

    with DirectoryLock("ai-usage-update", "AI usage update"):
        if not dry_run:
            private_records = read_jsonl(private_path)
            private_records.append(record)
            private_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_jsonl(private_path, private_records)

            public_records = read_jsonl(public_path)
            public_records.append(public_record)
            public_records = _merge_public_ai_usage(public_records)
            for item in public_records:
                item_errors = validate_public_record(item)
                if item_errors:
                    raise ValueError("public AI usage aggregate is not safe: " + "; ".join(item_errors))
            public_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_jsonl(public_path, public_records)

    return {
        "record": record,
        "public_record": public_record,
        "private_path": str(private_path),
        "public_summary_path": str(public_path),
        "dry_run": dry_run,
    }


def _normalize_key(key: object) -> str:
    return str(key).replace("-", "_").replace(" ", "_").lower()


def _is_sensitive_metadata_key(key: object) -> bool:
    normalized = str(key).replace("_", "").replace("-", "").lower()
    return normalized in {item.replace("_", "") for item in _SENSITIVE_METADATA_KEYS}


def _first(mapping: dict[str, object], *keys: str) -> object:
    normalized = {_normalize_key(key): value for key, value in mapping.items()}
    for key in keys:
        if key in normalized:
            return normalized[key]
    return None


def _extract_usage(node: dict[str, object], context: dict[str, object]) -> dict[str, object] | None:
    usage = node.get("usage") if isinstance(node.get("usage"), dict) else {}
    merged: dict[str, object] = {**context, **node, **usage}  # type: ignore[arg-type]
    input_tokens = _as_int(_first(merged, "input_tokens", "prompt_tokens"))
    output_tokens = _as_int(_first(merged, "output_tokens", "completion_tokens"))
    cache_create = _as_int(_first(merged, "cache_creation_input_tokens", "cache_creation_tokens"))
    cache_read = _as_int(_first(merged, "cache_read_input_tokens", "cache_read_tokens"))
    cost = _as_float(_first(merged, "cost_usd", "costusd", "total_cost_usd"))
    duration = _as_float(_first(merged, "duration_sec", "duration_seconds"))
    if not any([input_tokens, output_tokens, cache_create, cache_read, cost, duration]):
        return None
    return build_ai_usage_record(
        run_id=str(_first(merged, "run_id") or "imported"),
        provider=str(_first(merged, "provider") or context.get("provider") or "unknown"),
        model=str(_first(merged, "model") or context.get("model") or "unknown"),
        challenge_id=str(_first(merged, "challenge_id") or ""),
        session_id=str(_first(merged, "session_id") or ""),
        started_at=str(_first(merged, "started_at") or _first(merged, "timestamp") or ""),
        ended_at=str(_first(merged, "ended_at") or ""),
        duration_sec=duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_create,
        cache_read_input_tokens=cache_read,
        web_search_requests=_as_int(_first(merged, "web_search_requests")) if _first(merged, "web_search_requests") is not None else None,
        cost_usd=cost,
        tool_duration_ms=_as_int(_first(merged, "tool_duration_ms")) if _first(merged, "tool_duration_ms") is not None else None,
        api_duration_ms=_as_int(_first(merged, "api_duration_ms")) if _first(merged, "api_duration_ms") is not None else None,
        source="imported",
        source_file=str(context.get("source_file") or ""),
        category=str(_first(merged, "category") or ""),
        platform=str(_first(merged, "platform") or ""),
        event=str(_first(merged, "event") or ""),
        status=str(_first(merged, "status") or ""),
    )


def _iter_usage_records(node: object, context: dict[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if isinstance(node, dict):
        clean_items = {key: value for key, value in node.items() if not _is_sensitive_metadata_key(key)}
        next_context = dict(context)
        for key in ("provider", "model", "run_id", "category", "platform", "event", "status"):
            value = _first(clean_items, key)
            if value not in (None, ""):
                next_context[key] = value
        extracted = _extract_usage(clean_items, next_context)
        if extracted:
            records.append(extracted)
        for key, value in clean_items.items():
            if extracted and _normalize_key(key) == "usage":
                continue
            records.extend(_iter_usage_records(value, next_context))
    elif isinstance(node, list):
        for item in node:
            records.extend(_iter_usage_records(item, context))
    return records


def import_ai_usage(
    *,
    input_path: str | Path,
    source: str,
    provider: str = "",
    run_id: str = "",
    dry_run: bool = False,
) -> dict[str, object]:
    path = resolve_path(input_path)
    data = read_json(path, default={})
    context = {
        "source_file": path.name,
        "provider": provider or ("claude" if source == "claude-json" else "manual"),
    }
    if run_id:
        context["run_id"] = run_id
    records = _iter_usage_records(data, context)
    results = [record_ai_usage(record, dry_run=dry_run) for record in records]
    return {
        "imported_count": len(records),
        "input_basename": path.name,
        "source": source,
        "filtered_sensitive_metadata": True,
        "public_summary_path": str(metrics_root() / "ai_usage_summary.jsonl"),
        "private_path": str(ai_usage_root() / "usage.jsonl"),
        "dry_run": dry_run,
        "records": [
            {
                "ai_usage_id": item["record"].get("ai_usage_id"),
                "provider": item["record"].get("provider"),
                "model": item["record"].get("model"),
                "input_tokens": item["record"].get("input_tokens"),
                "output_tokens": item["record"].get("output_tokens"),
                "cost_usd": item["record"].get("cost_usd"),
            }
            for item in results
        ],
    }


def summarize_ai_usage(records: list[dict[str, object]]) -> dict[str, object]:
    total_input = sum(_as_int(record.get("total_input_tokens")) for record in records)
    total_output = sum(_as_int(record.get("total_output_tokens")) for record in records)
    total_cache_read = sum(_as_int(record.get("total_cache_read_tokens")) for record in records)
    total_cache_create = sum(_as_int(record.get("total_cache_creation_tokens")) for record in records)
    total_cost = round(sum(_as_float(record.get("total_cost_usd")) for record in records), 6)
    run_count = sum(_as_int(record.get("run_count")) for record in records)
    solved_count = sum(_as_int(record.get("solved_count")) for record in records)
    by_provider: dict[str, dict[str, object]] = defaultdict(lambda: {"run_count": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    for record in records:
        provider = str(record.get("provider") or "unknown")
        item = by_provider[provider]
        item["run_count"] = _as_int(item["run_count"]) + _as_int(record.get("run_count"))
        item["input_tokens"] = _as_int(item["input_tokens"]) + _as_int(record.get("total_input_tokens"))
        item["output_tokens"] = _as_int(item["output_tokens"]) + _as_int(record.get("total_output_tokens"))
        item["cost_usd"] = round(_as_float(item["cost_usd"]) + _as_float(record.get("total_cost_usd")), 6)
    time_values = [
        float(record["median_time_to_flag_sec"])
        for record in records
        if isinstance(record.get("median_time_to_flag_sec"), (int, float))
    ]
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "record_count": len(records),
        "run_count": run_count,
        "solved_count": solved_count,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_read_tokens": total_cache_read,
        "total_cache_creation_tokens": total_cache_create,
        "total_cost_usd": total_cost,
        "median_time_to_flag_sec": round(float(median(time_values)), 3) if time_values else None,
        "by_provider": dict(sorted(by_provider.items())),
    }


def render_ai_usage_dashboard(summary: dict[str, object]) -> str:
    lines = [
        "# AI Usage Dashboard",
        "",
        f"- Last updated: `{summary.get('updated_at')}`",
        f"- Aggregate rows: `{summary.get('record_count')}`",
        f"- Runs counted: `{summary.get('run_count')}`",
        f"- Solved count: `{summary.get('solved_count')}`",
        f"- Input tokens: `{summary.get('total_input_tokens')}`",
        f"- Output tokens: `{summary.get('total_output_tokens')}`",
        f"- Cache read tokens: `{summary.get('total_cache_read_tokens')}`",
        f"- Cache creation tokens: `{summary.get('total_cache_creation_tokens')}`",
        f"- Total cost USD: `{summary.get('total_cost_usd')}`",
        "",
        "## By Provider",
        "",
        "| Provider | Runs | Input Tokens | Output Tokens | Cost USD |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for provider, item in (summary.get("by_provider") or {}).items():  # type: ignore[union-attr]
        lines.append(
            f"| `{provider}` | {item.get('run_count', 0)} | {item.get('input_tokens', 0)} | "
            f"{item.get('output_tokens', 0)} | {item.get('cost_usd', 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_ai_usage_report(*, dry_run: bool = False) -> dict[str, object]:
    root = metrics_root()
    summary_path = root / "ai_usage_summary.jsonl"
    dashboard_path = root / "ai_usage_dashboard.md"
    records = read_jsonl(summary_path)
    summary = summarize_ai_usage(records)
    errors = validate_public_record(summary)
    if errors:
        raise ValueError("AI usage aggregate is not public-safe: " + "; ".join(errors))
    dashboard = render_ai_usage_dashboard(summary)
    with DirectoryLock("ai-usage-report-update", "AI usage report update"):
        if not dry_run:
            root.mkdir(parents=True, exist_ok=True)
            atomic_write_text(dashboard_path, dashboard)
    return {"summary": summary, "dashboard_path": str(dashboard_path), "record_count": len(records)}
