from __future__ import annotations

import json

from conftest import parse_json_output


def test_performance_report_aggregates_public_safe_metrics(temp_ctf_env, run_cli) -> None:
    run_cli(
        [
            "scripts/update_metrics.py",
            "--run-id",
            "RUN-PERF-1",
            "--status",
            "solved",
            "--platform",
            "dreamhack",
            "--event",
            "dreamhackWargame",
            "--category",
            "web",
            "--time-to-flag-sec",
            "210",
            "--verifier-success",
            "--verifier-flag-found",
            "--tool-call-counts-json",
            json.dumps({"http_request": 3, "python_exec": 2}),
            "--session-count",
            "1",
            "--closed-session-count",
            "1",
            "--browser-actions-count",
            "4",
            "--callback-hit-count",
            "2",
            "--cleanup-bytes-saved",
            "4096",
            "--remote-wait-time-sec",
            "30",
            "--local-prework-time-sec",
            "120",
        ]
    )
    run_cli(
        [
            "scripts/benchmark_record_result.py",
            "--benchmark-id",
            "perf-demo-001",
            "--run-id",
            "RUN-PERF-1",
            "--status",
            "solved",
            "--attempt-index",
            "1",
            "--time-to-flag-sec",
            "210",
            "--verifier-success",
            "true",
            "--verifier-flag-found",
            "true",
            "--platform",
            "dreamhack",
            "--event",
            "dreamhackWargame",
            "--category",
            "web",
        ]
    )
    run_cli(
        [
            "scripts/ai_usage_record.py",
            "--run-id",
            "RUN-PERF-1",
            "--provider",
            "codex",
            "--model",
            "gpt-example",
            "--input-tokens",
            "2000",
            "--output-tokens",
            "500",
            "--cost-usd",
            "0.5",
        ]
    )

    report = parse_json_output(run_cli(["scripts/performance_report.py", "--json"]))
    summary = report["summary"]
    assert summary["total_attempts"] == 1
    assert summary["solve_rate"] == 100.0
    assert summary["verifier_success_rate"] == 100.0
    assert summary["median_time_to_flag_sec"] == 210.0
    assert summary["tool_usage_top"]["http_request"] == 3
    assert summary["ai_usage"]["total_input_tokens"] == 2000
    assert summary["ai_usage"]["total_output_tokens"] == 500
    assert summary["ai_usage"]["total_cost_usd"] == 0.5

    dashboard = temp_ctf_env.solver_repo / "metrics" / "performance_dashboard.md"
    text = dashboard.read_text(encoding="utf-8")
    assert "Solve rate" in text
    assert "Verifier success rate" in text
    assert "AI input tokens" in text
    assert "AI total cost USD" in text

    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout
    secret = run_cli(["scripts/secret_scan.py", "--strict"])
    assert "secret scan clean" in secret.stdout

