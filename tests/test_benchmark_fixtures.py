from __future__ import annotations

import json
from pathlib import Path

from conftest import REPO_ROOT, parse_json_output
from ctf_solver_core.performance import validate_public_metrics_files
from ctf_solver_core.schemas import CATEGORIES, validate_public_record


BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "smoke"
AI_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "ai_usage"
BENCHMARK_RESULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "benchmark_results" / "public_safe_results.jsonl"

ALLOWED_BENCHMARK_KEYS = {
    "benchmark_id",
    "category",
    "platform",
    "event",
    "local_capable",
    "remote_required",
    "difficulty",
    "timeout_sec",
    "tags",
    "notes",
}
MINIMUM_CATEGORIES = {"web", "pwn", "crypto", "rev", "forensics", "misc", "osint"}
SENSITIVE_METADATA_KEY_PARTS = [
    ("oauth", "Account"),
    ("email", "Address"),
    ("account", "Uuid"),
    ("organization", "Uuid"),
    ("referral", "_", "link"),
]


def _parse_smoke_yaml(path: Path) -> dict[str, object]:
    record: dict[str, object] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value in {"true", "false"}:
            parsed: object = value == "true"
        elif value.isdigit():
            parsed = int(value)
        elif value.startswith("[") and value.endswith("]"):
            parsed = [item.strip() for item in value[1:-1].split(",") if item.strip()]
        else:
            parsed = value.strip("\"'")
        record[key.strip()] = parsed
    return record


def _jsonl_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _public_metrics_text(root: Path) -> str:
    chunks: list[str] = []
    for path in sorted((root / "metrics").glob("*")):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _assert_no_private_or_sensitive_public_text(text: str, temp_root: Path) -> None:
    assert "DH{" not in text
    assert str(temp_root) not in text
    assert "/Users/" not in text
    assert "Authori" + "zation:" not in text
    assert "Cook" + "ie:" not in text
    for parts in SENSITIVE_METADATA_KEY_PARTS:
        assert "".join(parts) not in text


def test_public_smoke_benchmark_definitions_are_safe() -> None:
    records = [_parse_smoke_yaml(path) for path in sorted(BENCHMARK_DIR.glob("*.yaml"))]
    assert records
    categories = {str(record["category"]) for record in records}
    assert MINIMUM_CATEGORIES.issubset(categories)

    for record in records:
        assert set(record) == ALLOWED_BENCHMARK_KEYS
        assert record["category"] in CATEGORIES
        assert record["platform"] == "smoke"
        assert record["event"] == "smoke"
        assert record["local_capable"] is True
        assert record["remote_required"] is False
        assert isinstance(record["timeout_sec"], int)
        assert record["timeout_sec"] > 0
        assert isinstance(record["tags"], list)
        assert not validate_public_record(record)


