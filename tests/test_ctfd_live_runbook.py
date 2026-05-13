from __future__ import annotations

from pathlib import Path

from conftest import REPO_ROOT, parse_json_output


def _commands(plan: dict[str, object]) -> dict[str, str]:
    return {
        str(item["name"]): str(item["command"])
        for item in plan["commands"]
        if isinstance(item, dict) and "name" in item and "command" in item
    }


def test_ctfd_runbook_helper_outputs_dry_run_without_live_by_default(run_cli) -> None:
    result = parse_json_output(run_cli(["scripts/ctfd_live_smoke_runbook.py", "--json"]))
    commands = _commands(result)
    assert result["ok"] is True
    assert result["network_performed"] is False
    assert "smoke_dry_run" in commands
    assert "--mode discovery" in commands["smoke_dry_run"]
    assert "--live" not in commands["smoke_dry_run"]
    assert "--queue" not in " ".join(commands.values())


def test_ctfd_runbook_helper_includes_live_command_only_when_requested(run_cli) -> None:
    default_result = parse_json_output(run_cli(["scripts/ctfd_live_smoke_runbook.py", "--json"]))
    default_commands = _commands(default_result)
    assert "smoke_live_discovery" not in default_commands
    assert "platform_discover_live" not in default_commands

    live_result = parse_json_output(
        run_cli(["scripts/ctfd_live_smoke_runbook.py", "--include-live-command", "--json"])
    )
    live_commands = _commands(live_result)
    assert live_result["network_performed"] is False
    assert live_result["live_commands_included"] is True
    assert "--live" in live_commands["smoke_live_discovery"]
    assert "--live" in live_commands["platform_discover_live"]


def test_ctfd_runbook_helper_does_not_print_cookie_or_url_secret_values(temp_ctf_env, run_cli) -> None:
    secret_value = "SECRET_VALUE_SHOULD_NOT_PRINT"
    temp_ctf_env.env["CTF_CTFD_COOKIE_HEADER"] = ("sess" + "ion=" + secret_value)
    output = run_cli(
        [
            "scripts/ctfd_live_smoke_runbook.py",
            "--base-url",
            "https://ctfd.example.invalid/path?" + "tok" + "en=" + secret_value,
            "--include-live-command",
            "--json",
        ]
    )
    assert secret_value not in output.stdout
    result = parse_json_output(output)
    assert result["base_url"] == "https://ctfd.example.invalid/path"


def test_ctfd_runbook_helper_queue_command_requires_explicit_option(run_cli) -> None:
    default_result = parse_json_output(
        run_cli(["scripts/ctfd_live_smoke_runbook.py", "--include-live-command", "--json"])
    )
    default_commands = _commands(default_result)
    assert "platform_discover_live_queue" not in default_commands
    assert "--queue" not in " ".join(default_commands.values())

    queue_result = parse_json_output(
        run_cli(
            [
                "scripts/ctfd_live_smoke_runbook.py",
                "--include-live-command",
                "--include-queue-command",
                "--json",
            ]
        )
    )
    queue_commands = _commands(queue_result)
    assert queue_result["queue_command_included"] is True
    assert "--queue" in queue_commands["platform_discover_live_queue"]


def test_ctfd_live_runbook_docs_mention_no_submit_and_dry_run_first() -> None:
    runbook = (REPO_ROOT / "docs" / "ctfd-live-smoke-runbook.md").read_text(encoding="utf-8")
    live_smoke = (REPO_ROOT / "docs" / "live-smoke.md").read_text(encoding="utf-8")
    combined = runbook + "\n" + live_smoke
    assert "dry-run first" in combined.lower()
    assert "no-submit" in combined.lower() or "never submits flags" in combined.lower()
    assert "CTF_CTFD_COOKIE_FILE" in combined
    assert "CTF_CTFD_COOKIE_HEADER" in combined
    assert "discovered_count" in combined
