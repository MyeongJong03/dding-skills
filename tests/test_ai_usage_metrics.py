from __future__ import annotations

import json

from conftest import parse_json_output


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_ai_usage_record_private_detail_and_public_aggregate(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/ai_usage_record.py",
                "--run-id",
                "RUN-AI-1",
                "--provider",
                "codex",
                "--model",
                "gpt-example",
                "--input-tokens",
                "1000",
                "--output-tokens",
                "200",
                "--cache-read-tokens",
                "50",
                "--cache-creation-tokens",
                "25",
                "--cost-usd",
                "0.125",
                "--duration-sec",
                "42",
                "--category",
                "web",
                "--platform",
                "dreamhack",
                "--event",
                "dreamhackWargame",
                "--status",
                "solved",
                "--json",
            ]
        )
    )
    assert result["record"]["ai_usage_id"].startswith("aiu-")
    private_records = _records(temp_ctf_env.ai_usage / "usage.jsonl")
    assert private_records[0]["run_id"] == "RUN-AI-1"

    public_records = _records(temp_ctf_env.solver_repo / "metrics" / "ai_usage_summary.jsonl")
    assert len(public_records) == 1
    public = public_records[0]
    assert public["total_input_tokens"] == 1000
    assert public["total_output_tokens"] == 200
    assert public["total_cost_usd"] == 0.125
    rendered_public = json.dumps(public, sort_keys=True)
    assert "RUN-AI-1" not in rendered_public
    assert str(temp_ctf_env.base) not in rendered_public
    assert "DH{" not in rendered_public


def test_ai_usage_import_filters_account_metadata_and_reports(temp_ctf_env, run_cli) -> None:
    usage_input = temp_ctf_env.base / "redacted-usage-fixture.json"
    sensitive_keys = {
        "".join(("oauth", "Account")): {"id": "dummy"},
        "".join(("email", "Address")): "tester@example.invalid",
        "".join(("account", "Uuid")): "00000000-0000-0000-0000-000000000000",
        "".join(("organization", "Uuid")): "11111111-1111-1111-1111-111111111111",
        "".join(("referral", "_", "link")): "https://example.invalid/ref",
    }
    usage_input.write_text(
        json.dumps(
            {
                **sensitive_keys,
                "projects": [
                    {
                        "sessions": [
                            {
                                "run_id": "RUN-AI-IMPORT",
                                "provider": "claude",
                                "model": "claude-example",
                                "usage": {
                                    "input_tokens": 1500,
                                    "output_tokens": 300,
                                    "cache_read_input_tokens": 70,
                                    "cache_creation_input_tokens": 30,
                                },
                                "costUSD": 0.25,
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = parse_json_output(
        run_cli(
            [
                "scripts/ai_usage_import.py",
                "--input",
                str(usage_input),
                "--source",
                "claude-json",
                "--json",
            ]
        )
    )
    assert result["imported_count"] == 1
    rendered = json.dumps(result, sort_keys=True)
    for key in sensitive_keys:
        assert key not in rendered
    assert "tester@example.invalid" not in rendered

    public_rendered = (temp_ctf_env.solver_repo / "metrics" / "ai_usage_summary.jsonl").read_text(encoding="utf-8")
    for key in sensitive_keys:
        assert key not in public_rendered
    assert "tester@example.invalid" not in public_rendered

    report = parse_json_output(run_cli(["scripts/ai_usage_report.py", "--json"]))
    assert report["summary"]["total_input_tokens"] >= 1500
    dashboard = temp_ctf_env.solver_repo / "metrics" / "ai_usage_dashboard.md"
    assert "AI Usage Dashboard" in dashboard.read_text(encoding="utf-8")

