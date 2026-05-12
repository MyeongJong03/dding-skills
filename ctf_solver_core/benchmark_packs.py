"""Private benchmark pack and public-safe comparison helpers."""

from __future__ import annotations

import json
from pathlib import Path
import re

from .benchmarks import summarize_benchmarks
from .paths import (
    is_inside_repo,
    is_relative_to,
    private_benchmark_root,
    public_benchmark_export_root,
    public_comparison_root,
    resolve_path,
)
from .schemas import atomic_write_json, atomic_write_jsonl, iso_now, read_jsonl, slugify, validate_public_record


PACK_MANIFEST_NAME = "benchmark_pack.yaml"
TOP_LEVEL_KEYS = {"pack_id", "name", "version", "created_at", "owner", "public_safe_description", "challenges"}
REQUIRED_TOP_LEVEL_KEYS = {"pack_id", "name", "version", "created_at", "public_safe_description", "challenges"}
CHALLENGE_KEYS = {
    "benchmark_id",
    "challenge_id",
    "platform",
    "event",
    "category",
    "difficulty",
    "local_capable",
    "remote_required",
    "artifact_dir",
    "expected_timeout_sec",
    "tags",
    "public_notes",
    "private_notes_path",
}
REQUIRED_CHALLENGE_KEYS = {
    "benchmark_id",
    "challenge_id",
    "platform",
    "event",
    "category",
    "difficulty",
    "local_capable",
    "remote_required",
    "artifact_dir",
    "expected_timeout_sec",
    "tags",
    "public_notes",
}
FORBIDDEN_KEY_NAMES = {
    "flag",
    "flags",
    "flag_value",
    "expected_flag",
    "exploit",
    "exploit_code",
    "exploit_path",
    "raw_transcript",
    "raw_transcripts",
    "transcript",
    "raw_log",
    "raw_logs",
    "cookie",
    "cookies",
    "token",
    "tokens",
    "api_key",
    "authorization",
    "password",
    "secret",
    "private_key",
}
FORBIDDEN_KEY_PARTS = ("flag", "exploit", "raw_transcript", "raw_log", "cookie", "token", "api_key")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
SENSITIVE_TEXT_RE = re.compile(
    r"(DH\{[^}\n]{3,}\}|flag\{[^}\n]{3,}\}|Authorization\s*:\s*Bearer\s+\S+|Cookie\s*:|"
    r"sk-[A-Za-z0-9_-]{8,}|github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9_]{10,})",
    re.IGNORECASE,
)


def _yaml_scalar(value: object) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_yaml_scalar(item) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def _parse_scalar(value: str) -> object:
    value = value.strip()
    if value in {"", '""', "''", "null", "Null", "NULL"}:
        return "" if value in {"", '""', "''"} else None
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            return json.loads(value) if value.startswith('"') else value[1:-1]
        except json.JSONDecodeError:
            return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_simple_yaml(text: str) -> dict[str, object]:
    """Parse the small YAML subset used by benchmark pack manifests."""

    data: dict[str, object] = {}
    current_list_key: str | None = None
    current_item: dict[str, object] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" "):
            current_item = None
            current_list_key = None
            if stripped.endswith(":"):
                key = stripped[:-1].strip()
                data[key] = []
                current_list_key = key
                continue
            key, sep, value = stripped.partition(":")
            if not sep:
                raise ValueError(f"invalid manifest line: {raw_line}")
            data[key.strip()] = _parse_scalar(value)
            continue
        if stripped.startswith("- "):
            if current_list_key is None:
                raise ValueError(f"list item without a list key: {raw_line}")
            items = data.setdefault(current_list_key, [])
            if not isinstance(items, list):
                raise ValueError(f"{current_list_key} is not a list")
            current_item = {}
            items.append(current_item)
            rest = stripped[2:].strip()
            if rest:
                key, sep, value = rest.partition(":")
                if not sep:
                    raise ValueError(f"invalid list item line: {raw_line}")
                current_item[key.strip()] = _parse_scalar(value)
            continue
        if current_item is None:
            raise ValueError(f"nested value without a list item: {raw_line}")
        key, sep, value = stripped.partition(":")
        if not sep:
            raise ValueError(f"invalid nested manifest line: {raw_line}")
        current_item[key.strip()] = _parse_scalar(value)
    return data


