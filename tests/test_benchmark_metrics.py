from __future__ import annotations

import json

from conftest import parse_json_output


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_benchmark_init_record_dedupe_replace_and_report(temp_ctf_env, run_cli) -> None:
    init = run_cli(
        [
            "scripts/benchmark_init.py",
            "--benchmark-id",
            "demo-web-001",
            "--platform",
            "dreamhack",
            "--event",
            "dreamhackWargame",
            "--category",
            "web",
            "--local-capable",
            "true",
            "--remote-required",
            "true",
            "--timeout-sec",
            "1800",
            "--notes",
            "public safe fixture",
            "--json",
        ]
    )
    init_data = parse_json_output(init)
    definition_path = temp_ctf_env.solver_repo / "config" / "benchmarks" / "demo-web-001.json"
    assert definition_path.is_file()
    rendered_definition = json.dumps(init_data["definition"], sort_keys=True)
    assert "DH{" not in rendered_definition
    assert str(temp_ctf_env.base) not in rendered_definition

    summary = temp_ctf_env.solver_repo / "metrics" / "benchmark_summary.jsonl"
    run_cli(
        [
            "scripts/benchmark_record_result.py",
            "--benchmark-id",
            "demo-web-001",
            "--run-id",
            "RUN-BENCH-1",
            "--status",
            "solved",
            "--attempt-index",
            "1",
            "--duration-sec",
            "120",
            "--time-to-flag-sec",
            "100",
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
    assert len(_records(summary)) == 1

    duplicate = parse_json_output(
        run_cli(
            [
                "scripts/benchmark_record_result.py",
                "--benchmark-id",
                "demo-web-001",
                "--run-id",
                "RUN-BENCH-1",
                "--status",
                "solved",
                "--attempt-index",
                "1",
                "--json",
            ]
        )
    )
    assert duplicate["duplicate_skipped"] is True
    assert len(_records(summary)) == 1

    replaced = parse_json_output(
        run_cli(
            [
                "scripts/benchmark_record_result.py",
                "--benchmark-id",
                "demo-web-001",
                "--run-id",
                "RUN-BENCH-1",
                "--status",
                "solved",
                "--attempt-index",
                "1",
                "--duration-sec",
                "130",
                "--time-to-flag-sec",
                "110",
                "--replace",
                "--json",
            ]
        )
    )
    assert replaced["replaced_existing"] is True
    assert _records(summary)[0]["time_to_flag_sec"] == 110.0

    run_cli(
        [
            "scripts/benchmark_record_result.py",
            "--benchmark-id",
            "demo-web-002",
            "--run-id",
            "RUN-BENCH-2",
            "--status",
            "solved",
            "--attempt-index",
            "3",
            "--time-to-flag-sec",
            "300",
            "--category",
            "crypto",
            "--platform",
            "dreamhack",
            "--event",
            "dreamhackWargame",
        ]
    )
    run_cli(
        [
            "scripts/benchmark_record_result.py",
            "--benchmark-id",
            "demo-web-003",
            "--run-id",
            "RUN-BENCH-3",
            "--status",
            "abandoned",
            "--attempt-index",
            "1",
            "--category",
            "pwn",
            "--platform",
            "ctf",
            "--event",
            "local",
        ]
    )

    report = parse_json_output(run_cli(["scripts/benchmark_report.py", "--json"]))
    report_summary = report["summary"]
    assert report_summary["benchmark_count"] == 3
    assert report_summary["pass_at_1"] == 33.3
    assert report_summary["pass_at_3"] == 66.7
    assert report_summary["solve_rate"] == 66.7
    dashboard = temp_ctf_env.solver_repo / "metrics" / "benchmark_dashboard.md"
    assert "pass@1" in dashboard.read_text(encoding="utf-8")
    assert "By Category" in dashboard.read_text(encoding="utf-8")
