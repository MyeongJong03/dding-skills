from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from conftest import parse_json_output


@pytest.fixture(autouse=True)
def _stop_session_daemon(run_cli):
    yield
    run_cli(["scripts/session_daemon.py", "stop"], check=False)


def _init_run(run_cli, name: str = "Verifier Regression") -> tuple[str, Path]:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                name,
                "--category",
                "misc",
                "--json",
            ]
        )
    )
    return str(init["run_id"]), Path(str(init["run_dir"]))


def _summary_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_command_success_saves_redacted_verifier(temp_ctf_env, run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Command Success")
    result = parse_json_output(
        run_cli(
            [
                "scripts/verify_run.py",
                "--run-dir",
                str(run_dir),
                "--mode",
                "command",
                "--command",
                f"{sys.executable} -c \"print('FLAG{{dummy}}')\"",
                "--flag-regex",
                r"FLAG\{[^}]+\}",
                "--local",
                "--json",
            ]
        )
    )
    assert result["success"] is True
    assert result["flag_found"] is True
    assert result["target"] == "local"
    assert "FLAG{dummy}" not in str(result["output_preview"])

    saved = json.loads((run_dir / "verifier.json").read_text(encoding="utf-8"))
    assert saved["success"] is True
    assert saved["flag_found"] is True
    assert "FLAG{dummy}" not in json.dumps(saved)

    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout


def test_command_failure(run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Command Failure")
    result = parse_json_output(
        run_cli(
            [
                "scripts/verify_run.py",
                "--run-dir",
                str(run_dir),
                "--mode",
                "command",
                "--command",
                f"{sys.executable} -c \"print('no flag here')\"",
                "--flag-regex",
                r"FLAG\{[^}]+\}",
                "--local",
                "--json",
            ],
            check=False,
        )
    )
    assert result["success"] is False
    assert result["flag_found"] is False


def test_retry_succeeds_on_second_attempt(run_cli, tmp_path: Path) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Retry")
    state = tmp_path / "state.txt"
    script = tmp_path / "flaky.py"
    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"state = Path({str(state)!r})",
                "count = int(state.read_text() or '0') if state.exists() else 0",
                "state.write_text(str(count + 1))",
                "if count == 0:",
                "    print('not yet')",
                "    raise SystemExit(1)",
                "print('OK second attempt')",
            ]
        ),
        encoding="utf-8",
    )
    result = parse_json_output(
        run_cli(
            [
                "scripts/verify_run.py",
                "--run-dir",
                str(run_dir),
                "--mode",
                "command",
                "--command",
                f"{sys.executable} {script}",
                "--success-regex",
                "OK second",
                "--retries",
                "1",
                "--local",
                "--json",
            ]
        )
    )
    assert result["success"] is True
    assert result["attempts"] == 2


def test_timeout_records_error(run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Timeout")
    result = parse_json_output(
        run_cli(
            [
                "scripts/verify_run.py",
                "--run-dir",
                str(run_dir),
                "--mode",
                "command",
                "--command",
                f"{sys.executable} -c \"import time; time.sleep(2)\"",
                "--timeout-sec",
                "1",
                "--success-regex",
                "never",
                "--local",
                "--json",
            ],
            check=False,
        )
    )
    assert result["success"] is False
    assert any("timeout after 1s" in item for item in result["errors"])


def test_manual_evidence(run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Manual")
    result = parse_json_output(
        run_cli(
            [
                "scripts/verify_run.py",
                "--run-dir",
                str(run_dir),
                "--mode",
                "manual",
                "--evidence-text",
                "remote returned FLAG{dummy}",
                "--flag-regex",
                r"FLAG\{[^}]+\}",
                "--remote",
                "--json",
            ]
        )
    )
    assert result["success"] is True
    assert result["flag_found"] is True
    assert result["target"] == "remote"
    assert "FLAG{dummy}" not in json.dumps(result)


def test_session_mode_expect(run_cli) -> None:
    run_id, run_dir = _init_run(run_cli, "Verifier Session")
    started = parse_json_output(run_cli(["scripts/session_start.py", "shell", "--run-id", run_id, "--json"]))
    session_id = str(started["session"]["session_id"])
    try:
        result = parse_json_output(
            run_cli(
                [
                    "scripts/verify_run.py",
                    "--run-dir",
                    str(run_dir),
                    "--mode",
                    "session",
                    "--session-id",
                    session_id,
                    "--session-input",
                    "echo SESSION_OK",
                    "--expect",
                    "SESSION_OK",
                    "--timeout-sec",
                    "2",
                    "--local",
                    "--json",
                ]
            )
        )
        assert result["success"] is True
        assert result["attempts"] == 1
    finally:
        run_cli(["scripts/session_close.py", session_id, "--json"], check=False)


def test_finalize_reads_verifier_summary(run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Finalize")
    run_cli(
        [
            "scripts/verify_run.py",
            "--run-dir",
            str(run_dir),
            "--mode",
            "manual",
            "--evidence-text",
            "verified",
            "--success-regex",
            "verified",
            "--local",
            "--json",
        ]
    )
    finalized = parse_json_output(
        run_cli(["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "solved"])
    )
    assert finalized["verifier"]["success"] is True
    final_record = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
    assert final_record["verifier_success"] is True
    assert final_record["verifier_target"] == "local"


def test_require_verifier_blocks_unverified_solved(run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Required")
    result = run_cli(
        [
            "scripts/challenge_finalize.py",
            "--run-dir",
            str(run_dir),
            "--status",
            "solved",
            "--require-verifier",
        ],
        check=False,
    )
    assert result.returncode != 0
    assert "without successful verifier" in result.stderr


def test_metrics_include_public_safe_verifier_summary(temp_ctf_env, run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Metrics")
    run_cli(
        [
            "scripts/verify_run.py",
            "--run-dir",
            str(run_dir),
            "--mode",
            "manual",
            "--evidence-text",
            "FLAG{dummy}",
            "--flag-regex",
            r"FLAG\{[^}]+\}",
            "--remote",
            "--json",
        ]
    )
    run_cli(["scripts/update_metrics.py", "--run-dir", str(run_dir), "--status", "solved"])
    summary = temp_ctf_env.solver_repo / "metrics" / "summary.jsonl"
    records = _summary_records(summary)
    assert len(records) == 1
    record = records[0]
    assert record["verifier_success"] is True
    assert record["verifier_flag_found"] is True
    assert record["verifier_target"] == "remote"
    rendered = json.dumps(record, sort_keys=True)
    assert "FLAG{dummy}" not in rendered
    assert str(temp_ctf_env.base) not in rendered


def test_writeup_includes_verification_section(run_cli) -> None:
    _, run_dir = _init_run(run_cli, "Verifier Writeup")
    run_cli(
        [
            "scripts/verify_run.py",
            "--run-dir",
            str(run_dir),
            "--mode",
            "manual",
            "--evidence-text",
            "proof marker",
            "--success-regex",
            "proof marker",
            "--local",
            "--json",
        ]
    )
    generated = parse_json_output(run_cli(["scripts/generate_writeup.py", "--run-dir", str(run_dir)]))
    writeup = Path(str(generated["writeup_path"])).read_text(encoding="utf-8")
    assert "## Verification" in writeup
    assert "Verifier ID" in writeup
    assert "Success: `True`" in writeup
