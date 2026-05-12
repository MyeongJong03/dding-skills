from __future__ import annotations

from conftest import parse_json_output


def test_browser_playwright_check_json_no_install(run_cli) -> None:
    result = parse_json_output(run_cli(["scripts/browser_playwright_check.py", "--json"]))
    assert "current_python_playwright_available" in result
    assert "uv_available" in result
    assert result["uv_playwright_available"] is None
    assert result["recommendation"]


def test_browser_playwright_check_uv_json_no_install(run_cli) -> None:
    result = parse_json_output(
        run_cli(["scripts/browser_playwright_check.py", "--use-uv", "--timeout-seconds", "5", "--json"])
    )
    assert "uv_available" in result
    assert result["uv_check_mode"] in {"offline_no_install", "uv_not_found"}
    assert "recommendation" in result
