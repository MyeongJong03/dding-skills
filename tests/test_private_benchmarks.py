from __future__ import annotations

import json
from pathlib import Path

from conftest import REPO_ROOT, parse_json_output
from ctf_solver_core.schemas import validate_public_record


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _clean_manifest() -> str:
    return """pack_id: "private-core"
name: "Private Core Pack"
version: 1
created_at: "2026-05-12T00:00:00Z"
owner: ""
public_safe_description: "Private pack metadata only."
challenges:
  - benchmark_id: "private-web-001"
    challenge_id: "private-web-fixture"
    platform: "dreamhack"
    event: "dreamhackWargame"
    category: "web"
    difficulty: "medium"
    local_capable: true
    remote_required: true
    artifact_dir: "artifacts/private-web-001"
    expected_timeout_sec: 1800
    tags: ["web", "callback"]
    public_notes: "Public-safe summary."
    private_notes_path: "notes/private-web-001.md"
"""


def test_benchmark_pack_init_creates_private_pack(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/benchmark_pack_init.py",
                "--pack-id",
                "private-core",
                "--name",
                "Private Core Pack",
                "--json",
            ]
        )
    )
    pack_dir = temp_ctf_env.private_benchmarks / "private-core"
    assert Path(result["pack_dir"]) == pack_dir
    assert (pack_dir / "benchmark_pack.yaml").is_file()
    assert (pack_dir / "artifacts").is_dir()
    assert (pack_dir / "results").is_dir()
    assert (pack_dir / "notes").is_dir()
    assert result["validation"]["ok"] is True


def test_benchmark_pack_init_refuses_repo_output(temp_ctf_env, run_cli) -> None:
    result = run_cli(
        [
            "scripts/benchmark_pack_init.py",
            "--pack-id",
            "repo-private-pack",
            "--name",
            "Repo Private Pack",
            "--output",
            str(temp_ctf_env.solver_repo / "repo-private-pack"),
        ],
        check=False,
    )
    assert result.returncode != 0
    assert "inside repo" in result.stderr


def test_benchmark_pack_validate_passes_clean_manifest(temp_ctf_env, run_cli) -> None:
    pack_dir = temp_ctf_env.private_benchmarks / "clean-pack"
    pack_dir.mkdir(parents=True)
    manifest = pack_dir / "benchmark_pack.yaml"
    manifest.write_text(_clean_manifest(), encoding="utf-8")

    result = parse_json_output(run_cli(["scripts/benchmark_pack_validate.py", str(manifest), "--json"]))
    assert result["ok"] is True
    assert result["challenge_count"] == 1


def test_benchmark_pack_validate_rejects_sensitive_manifest(temp_ctf_env, run_cli) -> None:
    pack_dir = temp_ctf_env.private_benchmarks / "bad-pack"
    pack_dir.mkdir(parents=True)
    manifest = pack_dir / "benchmark_pack.yaml"
    manifest.write_text(
        _clean_manifest()
        + "\nflag_value: REDACTED_FLAG\n"
        + "auth_token: redacted-token-placeholder\n"
        + 'private_absolute_path: "/tmp/private-benchmark-artifact"\n',
        encoding="utf-8",
    )

    result = parse_json_output(run_cli(["scripts/benchmark_pack_validate.py", str(manifest), "--json"], check=False))
    assert result["ok"] is False
    rendered = json.dumps(result, sort_keys=True)
    assert "forbidden manifest key" in rendered
    assert "absolute path" in rendered


def test_benchmark_export_public_strips_private_fields(temp_ctf_env, run_cli) -> None:
    private_result = temp_ctf_env.private_benchmark_runs / "private-results.json"
    private_result.write_text(
        json.dumps(
            {
                "benchmark_id": "private-web-001",
                "category": "web",
                "platform": "dreamhack",
                "event": "dreamhackWargame",
                "status": "solved",
                "attempt_index": 1,
                "duration_sec": 125,
                "time_to_flag_sec": 100,
                "verifier_success": True,
                "verifier_flag_found": True,
                "tool_call_counts": {"http_request": 3},
                "session_metrics": {"session_count": 1, "closed_session_count": 1},
                "browser_metrics": {"browser_actions_count": 2},
                "callback_metrics": {"callback_hit_count": 1},
                "ai_input_tokens": 100,
                "ai_output_tokens": 20,
                "ai_cost_usd": 0.01,
                "flag": "REDACTED_FLAG",
                "exploit_code": "print('redacted exploit')",
                "raw_transcript": "raw solver output",
                "artifact_path": str(temp_ctf_env.base),
                "challenge_description": "private challenge text",
            }
        ),
        encoding="utf-8",
    )
    output = temp_ctf_env.solver_repo / "metrics" / "benchmark_exports" / "private-results.jsonl"
    result = parse_json_output(
        run_cli(
            [
                "scripts/benchmark_export_public.py",
                "--input",
                str(private_result),
                "--output",
                str(output),
                "--json",
            ]
        )
    )
    records = _jsonl(output)
    assert result["exported_count"] == 1
    assert records[0]["benchmark_id"] == "private-web-001"
    rendered = output.read_text(encoding="utf-8") + Path(result["summary_path"]).read_text(encoding="utf-8")
    assert "REDACTED_FLAG" not in rendered
    assert "exploit" not in rendered
    assert "raw solver output" not in rendered
    assert str(temp_ctf_env.base) not in rendered
    assert validate_public_record(records[0]) == []