def render_pack_manifest(manifest: dict[str, object]) -> str:
    lines = [
        f"pack_id: {_yaml_scalar(manifest.get('pack_id', ''))}",
        f"name: {_yaml_scalar(manifest.get('name', ''))}",
        f"version: {_yaml_scalar(manifest.get('version', 1))}",
        f"created_at: {_yaml_scalar(manifest.get('created_at', iso_now()))}",
        f"owner: {_yaml_scalar(manifest.get('owner', ''))}",
        f"public_safe_description: {_yaml_scalar(manifest.get('public_safe_description', ''))}",
        "challenges:",
    ]
    challenges = manifest.get("challenges")
    if isinstance(challenges, list):
        for challenge in challenges:
            if not isinstance(challenge, dict):
                continue
            first = True
            for key in [
                "benchmark_id",
                "challenge_id",
                "platform",
                "event",
                "category",
                "difficulty",
                "local_capable",
                "remote_required",
                "artifact_dir",
                "expected_timeout_sec",
                "tags",
                "public_notes",
                "private_notes_path",
            ]:
                if key not in challenge:
                    continue
                prefix = "  - " if first else "    "
                lines.append(f"{prefix}{key}: {_yaml_scalar(challenge.get(key))}")
                first = False
    return "\n".join(lines) + "\n"


def _manifest_path(path: str | Path) -> Path:
    candidate = resolve_path(path)
    if candidate.is_dir():
        return candidate / PACK_MANIFEST_NAME
    return candidate


def load_pack_manifest(path: str | Path) -> tuple[dict[str, object], Path]:
    manifest_path = _manifest_path(path)
    data = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
    return data, manifest_path


def _is_absolute_text(value: str) -> bool:
    return Path(value).expanduser().is_absolute() or bool(WINDOWS_ABSOLUTE_RE.match(value))


def _walk_manifest_safety(node: object, errors: list[str], prefix: str = "") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            lowered = key_text.lower()
            path = f"{prefix}.{key_text}" if prefix else key_text
            if lowered in FORBIDDEN_KEY_NAMES or any(part in lowered for part in FORBIDDEN_KEY_PARTS):
                errors.append(f"forbidden manifest key: {path}")
            _walk_manifest_safety(value, errors, path)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_manifest_safety(value, errors, f"{prefix}[{index}]")
    elif isinstance(node, str):
        if SENSITIVE_TEXT_RE.search(node):
            errors.append(f"sensitive-looking manifest value at {prefix or '<root>'}")
        if _is_absolute_text(node):
            errors.append(f"absolute path is not allowed in manifest at {prefix or '<root>'}")


def _relative_path_error(value: object, pack_root: Path, field: str, index: int) -> str | None:
    if not isinstance(value, str) or not value:
        return f"challenges[{index}].{field} must be a non-empty relative path"
    if _is_absolute_text(value):
        return f"challenges[{index}].{field} must not be an absolute path"
    resolved = (pack_root / value).resolve()
    if not is_relative_to(resolved, pack_root):
        return f"challenges[{index}].{field} escapes the private pack root"
    return None


