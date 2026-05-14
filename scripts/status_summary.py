#!/usr/bin/env python3
"""Public-safe marker status summary for the ctf-solver repo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import secret_scan
from redact_sensitive import redact


BEGIN_MARKER = "===== CTF_SOLVER_STATUS_BEGIN ====="
END_MARKER = "===== CTF_SOLVER_STATUS_END ====="
SECTIONS = (
    "git",
    "docker",
    "mcp_json_summary",
    "mcp_live",
    "redaction",
    "repo_raw_grep",
    "doctor",
)
CANONICAL_MCP_NAME = "ctf_solver"
LEGACY_MCP_NAME = "".join(("dreamhack", "_solver"))
P1_15_FILES = (
    "scripts/offline_e2e_smoke.py",
    "docs/offline-e2e-smoke.md",
    "tests/test_offline_e2e_smoke.py",
)
NEW_COMMAND_FILES = (
    "scripts/status_summary.py",
    "scripts/regression_check.py",
    "docs/regression.md",
)
SENSITIVE_GREP_TERMS = (
    "mcpServers",
    "oauth" + "Account",
    "email" + "Address",
    "account" + "Uuid",
    "organization" + "Uuid",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    r"Authorization[[:space:]]*:[[:space:]]*Bearer",
    r"Cookie[[:space:]]*:",
)
SENSITIVE_GREP = "|".join(SENSITIVE_GREP_TERMS)


def _run(command: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _one_line(text: str) -> str:
    return redact(text).strip().splitlines()[0] if text.strip() else ""


def _git_tracked(relative: str) -> bool:
    result = _run(["git", "ls-files", "--error-unmatch", relative], timeout=5)
    return result.returncode == 0


def _collect_mcp_server_names(node: object) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        servers = node.get("mcpServers")
        if isinstance(servers, dict):
            names.update(str(name) for name in servers.keys())
        for value in node.values():
            names.update(_collect_mcp_server_names(value))
    elif isinstance(node, list):
        for item in node:
            names.update(_collect_mcp_server_names(item))
    return names


def _status_git() -> dict[str, Any]:
    section: dict[str, Any] = {"ok": True}
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=5)
    head = _run(["git", "log", "-1", "--oneline"], timeout=5)
    status = _run(["git", "status", "--short"], timeout=5)
    if branch.returncode != 0 or head.returncode != 0 or status.returncode != 0:
        section["ok"] = False
        section["reason"] = _one_line(branch.stderr or head.stderr or status.stderr or "git failed")
        return section
    section["branch"] = _one_line(branch.stdout)
    section["head"] = _one_line(head.stdout)
    section["dirty_entries"] = len([line for line in status.stdout.splitlines() if line.strip()])
    section["p1_15_tracked"] = {relative: _git_tracked(relative) for relative in P1_15_FILES}
    return section


def _status_docker() -> dict[str, Any]:
    docker = shutil.which("docker")
    section: dict[str, Any] = {
        "ok": True,
        "cli": bool(docker),
        "daemon": "not_checked",
        "ctf_pwn_image": "missing_optional",
    }
    if not docker:
        section["daemon"] = "skipped"
        return section
    info = _run([docker, "info"], timeout=8)
    if info.returncode == 0:
        section["daemon"] = "reachable"
        image = _run([docker, "image", "inspect", "ctf-pwn:latest"], timeout=8)
        section["ctf_pwn_image"] = "present" if image.returncode == 0 else "missing_optional"
    else:
        section["daemon"] = "unreachable_optional"
    return section


def _status_mcp_json_summary() -> dict[str, Any]:
    config = Path.home() / ".claude.json"
    section: dict[str, Any] = {"ok": True, "claude_json": "missing", "mcp_server_names": []}
    if not config.is_file():
        return section
    section["claude_json"] = "present"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        section["ok"] = False
        section["reason"] = exc.__class__.__name__
        return section
    names = sorted(_collect_mcp_server_names(data))
    section["mcp_server_names"] = names
    section["canonical_registered"] = CANONICAL_MCP_NAME in names
    section["legacy_registered"] = LEGACY_MCP_NAME in names
    return section


def _status_mcp_live() -> dict[str, Any]:
    section: dict[str, Any] = {"ok": True}
    server = ROOT / "server.py"
    text = server.read_text(encoding="utf-8", errors="replace") if server.is_file() else ""
    section["server_py"] = "present" if server.is_file() else "missing"
    section["canonical_name"] = f'FastMCP("{CANONICAL_MCP_NAME}")' in text
    try:
        import dump_mcp_tools

        tools = dump_mcp_tools.collect_tools()
        section["tool_count"] = len(tools)
        section["docs_tools_check"] = _run([sys.executable, "scripts/dump_mcp_tools.py", "--check"], timeout=15).returncode == 0
    except Exception as exc:  # noqa: BLE001 - status summaries must stay bounded.
        section["ok"] = False
        section["reason"] = exc.__class__.__name__
    if not section.get("canonical_name") or not section.get("docs_tools_check"):
        section["ok"] = False
    return section


def _grep_locations(limit: int = 30) -> dict[str, Any]:
    result = _run(["git", "grep", "-n", "-I", "-E", SENSITIVE_GREP, "--"], timeout=15)
    locations: list[str] = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 2:
                locations.append(redact(f"{parts[0]}:{parts[1]}"))
    elif result.returncode not in (1,):
        return {"ok": False, "reason": _one_line(result.stderr or "git grep failed"), "locations": []}
    return {
        "ok": True,
        "location_count": len(locations),
        "locations": locations[:limit],
        "truncated": len(locations) > limit,
    }


def _secret_scan_locations(limit: int = 30) -> dict[str, Any]:
    try:
        findings = secret_scan.scan_paths(secret_scan._git_ls_files(ROOT), root=ROOT)  # noqa: SLF001 - CLI reuse.
    except Exception as exc:  # noqa: BLE001 - status summaries must stay bounded.
        return {"ok": False, "reason": exc.__class__.__name__, "locations": []}
    locations = [
        redact(f"{finding.get('path', 'unknown')}:{finding.get('line', 'unknown')}:{finding.get('rule', 'unknown')}")
        for finding in findings
    ]
    return {
        "ok": True,
        "location_count": len(locations),
        "locations": locations[:limit],
        "truncated": len(locations) > limit,
    }


def _status_grep_summary(*, result: str, verbose: bool) -> dict[str, Any]:
    grep = _grep_locations()
    if not grep.get("ok"):
        return {
            "ok": False,
            "clean": False,
            "result": f"{result} failed",
            "reason": grep.get("reason", "git grep failed"),
        }

    findings = _secret_scan_locations()
    if not findings.get("ok"):
        return {
            "ok": False,
            "clean": False,
            "result": f"{result} failed",
            "reason": findings.get("reason", "secret scan failed"),
        }

    if int(findings.get("location_count", 0)):
        return {
            "ok": False,
            "clean": False,
            "result": f"{result} findings",
            "location_count": findings["location_count"],
            "locations": findings["locations"],
            "truncated": findings["truncated"],
        }

    section: dict[str, Any] = {"ok": True, "clean": True, "result": f"{result} clean"}
    if verbose:
        section.update(
            {
                "location_count": grep["location_count"],
                "locations": grep["locations"],
                "truncated": grep["truncated"],
            }
        )
    return section


def _status_doctor() -> dict[str, Any]:
    required = {relative: (ROOT / relative).is_file() for relative in NEW_COMMAND_FILES}
    section: dict[str, Any] = {
        "ok": all(required.values()),
        "required_files": required,
        "full_doctor": "skipped_fast_status_summary",
    }
    return section


def collect_status(*, verbose: bool = False) -> dict[str, Any]:
    raw = {
        "git": _status_git(),
        "docker": _status_docker(),
        "mcp_json_summary": _status_mcp_json_summary(),
        "mcp_live": _status_mcp_live(),
        "redaction": _status_grep_summary(result="redacted grep", verbose=verbose),
        "repo_raw_grep": _status_grep_summary(result="repo raw grep", verbose=verbose),
        "doctor": _status_doctor(),
    }
    raw["ok"] = all(bool(raw[name].get("ok", False)) for name in SECTIONS)
    return raw


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    if isinstance(value, dict):
        return ", ".join(f"{key}={_format_value(item)}" for key, item in value.items())
    return str(value)


def print_marker_summary(status: dict[str, Any]) -> None:
    print(BEGIN_MARKER)
    for name in SECTIONS:
        print(f"[{name}]")
        section = status.get(name)
        if not isinstance(section, dict):
            print("ok=false")
            continue
        for key in sorted(section):
            if key == "clean":
                continue
            value = section[key]
            if key == "locations" and isinstance(value, list):
                print(f"{key}_shown={len(value)}")
                for item in value:
                    print(f"- {item}")
                continue
            print(f"{key}={_format_value(value)}")
    print(END_MARKER)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print public-safe structured status")
    parser.add_argument("--verbose", action="store_true", help="include benign grep locations in clean sections")
    args = parser.parse_args()
    status = collect_status(verbose=args.verbose)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_marker_summary(status)
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
