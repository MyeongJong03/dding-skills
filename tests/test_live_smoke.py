from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from conftest import REPO_ROOT, parse_json_output
from ctf_solver_core.paths import is_inside_repo
from ctf_solver_core.schemas import read_json, read_jsonl, validate_public_record


def _fixture_bundle(base: Path) -> Path:
    files = base / "live-fixtures" / "files"
    files.mkdir(parents=True, exist_ok=True)
    (files / "handout.txt").write_text("local live smoke fixture\n", encoding="utf-8")
    fixture = base / "live-fixtures" / "challenges.json"
    fixture.write_text(
        json.dumps(
            {
                "challenges": [
                    {
                        "challenge_id": "web-1",
                        "name": "Web One",
                        "category": "web",
                        "files": ["files/handout.txt"],
                        "remote_required": True,
                        "local_capable": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture


def _path_from_display(temp_ctf_env, value: str) -> Path:
    if value.startswith("~/"):
        return temp_ctf_env.home / value[2:]
    return Path(value)


def test_live_smoke_dry_run_does_not_access_network(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_live_smoke.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--mode",
                "discovery",
                "--base-url",
                "https://ctf.example.invalid/challenges",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["live_network_allowed"] is False
    assert result["live_network_performed"] is False
    assert result["actions"]["discovery"]["performed"] is False
    assert result["actions"]["discovery"]["reason"] == "live_flag_absent_dry_run_only"


def test_live_smoke_dry_run_validates_profile_without_reading_storage_state(temp_ctf_env, run_cli) -> None:
    storage = temp_ctf_env.base / "external-state.json"
    marker = "SECRET_CONTENT_SHOULD_NOT_PRINT"
    storage.write_text(json.dumps({"cookies": [{"name": "dummy", "value": marker}]}), encoding="utf-8")
    run_cli(
        [
            "scripts/browser_state_init.py",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--profile",
            "main",
            "--storage-state",
            str(storage),
            "--json",
        ]
    )
    output = run_cli(
        [
            "scripts/platform_live_smoke.py",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--adapter",
            "mock",
            "--profile",
            "main",
            "--mode",
            "dry-run",
            "--json",
        ]
    )
    assert marker not in output.stdout
    result = parse_json_output(output)
    assert result["profile"]["ok"] is True
    assert result["profile"]["storage_state_configured"] is True
    result_path = _path_from_display(temp_ctf_env, str(result["result_path"]))
    assert marker not in result_path.read_text(encoding="utf-8")


def test_live_absent_blocks_all_non_dry_run_actions(temp_ctf_env, run_cli) -> None:
    for mode, key in [
        ("discovery", "discovery"),
        ("download", "download"),
        ("server-status", "server_status"),
        ("server-acquire", "server_acquire"),
    ]:
        args = [
            "scripts/platform_live_smoke.py",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--adapter",
            "mock",
            "--mode",
            mode,
            "--json",
        ]
        if mode in {"download", "server-acquire"}:
            args.extend(["--challenge-id", "web-1"])
        result = parse_json_output(run_cli(args))
        assert result["ok"] is True
        assert result["actions"][key]["performed"] is False
        assert result["actions"][key]["reason"] == "live_flag_absent_dry_run_only"


def test_mock_adapter_live_discovery_uses_local_fixture_only(temp_ctf_env, run_cli) -> None:
    temp_ctf_env.write_platform_config(auth_mode="none")
    fixture = _fixture_bundle(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_live_smoke.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--source",
                str(fixture),
                "--mode",
                "discovery",
                "--live",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["actions"]["discovery"]["performed"] is True
    assert result["actions"]["discovery"]["challenge_count"] == 1
    assert result["live_network_performed"] is False


def test_download_mode_requires_allow_download(temp_ctf_env, run_cli) -> None:
    temp_ctf_env.write_platform_config(auth_mode="none")
    fixture = _fixture_bundle(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_live_smoke.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--source",
                str(fixture),
                "--mode",
                "download",
                "--challenge-id",
                "web-1",
                "--live",
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["actions"]["download"]["reason"] == "allow_download_flag_required"


def test_server_acquire_mode_requires_allow_server_acquire(temp_ctf_env, run_cli) -> None:
    temp_ctf_env.write_platform_config(auth_mode="none")
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_live_smoke.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--mode",
                "server-acquire",
                "--challenge-id",
                "web-1",
                "--run-id",
                "live-smoke-run",
                "--live",
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["actions"]["server_acquire"]["reason"] == "allow_server_acquire_flag_required"


def test_no_submit_default_is_enforced_even_when_policy_allows_submission(temp_ctf_env, run_cli) -> None:
    temp_ctf_env.write_platform_config(auth_mode="none", allow_submission=True)
    fixture = _fixture_bundle(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_live_smoke.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--source",
                str(fixture),
                "--mode",
                "discovery",
                "--live",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["no_submit"] is True
    assert result["submission"]["attempted"] is False
    assert result["submission"]["policy"] == "true"


def test_live_smoke_writes_result_and_summary_under_private_root(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_live_smoke.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--mode",
                "dry-run",
                "--json",
            ]
        )
    )
    result_path = _path_from_display(temp_ctf_env, str(result["result_path"]))
    summary_path = _path_from_display(temp_ctf_env, str(result["summary_path"]))
    assert result_path.is_file()
    assert summary_path.is_file()
    assert temp_ctf_env.live_smoke in result_path.parents
    assert not is_inside_repo(result_path)
    stored = read_json(result_path)
    assert stored["smoke_id"] == result["smoke_id"]


def test_live_smoke_public_metrics_are_safe_and_update_metrics_accepts_them(temp_ctf_env, run_cli) -> None:
    temp_ctf_env.write_platform_config(auth_mode="none")
    fixture = _fixture_bundle(temp_ctf_env.base)
    smoke = parse_json_output(
        run_cli(
            [
                "scripts/platform_live_smoke.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--source",
                str(fixture),
                "--mode",
                "discovery",
                "--live",
                "--json",
            ]
        )
    )
    metrics = smoke["public_metrics"]
    assert validate_public_record(metrics) == []
    run_cli(
        [
            "scripts/update_metrics.py",
            "--run-id",
            "live-smoke-metric-run",
            "--status",
            "manual_stop",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--category",
            "web",
            "--platform-adapter",
            "mock",
            "--live-smoke-count",
            str(metrics["live_smoke_count"]),
            "--live-smoke-mode",
            str(metrics["live_smoke_mode"]),
            "--live-smoke-success",
            "--live-smoke-discovered-count",
            str(metrics["live_smoke_discovered_count"]),
        ]
    )
    records = read_jsonl(temp_ctf_env.solver_repo / "metrics" / "summary.jsonl")
    assert records[0]["live_smoke_mode"] == "discovery"
    assert records[0]["live_smoke_success"] is True
    assert records[0]["live_smoke_discovered_count"] == 1
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout


def test_live_smoke_secret_scan_strict_include_untracked_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "secret_scan.py"), "--strict", "--include-untracked"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