def test_benchmark_compare_computes_public_safe_deltas(temp_ctf_env, run_cli) -> None:
    before = temp_ctf_env.base / "before.jsonl"
    after = temp_ctf_env.base / "after.jsonl"
    before.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "benchmark_id": "bench-web",
                        "category": "web",
                        "platform": "dreamhack",
                        "event": "dreamhackWargame",
                        "status": "solved",
                        "attempt_index": 1,
                        "time_to_flag_sec": 100,
                        "verifier_success": True,
                        "ai_input_tokens": 100,
                        "ai_output_tokens": 50,
                        "ai_cost_usd": 0.1,
                    }
                ),
                json.dumps(
                    {
                        "benchmark_id": "bench-crypto",
                        "category": "crypto",
                        "platform": "dreamhack",
                        "event": "dreamhackWargame",
                        "status": "failed",
                        "attempt_index": 1,
                        "verifier_success": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    after.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "benchmark_id": "bench-web",
                        "category": "web",
                        "platform": "dreamhack",
                        "event": "dreamhackWargame",
                        "status": "solved",
                        "attempt_index": 1,
                        "time_to_flag_sec": 100,
                        "verifier_success": True,
                        "ai_input_tokens": 100,
                        "ai_output_tokens": 50,
                        "ai_cost_usd": 0.1,
                    }
                ),
                json.dumps(
                    {
                        "benchmark_id": "bench-crypto",
                        "category": "crypto",
                        "platform": "dreamhack",
                        "event": "dreamhackWargame",
                        "status": "solved",
                        "attempt_index": 3,
                        "time_to_flag_sec": 200,
                        "verifier_success": True,
                        "ai_input_tokens": 300,
                        "ai_output_tokens": 100,
                        "ai_cost_usd": 0.3,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = temp_ctf_env.solver_repo / "metrics" / "comparisons" / "feature-change.json"
    result = parse_json_output(
        run_cli(
            [
                "scripts/benchmark_compare.py",
                "--before",
                str(before),
                "--after",
                str(after),
                "--output",
                str(output),
                "--json",
            ]
        )
    )
    comparison = result["comparison"]
    assert comparison["deltas"]["solve_rate_delta"] == 50.0
    assert comparison["deltas"]["pass_at_1_delta"] == 0.0
    assert comparison["deltas"]["pass_at_3_delta"] == 50.0
    assert comparison["deltas"]["median_time_to_flag_delta"] == 50.0
    assert comparison["deltas"]["verifier_success_delta"] == 50.0
    assert comparison["deltas"]["ai_cost_delta"] == 0.3
    assert comparison["deltas"]["token_delta"] == 400
    assert comparison["by_category_delta"]["crypto"]["solve_rate_delta"] == 100.0
    assert validate_public_record(json.loads(output.read_text(encoding="utf-8"))) == []
    assert str(temp_ctf_env.base) not in output.read_text(encoding="utf-8")


def test_private_benchmark_doctor_and_secret_scan_pass(temp_ctf_env, run_cli) -> None:
    ctf_dir = temp_ctf_env.home / "CTF"
    ctf_dir.mkdir(parents=True)
    instructions = "# CTF\n\n## Challenge Lifecycle Rules\n\npresent\n"
    (ctf_dir / "CLAUDE.md").write_text(instructions, encoding="utf-8")
    (ctf_dir / "AGENTS.md").write_text(instructions, encoding="utf-8")
    skill = temp_ctf_env.home / ".agents" / "skills" / "ctf-personal"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# ctf-personal\n", encoding="utf-8")

    doctor = run_cli(["scripts/doctor.py"])
    assert "Hard failures: 0" in doctor.stdout

    strict = run_cli(["scripts/secret_scan.py", "--strict"])
    assert "OK: secret scan clean" in strict.stdout
    include_untracked = run_cli(["scripts/secret_scan.py", "--strict", "--include-untracked"])
    assert "OK: secret scan clean" in include_untracked.stdout