def validate_pack_manifest(path: str | Path) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest, manifest_path = load_pack_manifest(path)
    except Exception as exc:
        return {"ok": False, "errors": [f"could not read manifest: {exc}"], "warnings": [], "challenge_count": 0}

    pack_root = manifest_path.parent.resolve()
    if is_inside_repo(pack_root):
        warnings.append("private benchmark pack root is inside the repo")
    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(manifest))
    errors.extend(f"missing top-level field: {key}" for key in missing)
    unknown = sorted(set(manifest) - TOP_LEVEL_KEYS)
    errors.extend(f"unknown top-level field: {key}" for key in unknown)
    _walk_manifest_safety(manifest, errors)

    challenges = manifest.get("challenges")
    if not isinstance(challenges, list):
        errors.append("challenges must be a list")
        challenge_count = 0
    else:
        challenge_count = len(challenges)
        for index, challenge in enumerate(challenges):
            if not isinstance(challenge, dict):
                errors.append(f"challenges[{index}] must be a mapping")
                continue
            missing_challenge = sorted(REQUIRED_CHALLENGE_KEYS - set(challenge))
            errors.extend(f"challenges[{index}] missing field: {key}" for key in missing_challenge)
            unknown_challenge = sorted(set(challenge) - CHALLENGE_KEYS)
            errors.extend(f"challenges[{index}] unknown field: {key}" for key in unknown_challenge)
            for field in ("artifact_dir", "private_notes_path"):
                if field in challenge and challenge.get(field):
                    error = _relative_path_error(challenge.get(field), pack_root, field, index)
                    if error:
                        errors.append(error)
            if "tags" in challenge and not isinstance(challenge.get("tags"), list):
                errors.append(f"challenges[{index}].tags must be a list")
            for boolean_field in ("local_capable", "remote_required"):
                if boolean_field in challenge and not isinstance(challenge.get(boolean_field), bool):
                    errors.append(f"challenges[{index}].{boolean_field} must be true or false")
            timeout = challenge.get("expected_timeout_sec")
            if "expected_timeout_sec" in challenge and not isinstance(timeout, int):
                errors.append(f"challenges[{index}].expected_timeout_sec must be an integer")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "challenge_count": challenge_count,
        "manifest_name": manifest_path.name,
        "pack_id": str(manifest.get("pack_id") or ""),
    }


def create_pack_skeleton(
    *,
    pack_id: str,
    name: str,
    output: str | Path | None = None,
    allow_repo_output: bool = False,
) -> dict[str, object]:
    pack_slug = slugify(pack_id, fallback="benchmark-pack", max_length=96)
    pack_dir = resolve_path(output) if output else private_benchmark_root() / pack_slug
    if is_inside_repo(pack_dir) and not allow_repo_output:
        raise ValueError("refusing to create private benchmark pack inside repo without --allow-repo-output")
    pack_dir.mkdir(parents=True, exist_ok=True)
    for child in ("artifacts", "results", "notes"):
        (pack_dir / child).mkdir(parents=True, exist_ok=True)
    manifest = {
        "pack_id": pack_id,
        "name": name,
        "version": 1,
        "created_at": iso_now(),
        "owner": "",
        "public_safe_description": "Private benchmark pack metadata. Keep raw artifacts outside the repo.",
        "challenges": [],
    }
    manifest_path = pack_dir / PACK_MANIFEST_NAME
    if manifest_path.exists():
        raise ValueError(f"manifest already exists: {manifest_path}")
    manifest_text = render_pack_manifest(manifest)
    manifest_path.write_text(manifest_text, encoding="utf-8")
    validation = validate_pack_manifest(manifest_path)
    if not validation["ok"]:
        raise ValueError("generated manifest failed validation: " + "; ".join(validation["errors"]))  # type: ignore[index]
    return {
        "pack_id": pack_id,
        "pack_dir": str(pack_dir),
        "manifest_path": str(manifest_path),
        "created_dirs": ["artifacts", "results", "notes"],
        "validation": validation,
    }


def _read_json_records(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return read_jsonl(path)
    data = json.loads(text)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("records", "results", "benchmark_results", "attempts"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data]
    return []


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


def _count_dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, (int, float)):
            counts[key] = max(0, int(item))
    return counts


def _source_record(record: dict[str, object]) -> dict[str, object]:
    public_record = record.get("public_record")
    if isinstance(public_record, dict):
        return public_record
    finalization = record.get("finalization")
    if isinstance(finalization, dict) and isinstance(finalization.get("public_record"), dict):
        return finalization["public_record"]  # type: ignore[return-value]
    return record


