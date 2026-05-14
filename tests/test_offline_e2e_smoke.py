from __future__ import annotations

from conftest import parse_json_output
from ctf_solver_core.schemas import validate_public_record


STAGE_KEYS = (
    "discovery_ok",
    "queue_ok",
    "download_ok",
    "init_ok",
    "verifier_ok",
    "finalize_ok",
    "writeup_ok",
    "metrics_ok",
    "cleanup_ok",
    "public_safe_ok",
)


def _assert_success(result: dict[str, object], platform: str) -> None:
    assert result["ok"] is True
    assert result["platform"] == platform
    for key in STAGE_KEYS:
        assert result[key] is True
    assert result["downloaded_file_count"] == 1
    assert result["temp_kept"] is False
    assert str(result["run_id"])
    assert str(result["challenge_id"])
    assert validate_public_record(result) == []


def test_offline_e2e_smoke_ctfd_fixture_flow(run_cli) -> None:
    output = run_cli(["scripts/offline_e2e_smoke.py", "--platform", "ctfd", "--json"])
    result = parse_json_output(output)
    _assert_success(result, "ctfd")
    assert result["challenge_id"] == "ctfd/offline-e2e/web/offline-ctfd-smoke"
    assert "/Users/" not in output.stdout
    assert "/private/" not in output.stdout


def test_offline_e2e_smoke_dreamhack_fixture_flow(run_cli) -> None:
    output = run_cli(["scripts/offline_e2e_smoke.py", "--platform", "dreamhack", "--json"])
    result = parse_json_output(output)
    _assert_success(result, "dreamhack")
    assert result["challenge_id"] == "dreamhack/offline-e2e/web/offline-dreamhack-smoke"
    assert "/Users/" not in output.stdout
    assert "/private/" not in output.stdout


def test_offline_e2e_smoke_carries_explicit_challenge_id(run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/offline_e2e_smoke.py",
                "--platform",
                "ctfd",
                "--challenge-id",
                "offline-explicit-id",
                "--json",
            ]
        )
    )
    _assert_success(result, "ctfd")
    assert result["challenge_id"] == "offline-explicit-id"


def test_offline_e2e_smoke_rejects_url_fixture_root(run_cli) -> None:
    output = run_cli(
        [
            "scripts/offline_e2e_smoke.py",
            "--platform",
            "ctfd",
            "--fixture-root",
            "https://example.invalid/fixtures",
            "--json",
        ],
        check=False,
    )
    result = parse_json_output(output)
    assert output.returncode == 1
    assert result["ok"] is False
    assert result["reason"] == "fixture:fixture_root_must_be_local"
    assert result["public_safe_ok"] is False
    assert validate_public_record(result) == []
