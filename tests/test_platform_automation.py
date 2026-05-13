from __future__ import annotations

import json
from pathlib import Path

from conftest import parse_json_output
from ctf_solver_core.paths import download_root, is_inside_repo
from ctf_solver_core.queue import list_queue_items
from ctf_solver_core.resources import list_leases
from ctf_solver_core.schemas import read_json, read_jsonl


def _fixture_bundle(base: Path) -> tuple[Path, Path]:
    files = base / "files"
    files.mkdir(parents=True, exist_ok=True)
    challenge_file = files / "web1.txt"
    challenge_file.write_text("fixture challenge payload\n", encoding="utf-8")
    fixture = base / "challenges.json"
    fixture.write_text(
        json.dumps(
            {
                "challenges": [
                    {
                        "challenge_id": "web-1",
                        "name": "Web One",
                        "category": "web",
                        "files": ["files/web1.txt"],
                        "remote_required": True,
                        "local_capable": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture, challenge_file


def test_browser_state_init_refuses_repo_internal_storage_state(temp_ctf_env, run_cli) -> None:
    storage = temp_ctf_env.solver_repo / "storage-state.json"
    storage.write_text("{}", encoding="utf-8")
    result = run_cli(
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
        ],
        check=False,
    )
    assert result.returncode != 0
    parsed = parse_json_output(result)
    assert parsed["ok"] is False
    assert parsed["reason"] == "storage_state_path_inside_repo"


def test_browser_state_init_registers_external_storage_without_printing_contents(temp_ctf_env, run_cli) -> None:
    storage = temp_ctf_env.base / "external-state.json"
    storage.write_text('{"cookies":[{"name":"dummy","value":"SECRET_CONTENT_SHOULD_NOT_PRINT"}]}', encoding="utf-8")
    result = run_cli(
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
    assert "SECRET_CONTENT_SHOULD_NOT_PRINT" not in result.stdout
    parsed = parse_json_output(result)
    assert parsed["ok"] is True
    assert parsed["storage_state_configured"] is True


def test_browser_state_check_returns_profile_exists(temp_ctf_env, run_cli) -> None:
    storage = temp_ctf_env.base / "external-state.json"
    storage.write_text("{}", encoding="utf-8")
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
    checked = parse_json_output(
        run_cli(
            [
                "scripts/browser_state_check.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--profile",
                "main",
                "--json",
            ]
        )
    )
    assert checked["ok"] is True
    assert checked["exists"] is True
    assert checked["storage_state_exists"] is True


def test_mock_platform_discover_parses_local_json_fixture(temp_ctf_env, run_cli) -> None:
    fixture, _ = _fixture_bundle(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--source",
                str(fixture),
                "--queue",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["challenge_count"] == 1
    assert result["challenges"][0]["challenge_id"] == "web-1"


def test_platform_discover_queue_adds_items(temp_ctf_env, run_cli) -> None:
    fixture, _ = _fixture_bundle(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--adapter",
                "mock",
                "--source",
                str(fixture),
                "--queue",
                "--json",
            ]
        )
    )
    assert result["queued_count"] == 1
    items = list_queue_items(platform="thcon", event="THCON")
    assert len(items) == 1
    assert items[0]["challenge_id"] == "web-1"
    assert items[0]["state"] == "discovered"


def test_platform_download_copies_fixture_outside_repo_and_writes_metadata(temp_ctf_env, run_cli) -> None:
    fixture, _ = _fixture_bundle(temp_ctf_env.base)
    run_cli(
        [
            "scripts/platform_discover.py",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--adapter",
            "mock",
            "--source",
            str(fixture),
            "--queue",
            "--json",
        ]
    )
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_download.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-id",
                "web-1",
                "--adapter",
                "mock",
                "--source",
                str(fixture),
                "--queue",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["metadata"]["size"] > 0
    metadata_path = download_root() / "thcon" / "thcon" / "web-1" / "download_metadata.json"
    assert metadata_path.is_file()
    assert not is_inside_repo(metadata_path)
    metadata = read_json(metadata_path)
    assert metadata["files"][0]["relative_path"] == "files/web1.txt"
    assert list_queue_items(platform="thcon", event="THCON")[0]["state"] == "downloaded"


def test_platform_server_acquire_respects_max_active_leases_one(temp_ctf_env, run_cli) -> None:
    acquired_a = parse_json_output(
        run_cli(
            [
                "scripts/platform_server_acquire.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-id",
                "web-1",
                "--run-id",
                "run-A",
                "--adapter",
                "mock",
                "--confirm",
                "--json",
            ]
        )
    )
    assert acquired_a["server_acquired"] is True
    acquired_b = parse_json_output(
        run_cli(
            [
                "scripts/platform_server_acquire.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-id",
                "web-2",
                "--run-id",
                "run-B",
                "--adapter",
                "mock",
                "--confirm",
                "--json",
            ],
            check=False,
        )
    )
    assert acquired_b["ok"] is False
    assert acquired_b["reason"] == "max_active_leases_reached"


def test_platform_server_release_releases_server_and_lease(temp_ctf_env, run_cli) -> None:
    acquired = parse_json_output(
        run_cli(
            [
                "scripts/platform_server_acquire.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-id",
                "web-1",
                "--run-id",
                "run-A",
                "--adapter",
                "mock",
                "--confirm",
                "--json",
            ]
        )
    )
    assert acquired["server_acquired"] is True
    released = parse_json_output(
        run_cli(
            [
                "scripts/platform_server_release.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--run-id",
                "run-A",
                "--adapter",
                "mock",
                "--json",
            ]
        )
    )
    assert released["ok"] is True
    assert released["server_release_count"] == 1
    assert released["lease_release_count"] == 1
    assert list_leases(platform="thcon", event="THCON") == []


def test_platform_submit_default_ask_does_not_submit(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_submit.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-id",
                "web-1",
                "--flag",
                "PLACEHOLDER_FLAG",
                "--adapter",
                "mock",
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["submitted"] is False
    assert result["reason"] == "allow_submission_requires_confirmation"
    assert "PLACEHOLDER_FLAG" not in json.dumps(result)


def test_helper_role_cannot_submit(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_submit.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-id",
                "web-1",
                "--flag",
                "PLACEHOLDER_FLAG",
                "--role",
                "helper",
                "--adapter",
                "mock",
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["submitted"] is False
    assert result["reason"] == "primary_role_required"


def test_platform_metrics_public_safe_check_passes(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/update_metrics.py",
                "--run-id",
                "metric-run",
                "--status",
                "manual_stop",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--category",
                "web",
                "--platform-discovery-count",
                "1",
                "--downloaded-file-count",
                "1",
                "--downloaded-bytes",
                "12",
                "--server-acquire-attempted",
                "--server-acquire-success",
                "--server-release-count",
                "1",
                "--submission-attempted",
                "--submission-policy",
                "ask",
                "--platform-adapter",
                "mock",
            ]
        )
    )
    assert result["public_summary_updated"] is True
    records = read_jsonl(temp_ctf_env.solver_repo / "metrics" / "summary.jsonl")
    assert records[0]["platform_adapter"] == "mock"
    assert records[0]["server_release_count"] == 1
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout


def test_doctor_passes_with_platform_scaffold(temp_ctf_env, run_cli) -> None:
    ctf_dir = temp_ctf_env.home / "CTF"
    ctf_dir.mkdir(parents=True, exist_ok=True)
    claude_md = ctf_dir / "CLAUDE.md"
    claude_md.write_text("## Challenge Lifecycle Rules\n", encoding="utf-8")
    (ctf_dir / "AGENTS.md").write_text("## Challenge Lifecycle Rules\n", encoding="utf-8")
    skill_dir = temp_ctf_env.home / ".agents" / "skills" / "ctf-personal"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# ctf-personal\n", encoding="utf-8")
    result = run_cli(["scripts/doctor.py"])
    assert "Hard failures: 0" in result.stdout