def sanitize_private_benchmark_result(record: dict[str, object]) -> dict[str, object]:
    source = _source_record(record)
    out: dict[str, object] = {}
    for key in ("benchmark_id", "category", "platform", "event", "status", "ai_usage_id"):
        value = source.get(key)
        if isinstance(value, str) and value:
            out[key] = value
    for key in ("attempt_index", "duration_sec", "time_to_flag_sec", "remote_wait_time_sec"):
        value = source.get(key)
        if isinstance(value, (int, float)):
            out[key] = _nonnegative_float(value) if key.endswith("_sec") else _nonnegative_int(value)
    if "attempt_index" not in out:
        out["attempt_index"] = 1
    for key in ("verifier_success", "verifier_flag_found"):
        if key in source:
            out[key] = bool(source.get(key))

    tool_counts = source.get("tool_counts") or source.get("tool_call_counts")
    counts = _count_dict(tool_counts)
    if counts:
        out["tool_counts"] = counts

    session_counts = source.get("session_counts")
    if isinstance(session_counts, dict):
        out["session_counts"] = {
            "session_count": _nonnegative_int(session_counts.get("session_count")),
            "closed_session_count": _nonnegative_int(session_counts.get("closed_session_count")),
        }
    else:
        session_metrics = source.get("session_metrics") if isinstance(source.get("session_metrics"), dict) else {}
        if session_metrics:
            out["session_counts"] = {
                "session_count": _nonnegative_int(session_metrics.get("session_count")),
                "closed_session_count": _nonnegative_int(session_metrics.get("closed_session_count")),
            }

    for target, candidates in {
        "browser_action_count": ("browser_action_count", "browser_actions_count"),
        "callback_hit_count": ("callback_hit_count",),
        "worker_action_count": ("worker_action_count",),
        "cleanup_bytes_saved": ("cleanup_bytes_saved",),
    }.items():
        for candidate in candidates:
            if isinstance(source.get(candidate), (int, float)):
                out[target] = _nonnegative_int(source.get(candidate))
                break

    for metric_key, source_key in {
        "browser_action_count": "browser_metrics",
        "callback_hit_count": "callback_metrics",
        "worker_action_count": "worker_metrics",
    }.items():
        if metric_key in out:
            continue
        metrics = source.get(source_key)
        if isinstance(metrics, dict):
            for candidate in (metric_key, metric_key.replace("action_count", "actions_count")):
                if isinstance(metrics.get(candidate), (int, float)):
                    out[metric_key] = _nonnegative_int(metrics.get(candidate))
                    break

    ai_usage = source.get("ai_usage") if isinstance(source.get("ai_usage"), dict) else {}
    ai_fields = {
        "ai_input_tokens": ("ai_input_tokens", "total_input_tokens"),
        "ai_output_tokens": ("ai_output_tokens", "total_output_tokens"),
        "ai_cache_read_tokens": ("ai_cache_read_tokens", "total_cache_read_tokens"),
        "ai_cache_creation_tokens": ("ai_cache_creation_tokens", "total_cache_creation_tokens"),
        "ai_cost_usd": ("ai_cost_usd", "total_cost_usd"),
    }
    for public_key, candidates in ai_fields.items():
        value: object = None
        for candidate in candidates:
            if isinstance(source.get(candidate), (int, float)):
                value = source.get(candidate)
                break
            if isinstance(ai_usage.get(candidate), (int, float)):
                value = ai_usage.get(candidate)
                break
        if value is not None:
            out[public_key] = _nonnegative_float(value) if public_key.endswith("_usd") else _nonnegative_int(value)

    if not out.get("benchmark_id"):
        raise ValueError("private result is missing benchmark_id")
    if not out.get("status"):
        raise ValueError(f"private result for {out.get('benchmark_id')} is missing status")
    errors = validate_public_record(out)
    if errors:
        raise ValueError("exported benchmark result is not public-safe: " + "; ".join(errors))
    return out