def test_fixture_reports_and_ai_usage_import_are_public_safe(temp_ctf_env, run_cli) -> None:
    for record in _jsonl_records(BENCHMARK_RESULT_FIXTURE):
        assert not validate_public_record(record)
        args = [
            "scripts/benchmark_record_result.py",
            "--benchmark-id",
            str(record["benchmark_id"]),
            "--run-id",
            str(record["run_id"]),
            "--status",
            str(record["status"]),
            "--attempt-index",
            str(record["attempt_index"]),
            "--duration-sec",
            str(record["duration_sec"]),
            "--verifier-success",
            "true" if record["verifier_success"] else "false",
            "--verifier-flag-found",
            "true" if record["verifier_flag_found"] else "false",
            "--platform",
            str(record["platform"]),
            "--event",
            str(record["event"]),
            "--category",
            str(record["category"]),
        ]
        if "time_to_flag_sec" in record:
            args.extend(["--time-to-flag-sec", str(record["time_to_flag_sec"])])
        run_cli(args)

    benchmark_report = parse_json_output(run_cli(["scripts/benchmark_report.py", "--json"]))
    benchmark_summary = benchmark_report["summary"]
    assert benchmark_summary["benchmark_count"] == 8
    assert benchmark_summary["pass_at_1"] == 37.5
    assert benchmark_summary["pass_at_3"] == 62.5
    assert benchmark_summary["solve_rate"] == 62.5
    benchmark_dashboard = (temp_ctf_env.solver_repo / "metrics" / "benchmark_dashboard.md").read_text(
        encoding="utf-8"
    )
    assert "pass@1" in benchmark_dashboard
    assert "pass@3" in benchmark_dashboard
    assert "Solve rate" in benchmark_dashboard

    claude_import = parse_json_output(
        run_cli(
            [
                "scripts/ai_usage_import.py",
                "--input",
                str(AI_FIXTURE_DIR / "claude_usage_redacted.json"),
                "--source",
                "claude-json",
                "--json",
            ]
        )
    )
    codex_import = parse_json_output(
        run_cli(
            [
                "scripts/ai_usage_import.py",
                "--input",
                str(AI_FIXTURE_DIR / "codex_usage_manual.json"),
                "--source",
                "manual-json",
                "--json",
            ]
        )
    )
    assert claude_import["imported_count"] == 1
    assert codex_import["imported_count"] == 2

    augmented = json.loads((AI_FIXTURE_DIR / "claude_usage_redacted.json").read_text(encoding="utf-8"))
    for parts in SENSITIVE_METADATA_KEY_PARTS:
        augmented["".join(parts)] = "redacted-dummy-metadata"
    augmented_path = temp_ctf_env.base / "augmented-ai-usage.json"
    augmented_path.write_text(json.dumps(augmented), encoding="utf-8")
    augmented_import = parse_json_output(
        run_cli(
            [
                "scripts/ai_usage_import.py",
                "--input",
                str(augmented_path),
                "--source",
                "claude-json",
                "--json",
            ]
        )
    )
    rendered_augmented = json.dumps(augmented_import, sort_keys=True)
    for parts in SENSITIVE_METADATA_KEY_PARTS:
        assert "".join(parts) not in rendered_augmented
    assert "redacted-dummy-metadata" not in rendered_augmented

    ai_report = parse_json_output(run_cli(["scripts/ai_usage_report.py", "--json"]))
    ai_summary = ai_report["summary"]
    assert ai_summary["total_input_tokens"] == 3700
    assert ai_summary["total_output_tokens"] == 760
    assert ai_summary["total_cache_read_tokens"] == 200
    assert ai_summary["total_cache_creation_tokens"] == 50
    assert ai_summary["by_provider"]["claude"]["run_count"] == 2
    assert ai_summary["by_provider"]["codex"]["run_count"] == 1
    assert ai_summary["by_provider"]["manual"]["run_count"] == 1
    ai_dashboard = (temp_ctf_env.solver_repo / "metrics" / "ai_usage_dashboard.md").read_text(encoding="utf-8")
    assert "Input tokens" in ai_dashboard
    assert "Output tokens" in ai_dashboard

    performance_report = parse_json_output(run_cli(["scripts/performance_report.py", "--json"]))
    performance_summary = performance_report["summary"]
    assert performance_summary["total_attempts"] == 8
    assert performance_summary["solve_rate"] == 62.5
    assert performance_summary["ai_usage"]["total_input_tokens"] == 3700
    assert performance_summary["ai_usage"]["total_output_tokens"] == 760
    performance_dashboard = (temp_ctf_env.solver_repo / "metrics" / "performance_dashboard.md").read_text(
        encoding="utf-8"
    )
    assert "Solve rate" in performance_dashboard
    assert "AI input tokens" in performance_dashboard

    assert validate_public_metrics_files(temp_ctf_env.solver_repo / "metrics") == []
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout
    _assert_no_private_or_sensitive_public_text(_public_metrics_text(temp_ctf_env.solver_repo), temp_ctf_env.base)
