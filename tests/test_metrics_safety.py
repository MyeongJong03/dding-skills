from __future__ import annotations

import json


def _summary_records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_public_metrics_are_safe_and_deduplicated(temp_ctf_env, run_cli) -> None:
    summary = temp_ctf_env.solver_repo / "metrics" / "summary.jsonl"
    dashboard = temp_ctf_env.solver_repo / "metrics" / "dashboard.md"

    run_cli(
        [
            "scripts/update_metrics.py",
            "--run-id",
            "RUN-METRICS-1",
            "--status",
            "solved",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--challenge-name",
            "Private Challenge Name",
            "--category",
            "web",
            "--flag",
            "DH{dummy_public_metrics_must_not_include}",
            "--writeup-generated",
            "--exploit-included",
        ]
    )
    records = _summary_records(summary)
    assert len(records) == 1
    record = records[0]
    assert record["run_id"] == "RUN-METRICS-1"
    rendered = json.dumps(record, sort_keys=True)
    assert "DH{" not in rendered
    assert "exploit_code" not in rendered
    assert "raw_transcript" not in rendered
    assert str(temp_ctf_env.base) not in rendered
    assert "challenge_name" not in record
    assert "Private Challenge Name" not in rendered
    assert dashboard.is_file()

    run_cli(
        [
            "scripts/update_metrics.py",
            "--run-id",
            "RUN-METRICS-1",
            "--status",
            "solved",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--category",
            "web",
        ]
    )
    assert len(_summary_records(summary)) == 1

    run_cli(
        [
            "scripts/update_metrics.py",
            "--run-id",
            "RUN-METRICS-1",
            "--status",
            "manual_stop",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--category",
            "web",
            "--replace",
        ]
    )
    replaced = _summary_records(summary)
    assert len(replaced) == 1
    assert replaced[0]["status"] == "manual_stop"

    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout
