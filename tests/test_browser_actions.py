from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import parse_json_output
from ctf_solver_core.browser_actions import (
    BrowserActionError,
    browser_session_metadata_path,
    is_inside_repo,
    new_session_metadata,
    redact_headers,
    redacted_cookie_summary,
    redacted_network_event,
    validate_storage_state_path,
    write_private_json,
)


@pytest.fixture(autouse=True)
def _stop_browser_daemon(run_cli):
    yield
    run_cli(["scripts/browser_daemon.py", "stop"], check=False)


def test_browser_roots_are_local_only_in_tests(temp_ctf_env) -> None:
    assert not is_inside_repo(temp_ctf_env.browser)
    assert not is_inside_repo(temp_ctf_env.browser_artifacts)


def test_storage_state_inside_repo_is_rejected(temp_ctf_env) -> None:
    state = temp_ctf_env.solver_repo / "storage-state.json"
    state.write_text("{}", encoding="utf-8")
    with pytest.raises(BrowserActionError, match="storage_state_path_inside_repo"):
        validate_storage_state_path(state)


def test_cookie_summary_redacts_value() -> None:
    summary = redacted_cookie_summary(
        {
            "name": "sid",
            "value": "raw-cookie-value",
            "domain": "example.test",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
    )
    assert summary["name"] == "sid"
    assert summary["value"] == "<REDACTED>"
    assert "raw-cookie-value" not in json.dumps(summary)


def test_network_and_header_redaction() -> None:
    headers = redact_headers(
        {
            "Authorization": "Bearer secret-token",
            "Cookie": "sid=secret-cookie",
            "Set-Cookie": "sid=secret-cookie",
            "Content-Type": "text/html",
        }
    )
    assert headers["Authorization"] == "<REDACTED>"
    assert headers["Cookie"] == "<REDACTED>"
    assert headers["Set-Cookie"] == "<REDACTED>"
    assert headers["Content-Type"] == "text/html"

    event = redacted_network_event(
        {
            "type": "request",
            "method": "GET",
            "url": "https://example.test/path?" + "token" + "=secret-token&ok=1",
            "headers": {"Authorization": "Bearer secret-token"},
        }
    )
    assert "secret-token" not in json.dumps(event)
    assert ("token" + "=%3CREDACTED%3E") in str(event["url"])


def test_browser_start_is_skip_safe_without_required_playwright(run_cli) -> None:
    result = parse_json_output(run_cli(["scripts/browser_start.py", "--run-id", "RUN_BROWSER", "--json"], check=False))
    if result.get("ok"):
        session_id = str(result["session"]["browser_session_id"])
        run_cli(["scripts/browser_close.py", "--browser-session-id", session_id, "--json"], check=False)
    else:
        assert result.get("reason") in {
            "playwright_not_installed",
            "playwright_browser_not_installed",
            "playwright_browser_unavailable",
            "browser_start_failed",
        }


def test_finalize_records_browser_sessions_when_daemon_is_unavailable(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Browser Finalize",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    metadata = new_session_metadata(browser_session_id="fake-browser-session", run_id=run_id, challenge_id=str(init["challenge_id"]))
    metadata["status"] = "running"
    metadata["actions_count"] = 3
    write_private_json(browser_session_metadata_path("fake-browser-session"), metadata)

    finalized = parse_json_output(
        run_cli(["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "manual_stop"])
    )
    assert finalized["browser_sessions"]["reason"] == "daemon_not_running"
    assert finalized["browser_sessions"]["session_count"] == 1
    final_record = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
    assert final_record["browser_metrics"]["browser_session_count"] == 1
    assert final_record["closed_browser_session_count"] == 0


def test_platform_smoke_test_dry_run_no_network(run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_smoke_test.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--json",
            ]
        )
    )
    assert result["dry_run"] is True
    assert result["live_network_performed"] is False

    live = parse_json_output(
        run_cli(
            [
                "scripts/platform_smoke_test.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--live",
                "--json",
            ],
            check=False,
        )
    )
    assert live["ok"] is False
    assert live["live_network_performed"] is False


def test_optional_playwright_data_url_flow(run_cli, temp_ctf_env) -> None:
    pytest.importorskip("playwright.sync_api")
    started = parse_json_output(run_cli(["scripts/browser_start.py", "--run-id", "RUN_PW", "--json"], check=False))
    if not started.get("ok"):
        pytest.skip(str(started.get("reason") or "playwright browser unavailable"))
    session_id = str(started["session"]["browser_session_id"])
    try:
        html = "data:text/html,<html><head><title>Local</title></head><body><input id='x'><script>console.log('ready')</script></body></html>"
        goto = parse_json_output(
            run_cli(["scripts/browser_goto.py", "--browser-session-id", session_id, "--url", html, "--json"])
        )
        assert goto["ok"] is True
        filled = parse_json_output(
            run_cli(
                [
                    "scripts/browser_fill.py",
                    "--browser-session-id",
                    session_id,
                    "--selector",
                    "#x",
                    "--value",
                    "hello",
                    "--json",
                ]
            )
        )
        assert filled["value_redacted"] is True
        evaluated = parse_json_output(
            run_cli(
                [
                    "scripts/browser_eval.py",
                    "--browser-session-id",
                    session_id,
                    "--expression",
                    "document.title",
                    "--json",
                ]
            )
        )
        assert evaluated["result"] == "Local"
        screenshot = parse_json_output(
            run_cli(["scripts/browser_screenshot.py", "--browser-session-id", session_id, "--name", "local", "--json"])
        )
        screenshot_path = Path(str(screenshot["screenshot_path"]).replace("~", str(temp_ctf_env.home), 1))
        assert screenshot_path.is_file()
        assert temp_ctf_env.solver_repo not in screenshot_path.parents
    finally:
        run_cli(["scripts/browser_close.py", "--browser-session-id", session_id, "--json"], check=False)
