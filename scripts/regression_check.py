#!/usr/bin/env python3
"""Run the public-safe regression command pack."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from redact_sensitive import redact


BEGIN_MARKER = "===== CTF_SOLVER_REGRESSION_BEGIN ====="
END_MARKER = "===== CTF_SOLVER_REGRESSION_END ====="
SECTIONS = (
    "git",
    "secret_scan",
    "pytest",
    "doctor",
    "update_metrics",
    "dump_mcp_tools",
    "redact_self_test",
    "offline_e2e_ctfd",
    "offline_e2e_dreamhack",
    "compileall",
    "git_diff_check",
)
QUICK_TESTS = (
    "tests/test_secret_scan.py",
    "tests/test_redact_sensitive.py",
    "tests/test_metrics_safety.py",
    "tests/test_shortcuts.py",
    "tests/test_offline_e2e_smoke.py",
)
SCRUB_ENV_KEYS = (
    "CTF_DOCTOR_INSPECT_CLAUDE_CONFIG",
    "CTF_CTFD_COOKIE_FILE",
    "CTF_CTFD_COOKIE_HEADER",
    "CTF_DREAMHACK_SESSION_ID",
    "CTF_DREAMHACK_CSRF_TOKEN",
    "DREAMHACK_SESSION_ID",
    "DREAMHACK_CSRF_TOKEN",
)


@dataclass
class StepResult:
    name: str
    ok: bool
    returncode: int
    duration_sec: float
    lines: list[str]


def _safe_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in SCRUB_ENV_KEYS:
        env.pop(key, None)
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("CTF_REGRESSION_COMMAND_PACK", "1")
    return env


def _bounded_lines(text: str, *, max_lines: int = 40, max_chars: int = 8000) -> list[str]:
    safe = redact(text)
    if len(safe) > max_chars:
        safe = safe[-max_chars:]
    lines = [line.rstrip() for line in safe.splitlines() if line.rstrip()]
    if len(lines) > max_lines:
        return [f"... truncated {len(lines) - max_lines} lines ...", *lines[-max_lines:]]
    return lines


def _run(
    name: str,
    command: list[str],
    *,
    timeout: int = 120,
    include_output: bool = True,
    env: dict[str, str] | None = None,
) -> StepResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env or _safe_env(),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        duration = time.monotonic() - started
        lines = [f"command={' '.join(command)}", f"returncode={result.returncode}", f"duration_sec={duration:.2f}"]
        if include_output and result.returncode != 0:
            lines.extend(_bounded_lines((result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")))
        return StepResult(name, result.returncode == 0, result.returncode, duration, lines)
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        lines = [f"command={' '.join(command)}", "returncode=timeout", f"duration_sec={duration:.2f}"]
        if include_output:
            out = (exc.stdout or "") + ("\n" if exc.stdout and exc.stderr else "") + (exc.stderr or "")
            lines.extend(_bounded_lines(out))
        return StepResult(name, False, 124, duration, lines)


def _run_capture_line(command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        env=_safe_env(),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return redact((result.stdout or result.stderr).strip().splitlines()[0]) if (result.stdout or result.stderr).strip() else ""


def _git_step() -> StepResult:
    started = time.monotonic()
    branch = _run_capture_line(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    head = _run_capture_line(["git", "log", "-1", "--oneline"])
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(ROOT),
        env=_safe_env(),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    ok = bool(branch and head and status.returncode == 0)
    dirty = len([line for line in status.stdout.splitlines() if line.strip()]) if status.returncode == 0 else 0
    return StepResult(
        "git",
        ok,
        0 if ok else 1,
        time.monotonic() - started,
        [
            f"branch={branch or 'unknown'}",
            f"head={head or 'unknown'}",
            f"dirty_entries={dirty}",
            "dirty_entries_are_info_only=true",
        ],
    )


def _secret_scan_step() -> StepResult:
    started = time.monotonic()
    commands = [
        [sys.executable, "scripts/secret_scan.py", "--strict", "--json"],
        [sys.executable, "scripts/secret_scan.py", "--strict", "--include-untracked", "--json"],
    ]
    ok = True
    lines: list[str] = []
    returncode = 0
    for command in commands:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=_safe_env(),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        returncode = result.returncode if result.returncode != 0 else returncode
        label = "include_untracked" if "--include-untracked" in command else "tracked"
        try:
            data = json.loads(result.stdout)
            findings = data.get("findings") if isinstance(data, dict) else []
            lines.append(f"{label}_ok={str(result.returncode == 0).lower()}")
            lines.append(f"{label}_findings={len(findings) if isinstance(findings, list) else 'unknown'}")
            if result.returncode != 0 and isinstance(findings, list):
                for finding in findings[:20]:
                    if isinstance(finding, dict):
                        path = redact(str(finding.get("path", "unknown")))
                        line = str(finding.get("line", "unknown"))
                        rule = str(finding.get("rule", "unknown"))
                        lines.append(f"- {path}:{line}:{rule}")
        except json.JSONDecodeError:
            lines.append(f"{label}_ok=false")
            lines.extend(_bounded_lines(result.stdout + result.stderr))
        ok = ok and result.returncode == 0
    return StepResult("secret_scan", ok, returncode, time.monotonic() - started, lines)


def _pytest_step(quick: bool) -> StepResult:
    if quick:
        command = [sys.executable, "-m", "pytest", *QUICK_TESTS, "-q"]
        return _run("pytest", command, timeout=180)
    return _run("pytest", [sys.executable, "-m", "pytest", "tests"], timeout=600)


def _simple_ok_step(name: str, command: list[str], *, timeout: int = 120, include_output: bool = True) -> StepResult:
    return _run(name, command, timeout=timeout, include_output=include_output)


def _redact_self_test_step() -> StepResult:
    result = _run("redact_self_test", [sys.executable, "scripts/redact_sensitive.py", "--self-test"], timeout=30, include_output=False)
    result.lines.append(f"self_test={'ok' if result.ok else 'failed'}")
    return result


def _offline_e2e_step(platform: str, skip: bool) -> StepResult:
    if skip:
        return StepResult(f"offline_e2e_{platform}", True, 0, 0.0, ["skipped=true"])
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "scripts/offline_e2e_smoke.py", "--platform", platform, "--json"],
        cwd=str(ROOT),
        env=_safe_env(),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    lines = [f"returncode={result.returncode}", f"duration_sec={time.monotonic() - started:.2f}"]
    try:
        data = json.loads(result.stdout)
        lines.extend(
            [
                f"ok={str(bool(data.get('ok'))).lower()}",
                f"platform={platform}",
                f"discovery_ok={str(bool(data.get('discovery_ok'))).lower()}",
                f"finalize_ok={str(bool(data.get('finalize_ok'))).lower()}",
                f"metrics_ok={str(bool(data.get('metrics_ok'))).lower()}",
                f"cleanup_ok={str(bool(data.get('cleanup_ok'))).lower()}",
                f"public_safe_ok={str(bool(data.get('public_safe_ok'))).lower()}",
            ]
        )
        if not data.get("ok") and data.get("reason"):
            lines.append(f"reason={redact(str(data.get('reason')))}")
    except json.JSONDecodeError:
        lines.extend(_bounded_lines(result.stdout + result.stderr))
    return StepResult(f"offline_e2e_{platform}", result.returncode == 0, result.returncode, time.monotonic() - started, lines)


def _git_diff_check_step() -> StepResult:
    started = time.monotonic()
    commands = [
        ("worktree", ["git", "diff", "--check"]),
        ("staged", ["git", "diff", "--cached", "--check"]),
    ]
    ok = True
    returncode = 0
    lines: list[str] = []
    for label, command in commands:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=_safe_env(),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        ok = ok and result.returncode == 0
        returncode = result.returncode if result.returncode != 0 else returncode
        lines.append(f"{label}_ok={str(result.returncode == 0).lower()}")
        if result.returncode != 0:
            lines.extend(_bounded_lines(result.stdout + result.stderr))
    return StepResult("git_diff_check", ok, returncode, time.monotonic() - started, lines)


def _print_step(step: StepResult) -> None:
    print(f"[{step.name}]")
    print(f"ok={str(step.ok).lower()}")
    for line in step.lines:
        print(line)


def run_pack(args: argparse.Namespace) -> list[StepResult]:
    return [
        _git_step(),
        _secret_scan_step(),
        _pytest_step(args.quick),
        _simple_ok_step("doctor", [sys.executable, "scripts/doctor.py"], timeout=120),
        _simple_ok_step("update_metrics", [sys.executable, "scripts/update_metrics.py", "--check"], timeout=60),
        _simple_ok_step("dump_mcp_tools", [sys.executable, "scripts/dump_mcp_tools.py", "--check"], timeout=60),
        _redact_self_test_step(),
        _offline_e2e_step("ctfd", args.skip_offline_e2e),
        _offline_e2e_step("dreamhack", args.skip_offline_e2e),
        _simple_ok_step(
            "compileall",
            [sys.executable, "-m", "compileall", "-q", "tools", "server.py", "scripts", "ctf_solver_core"],
            timeout=120,
        ),
        _git_diff_check_step(),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="run selected pytest files instead of the full tests directory")
    parser.add_argument("--skip-offline-e2e", action="store_true", help="skip fixture-only offline E2E smoke stages")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    steps = run_pack(args)
    print(BEGIN_MARKER)
    for step in steps:
        _print_step(step)
    print(END_MARKER)
    return 0 if all(step.ok for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
