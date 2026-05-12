#!/usr/bin/env python3
"""No-install Playwright runtime checks for local browser automation."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def _find_uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "uv"
    if candidate.is_file() and candidate.stat().st_mode & 0o111:
        return str(candidate)
    return None


def _current_playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _current_chromium_available() -> bool | None:
    if not _current_playwright_available():
        return None
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as playwright:
            return Path(str(playwright.chromium.executable_path)).is_file()
    except Exception:
        return False


def _run_uv_check(uv_bin: str, *, timeout_seconds: int) -> dict[str, object]:
    code = (
        "import json\n"
        "from pathlib import Path\n"
        "result = {'playwright_available': False, 'chromium_available': None}\n"
        "try:\n"
        "    from playwright.sync_api import sync_playwright\n"
        "    result['playwright_available'] = True\n"
        "    with sync_playwright() as p:\n"
        "        result['chromium_available'] = Path(str(p.chromium.executable_path)).is_file()\n"
        "except Exception as exc:\n"
        "    if result['playwright_available']:\n"
        "        result['chromium_available'] = False\n"
        "    result['error'] = exc.__class__.__name__\n"
        "print(json.dumps(result, sort_keys=True))\n"
    )
    command = [
        uv_bin,
        "run",
        "--offline",
        "--with",
        "playwright",
        "python",
        "-c",
        code,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "uv_playwright_available": None,
            "uv_chromium_available": None,
            "uv_check_error": "timeout",
        }
    if completed.returncode != 0:
        return {
            "uv_playwright_available": False,
            "uv_chromium_available": None,
            "uv_check_error": "offline_package_unavailable",
        }
    try:
        parsed = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {
            "uv_playwright_available": False,
            "uv_chromium_available": None,
            "uv_check_error": "invalid_uv_output",
        }
    return {
        "uv_playwright_available": bool(parsed.get("playwright_available")),
        "uv_chromium_available": parsed.get("chromium_available"),
        "uv_check_error": parsed.get("error", ""),
    }


def _recommendation(result: dict[str, object]) -> str:
    if result.get("current_python_playwright_available") and result.get("current_python_chromium_available"):
        return "current_python_ready"
    if result.get("current_python_playwright_available"):
        return "install_chromium_with_current_python_or_uv"
    if result.get("uv_playwright_available") and result.get("uv_chromium_available"):
        return "run_browser_tools_with_uv_with_playwright"
    if result.get("uv_available"):
        return "use_uv_with_playwright_and_install_chromium"
    return "create_repo_external_venv_for_playwright"


def collect_status(*, use_uv: bool = False, timeout_seconds: int = 15) -> dict[str, object]:
    uv_bin = _find_uv()
    result: dict[str, object] = {
        "current_python_playwright_available": _current_playwright_available(),
        "current_python_chromium_available": _current_chromium_available(),
        "uv_available": uv_bin is not None,
        "uv_playwright_available": None,
        "uv_chromium_available": None,
        "uv_check_mode": "not_requested",
        "uv_check_error": "",
        "recommendation": "",
    }
    if use_uv and uv_bin:
        result["uv_check_mode"] = "offline_no_install"
        result.update(_run_uv_check(uv_bin, timeout_seconds=timeout_seconds))
    elif use_uv:
        result["uv_check_mode"] = "uv_not_found"
    result["recommendation"] = _recommendation(result)
    return result


def _print_human(result: dict[str, object]) -> None:
    for key in [
        "current_python_playwright_available",
        "current_python_chromium_available",
        "uv_available",
        "uv_playwright_available",
        "uv_chromium_available",
        "uv_check_mode",
        "recommendation",
    ]:
        print(f"{key}: {result.get(key)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-uv", action="store_true", help="also check uv cache in offline/no-install mode")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = collect_status(use_uv=args.use_uv, timeout_seconds=max(1, args.timeout_seconds))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
