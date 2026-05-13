from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT, parse_json_output
from ctf_solver_core.adapters import dreamhack as dreamhack_module
from ctf_solver_core.platform_adapters import get_adapter
from ctf_solver_core.platform_automation import control_dreamhack_vm
from ctf_solver_core.platforms import load_platform_policies
from ctf_solver_core.resources import list_leases
from ctf_solver_core.schemas import read_jsonl


def _dreamhack_policy(temp_ctf_env, **kwargs) -> None:
    defaults = {
        "platform": "dreamhack",
        "event": "dreamhackWargame",
        "adapter": "dreamhack",
        "auth_mode": "manual",
        "provisioning": True,
        "max_active": 1,
        "allow_problem_discovery": True,
        "allow_file_download": True,
        "allow_server_create": "ask",
        "allow_submission": False,
    }
    defaults.update(kwargs)
    temp_ctf_env.write_platform_config(**defaults)


def _dreamhack_fixture(base: Path) -> tuple[Path, Path]:
    files = base / "attachments"
    files.mkdir(parents=True, exist_ok=True)
    handout = files / "handout.txt"
    handout.write_text("dreamhack fixture handout\n", encoding="utf-8")
    fixture = base / "dreamhack.json"
    fixture.write_text(
        json.dumps(
            {
                "challenges": [
                    {
                        "id": 1001,
                        "name": "web baby",
                        "category": "web",
                        "files": [{"name": "handout.txt", "path": "attachments/handout.txt"}],
                        "has_vm": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture, handout


def test_dreamhack_adapter_registry_present() -> None:
    adapter = get_adapter("dreamhack")
    assert adapter.name == "dreamhack"


def test_dreamhack_policy_loads_from_example_config() -> None:
    policies = load_platform_policies(REPO_ROOT / "config" / "platforms.example.yaml")
    dreamhack = [item for item in policies if item.platform == "dreamhack" and item.event == "dreamhackWargame"]
    assert len(dreamhack) == 1
    policy = dreamhack[0]
    assert policy.adapter == "dreamhack"
    assert policy.resources.remote_server.max_active_leases == 1
    assert policy.resources.remote_server.lease_scope == "platform_event"
    assert policy.automation.allow_submission is False


def test_dreamhack_discovery_parses_fixture(temp_ctf_env, run_cli) -> None:
    _dreamhack_policy(temp_ctf_env)
    fixture, _ = _dreamhack_fixture(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "dreamhack",
                "--event",
                "dreamhackWargame",
                "--adapter",
                "dreamhack",
                "--source",
                str(fixture),
                "--queue",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["adapter"] == "dreamhack"
    assert result["challenge_count"] == 1
    assert result["challenges"][0]["external_id"] == "1001"
    assert result["queued_count"] == 1


def test_vm_action_summary_redacts_session_csrf_and_host() -> None:
    adapter = get_adapter("dreamhack")
    summary = adapter.summarize_vm_response(
        action="start",
        challenge_id="1001",
        status_code=200,
        response={"status": "started", "host": "host3.dreamhack.games", "port": 31337},
        session_configured=True,
        csrf_configured=True,
    )
    rendered = json.dumps(summary, sort_keys=True)
    assert summary["ok"] is True
    assert summary["host"] == "<redacted>"
    assert summary["port"] == 31337
    assert summary["auth"] == {"session_configured": True, "csrf_configured": True}
    assert "host3.dreamhack.games" not in rendered
    assert "csrf-token-value" not in rendered
    assert "session-value" not in rendered


def test_start_action_requires_explicit_live_and_auth(temp_ctf_env, run_cli) -> None:
    _dreamhack_policy(temp_ctf_env)
    no_live = parse_json_output(
        run_cli(
            [
                "scripts/dreamhack_vm_control.py",
                "--challenge-id",
                "1001",
                "--run-id",
                "run-A",
                "--action",
                "start",
                "--confirm",
                "--json",
            ],
            check=False,
        )
    )
    assert no_live["ok"] is False
    assert no_live["reason"] == "dreamhack_live_required"

    no_auth = parse_json_output(
        run_cli(
            [
                "scripts/dreamhack_vm_control.py",
                "--challenge-id",
                "1001",
                "--run-id",
                "run-A",
                "--action",
                "start",
                "--confirm",
                "--live",
                "--json",
            ],
            check=False,
        )
    )
    assert no_auth["ok"] is False
    assert no_auth["reason"] == "dreamhack_auth_required"


def test_max_active_leases_blocks_second_dreamhack_vm_action(temp_ctf_env, monkeypatch) -> None:
    _dreamhack_policy(temp_ctf_env)
    monkeypatch.setenv("CTF_DREAMHACK_SESSION_ID", "LOCAL_SESSION_SHOULD_NOT_PRINT")
    monkeypatch.setenv("CTF_DREAMHACK_CSRF_TOKEN", "LOCAL_CSRF_SHOULD_NOT_PRINT")

    def fake_vm_action(**kwargs):
        return 200, {"state": "started", "host": "host3.dreamhack.games", "port": 30001}

    monkeypatch.setattr(dreamhack_module, "_vm_action_live", fake_vm_action)
    first = control_dreamhack_vm(
        platform="dreamhack",
        event="dreamhackWargame",
        challenge_id="1001",
        run_id="run-A",
        action="start",
        adapter_name="dreamhack",
        confirmed=True,
        live=True,
    )
    rendered_first = json.dumps(first, sort_keys=True)
    assert first["ok"] is True
    assert first["dreamhack_vm_active_count"] == 1
    assert "LOCAL_SESSION_SHOULD_NOT_PRINT" not in rendered_first
    assert "LOCAL_CSRF_SHOULD_NOT_PRINT" not in rendered_first
    assert "host3.dreamhack.games" not in rendered_first

    second = control_dreamhack_vm(
        platform="dreamhack",
        event="dreamhackWargame",
        challenge_id="1002",
        run_id="run-B",
        action="start",
        adapter_name="dreamhack",
        confirmed=True,
        live=True,
    )
    assert second["ok"] is False
    assert second["reason"] == "max_active_leases_reached"
    assert len(list_leases(platform="dreamhack", event="dreamhackWargame")) == 1


def test_dreamhack_metrics_public_safe_check_passes(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/update_metrics.py",
                "--run-id",
                "dreamhack-metric-run",
                "--status",
                "manual_stop",
                "--platform",
                "dreamhack",
                "--event",
                "dreamhackWargame",
                "--category",
                "web",
                "--platform-adapter",
                "dreamhack",
                "--dreamhack-vm-action-attempted",
                "--dreamhack-vm-action-success",
                "--dreamhack-vm-active-count",
                "1",
            ]
        )
    )
    assert result["public_summary_updated"] is True
    records = read_jsonl(temp_ctf_env.solver_repo / "metrics" / "summary.jsonl")
    record = records[0]
    assert record["platform_adapter"] == "dreamhack"
    assert record["dreamhack_vm_action_attempted"] is True
    assert record["dreamhack_vm_action_success"] is True
    assert record["dreamhack_vm_active_count"] == 1
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout


def test_dreamhack_secret_scan_include_untracked_passes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "secret_scan.py"),
            "--strict",
            "--include-untracked",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