def export_private_benchmark_results(
    *,
    input_path: str | Path,
    output_path: str | Path | None = None,
    summary_output_path: str | Path | None = None,
) -> dict[str, object]:
    source_path = resolve_path(input_path)
    records = [sanitize_private_benchmark_result(record) for record in _read_json_records(source_path)]
    output = resolve_path(output_path) if output_path else public_benchmark_export_root() / f"{slugify(source_path.stem)}.jsonl"
    summary_output = (
        resolve_path(summary_output_path)
        if summary_output_path
        else output.with_suffix(".summary.json")
    )
    summary = summarize_benchmarks(records)
    for key in ("ai_input_tokens", "ai_output_tokens", "ai_cache_read_tokens", "ai_cache_creation_tokens"):
        summary[key] = sum(_nonnegative_int(record.get(key)) for record in records)
    summary["ai_cost_usd"] = round(sum(_nonnegative_float(record.get("ai_cost_usd")) for record in records), 6)
    summary_errors = validate_public_record(summary)
    if summary_errors:
        raise ValueError("exported benchmark summary is not public-safe: " + "; ".join(summary_errors))
    atomic_write_jsonl(output, records)
    atomic_write_json(summary_output, summary)
    return {
        "exported_count": len(records),
        "output_path": str(output),
        "summary_path": str(summary_output),
        "summary": summary,
    }


def _token_total(snapshot: dict[str, object]) -> int:
    if isinstance(snapshot.get("token_total"), (int, float)):
        return _nonnegative_int(snapshot.get("token_total"))
    ai_usage = snapshot.get("ai_usage") if isinstance(snapshot.get("ai_usage"), dict) else {}
    total = 0
    for key in (
        "ai_input_tokens",
        "ai_output_tokens",
        "ai_cache_read_tokens",
        "ai_cache_creation_tokens",
        "total_input_tokens",
        "total_output_tokens",
        "total_cache_read_tokens",
        "total_cache_creation_tokens",
    ):
        total += _nonnegative_int(snapshot.get(key))
        total += _nonnegative_int(ai_usage.get(key)) if isinstance(ai_usage, dict) else 0
    return total


def _ai_cost(snapshot: dict[str, object]) -> float:
    ai_usage = snapshot.get("ai_usage") if isinstance(snapshot.get("ai_usage"), dict) else {}
    return round(
        _nonnegative_float(snapshot.get("ai_cost_usd"))
        + _nonnegative_float(snapshot.get("total_cost_usd"))
        + (_nonnegative_float(ai_usage.get("total_cost_usd")) if isinstance(ai_usage, dict) else 0.0),
        6,
    )


def _group_rates(rows: object) -> dict[str, dict[str, object]]:
    if not isinstance(rows, dict):
        return {}
    result: dict[str, dict[str, object]] = {}
    for name, counts in rows.items():
        if not isinstance(counts, dict):
            continue
        attempts = sum(_nonnegative_int(value) for value in counts.values())
        solved = _nonnegative_int(counts.get("solved"))
        result[str(name)] = {"attempts": attempts, "solved": solved, "solve_rate": round((solved / attempts * 100.0), 1) if attempts else 0.0}
    return result


def _normalize_snapshot(path: Path) -> dict[str, object]:
    if path.suffix == ".jsonl":
        records = read_jsonl(path)
        summary = summarize_benchmarks(records)
        summary["token_total"] = sum(_token_total(record) for record in records)
        summary["ai_cost_usd"] = round(sum(_ai_cost(record) for record in records), 6)
        return summary
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("summary"), dict):
        data = data["summary"]
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        records = [item for item in data["records"] if isinstance(item, dict)]
        summary = summarize_benchmarks(records)
        summary["token_total"] = sum(_token_total(record) for record in records)
        summary["ai_cost_usd"] = round(sum(_ai_cost(record) for record in records), 6)
        return summary
    if isinstance(data, dict):
        normalized = dict(data)
        if "token_total" not in normalized:
            normalized["token_total"] = _token_total(normalized)
        if "ai_cost_usd" not in normalized:
            normalized["ai_cost_usd"] = _ai_cost(normalized)
        return normalized
    raise ValueError(f"unsupported benchmark snapshot format: {path}")


