from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from conftest import REPO_ROOT


STATUS_SECTIONS = (
    "[git]",
    "[docker]",
    "[mcp_json_summary]",
    "[mcp_live]",
    "[redaction]",
    "[repo_raw_grep]",
    "[doctor]",
)
REGRESSION_SECTIONS = (
    "[git]",
    "[secret_scan]",
    "[pytest]",
    "[doctor]",
    "[update_metrics]",
    "[dump_mcp_tools]",
    "[redact_self_test]",
    "[offline_e2e_ctfd]",
    "[offline_e2e_dreamhack]",
    "[compileall]",
    "[git_diff_check]",
)


def _run(command: list[str], *, env: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *command],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _write_temp_claude_config(home: Path) -> str:
    private_value = "raw-" + "private-" + "value"
    nested_metadata_key = "email" + "Address"
    account_key = "account" + "Uuid"
    data = {
        "mcpServers": {
            "ctf_solver": {
                "command": "python3",
                "args": ["/Users/private/source/server.py"],
                "env": {"PRIVATE_VALUE": private_value},
            }
        },
        "projects": {
            "/Users/private/source": {
                "mcpServers": {
                    "local_probe": {
                        "command": "node",
                        nested_metadata_key: "person@example.invalid",
                        account_key: "11111111-1111-4111-8111-111111111111",
                    }
                }
            }
        },
    }
    (home / ".claude.json").write_text(json.dumps(data), encoding="utf-8")
    return private_value


def _prepare_doctor_home(home: Path) -> None:
    ctf = home / "CTF"
    ctf.mkdir(parents=True, exist_ok=True)
    claude = ctf / "CLAUDE.md"
    claude.write_text("## Challenge Lifecycle Rules\n", encoding="utf-8")
    agents = ctf / "AGENTS.md"
    try:
        agents.symlink_to(claude)
    except OSError:
        agents.write_text(claude.read_text(encoding="utf-8"), encoding="utf-8")
    skill = home / ".agents" / "skills" / "ctf-personal"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("# ctf-personal\n", encoding="utf-8")


def test_status_summary_help(run_cli) -> None:
    result = run_cli(["scripts/status_summary.py", "--help"])
    assert result.returncode == 0
    assert "marker status summary" in result.stdout


def test_status_summary_markers_and_claude_redaction(temp_ctf_env) -> None:
    private_value = _write_temp_claude_config(temp_ctf_env.home)
    result = _run(["scripts/status_summary.py"], env=temp_ctf_env.env)
    assert result.returncode in (0, 1)
    output = result.stdout
    assert "===== CTF_SOLVER_STATUS_BEGIN =====" in output
    assert "===== CTF_SOLVER_STATUS_END =====" in output
    for section in STATUS_SECTIONS:
        assert section in output
    assert "ctf_solver" in output
    assert "local_probe" in output
    assert "result=redacted grep clean" in output
    assert "result=repo raw grep clean" in output
    assert "clean=true" not in output
    assert "locations_shown=" not in output
    assert "location_count=" not in output
    assert '"mcpServers"' not in output
    assert private_value not in output
    assert "person@example.invalid" not in output
    assert "11111111-1111-4111-8111-111111111111" not in output
    assert "/Users/private" not in output


def test_status_summary_verbose_shows_grep_locations(temp_ctf_env) -> None:
    _write_temp_claude_config(temp_ctf_env.home)
    result = _run(["scripts/status_summary.py", "--verbose"], env=temp_ctf_env.env)
    assert result.returncode in (0, 1)
    output = result.stdout
    assert "result=redacted grep clean" in output
    assert "result=repo raw grep clean" in output
    assert "location_count=" in output
    assert "locations_shown=" in output


def test_status_summary_json_is_public_safe(temp_ctf_env) -> None:
    private_value = _write_temp_claude_config(temp_ctf_env.home)
    result = _run(["scripts/status_summary.py", "--json"], env=temp_ctf_env.env)
    assert result.returncode in (0, 1)
    data = json.loads(result.stdout)
    assert set(STATUS_SECTIONS_SECTION.strip("[]") for STATUS_SECTIONS_SECTION in STATUS_SECTIONS) <= set(data)
    assert data["mcp_json_summary"]["mcp_server_names"] == ["ctf_solver", "local_probe"]
    assert data["redaction"]["clean"] is True
    assert data["redaction"]["result"] == "redacted grep clean"
    assert data["repo_raw_grep"]["clean"] is True
    assert data["repo_raw_grep"]["result"] == "repo raw grep clean"
    assert "location_count" not in data["redaction"]
    assert "locations" not in data["redaction"]
    assert "location_count" not in data["repo_raw_grep"]
    assert "locations" not in data["repo_raw_grep"]
    assert private_value not in result.stdout
    assert "/Users/private" not in result.stdout


def test_regression_check_help(run_cli) -> None:
    result = run_cli(["scripts/regression_check.py", "--help"])
    assert result.returncode == 0
    assert "--quick" in result.stdout
    assert "--skip-offline-e2e" in result.stdout


def test_operator_mode_runbook_links_and_rules_exist() -> None:
    operator_doc = (REPO_ROOT / "docs" / "operator-mode.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "GUIDE.md").read_text(encoding="utf-8")
    claude_base = (REPO_ROOT / "config" / "CLAUDE.base.md").read_text(encoding="utf-8")

    assert "# Operator Mode Runbook" in operator_doc
    for required in (
        "ctf-status",
        "ctf-check",
        "ctf-regression",
        "challenge_init.py",
        "worker_next.py",
        "worker_run_once.py",
        "verify_run.py",
        "challenge_finalize.py --run-dir <run-dir> --status solved --require-verifier --generate-writeup --cleanup --update-metrics",
        "CTFd",
        "Dreamhack",
        "~/SolvedWriteUp",
        "metrics/",
    ):
        assert required in operator_doc
    assert "docs/operator-mode.md" in readme
    assert "docs/operator-mode.md" in guide
    assert "## Operator Mode Rules" in claude_base


def test_regression_check_quick_marker_pack(temp_ctf_env) -> None:
    _prepare_doctor_home(temp_ctf_env.home)
    env = dict(temp_ctf_env.env)
    env.pop("CTF_DOCTOR_INSPECT_CLAUDE_CONFIG", None)
    env["PYTHONPATH"] = os.pathsep.join(path for path in sys.path if path)
    result = _run(["scripts/regression_check.py", "--quick"], env=env, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout
    assert "===== CTF_SOLVER_REGRESSION_BEGIN =====" in output
    assert "===== CTF_SOLVER_REGRESSION_END =====" in output
    for section in REGRESSION_SECTIONS:
        assert section in output
    assert "--live" not in output
    assert "person@example.invalid" not in output
    assert "/Users/private" not in output