def _delta(after: object, before: object) -> float | None:
    if isinstance(after, (int, float)) and isinstance(before, (int, float)):
        return round(float(after) - float(before), 6)
    return None


def _dimension_delta(before_rows: object, after_rows: object) -> dict[str, dict[str, object]]:
    before = _group_rates(before_rows)
    after = _group_rates(after_rows)
    result: dict[str, dict[str, object]] = {}
    for name in sorted(set(before) | set(after)):
        b = before.get(name, {"attempts": 0, "solved": 0, "solve_rate": 0.0})
        a = after.get(name, {"attempts": 0, "solved": 0, "solve_rate": 0.0})
        result[name] = {
            "before_attempts": b["attempts"],
            "after_attempts": a["attempts"],
            "attempts_delta": int(a["attempts"]) - int(b["attempts"]),
            "before_solved": b["solved"],
            "after_solved": a["solved"],
            "solved_delta": int(a["solved"]) - int(b["solved"]),
            "solve_rate_delta": _delta(a["solve_rate"], b["solve_rate"]),
        }
    return result


def compare_benchmark_snapshots(
    *,
    before_path: str | Path,
    after_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    before_file = resolve_path(before_path)
    after_file = resolve_path(after_path)
    before = _normalize_snapshot(before_file)
    after = _normalize_snapshot(after_file)
    comparison = {
        "schema_version": 1,
        "created_at": iso_now(),
        "before_label": before_file.name,
        "after_label": after_file.name,
        "before": {
            "solve_rate": before.get("solve_rate"),
            "pass_at_1": before.get("pass_at_1"),
            "pass_at_3": before.get("pass_at_3"),
            "median_time_to_flag_sec": before.get("median_time_to_flag_sec"),
            "verifier_success_rate": before.get("verifier_success_rate"),
            "ai_cost_usd": _ai_cost(before),
            "token_total": _token_total(before),
        },
        "after": {
            "solve_rate": after.get("solve_rate"),
            "pass_at_1": after.get("pass_at_1"),
            "pass_at_3": after.get("pass_at_3"),
            "median_time_to_flag_sec": after.get("median_time_to_flag_sec"),
            "verifier_success_rate": after.get("verifier_success_rate"),
            "ai_cost_usd": _ai_cost(after),
            "token_total": _token_total(after),
        },
        "deltas": {
            "solve_rate_delta": _delta(after.get("solve_rate"), before.get("solve_rate")),
            "pass_at_1_delta": _delta(after.get("pass_at_1"), before.get("pass_at_1")),
            "pass_at_3_delta": _delta(after.get("pass_at_3"), before.get("pass_at_3")),
            "median_time_to_flag_delta": _delta(after.get("median_time_to_flag_sec"), before.get("median_time_to_flag_sec")),
            "verifier_success_delta": _delta(after.get("verifier_success_rate"), before.get("verifier_success_rate")),
            "ai_cost_delta": _delta(_ai_cost(after), _ai_cost(before)),
            "token_delta": _token_total(after) - _token_total(before),
        },
        "by_category_delta": _dimension_delta(before.get("by_category"), after.get("by_category")),
        "by_platform_event_delta": _dimension_delta(before.get("by_platform_event"), after.get("by_platform_event")),
    }
    errors = validate_public_record(comparison)
    if errors:
        raise ValueError("comparison report is not public-safe: " + "; ".join(errors))
    output = (
        resolve_path(output_path)
        if output_path
        else public_comparison_root()
        / f"{slugify(before_file.stem, fallback='before')}-vs-{slugify(after_file.stem, fallback='after')}.json"
    )
    atomic_write_json(output, comparison)
    return {"output_path": str(output), "comparison": comparison}
