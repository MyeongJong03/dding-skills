#!/usr/bin/env python3
"""Minimal P0 consistency doctor for the ctf-solver repo."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MCP_NAME = "ctf_solver"
LEGACY_MCP_NAME = "".join(("dreamhack", "_solver"))


class Doctor:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, message: str) -> None:
        print(f"[OK] {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"[WARN] {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"[FAIL] {message}")

    def require_file(self, relative: str) -> bool:
        path = ROOT / relative
        if path.is_file():
            self.ok(f"{relative} exists")
            return True
        self.fail(f"{relative} missing")
        return False

    def run_syntax(self, relative: str) -> None:
        path = ROOT / relative
        if not path.is_file():
            self.fail(f"{relative} missing")
            return
        result = subprocess.run(
            ["bash", "-n", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            self.ok(f"{relative} syntax ok")
        else:
            self.fail(f"{relative} syntax failed: {result.stderr.strip()}")

    def command_version(self, name: str, optional: bool) -> None:
        path = shutil.which(name)
        if not path:
            if optional:
                self.warn(f"{name} CLI not found (optional)")
            else:
                self.fail(f"{name} CLI not found")
            return

        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = (result.stdout or result.stderr).strip().splitlines()
        suffix = f": {version[0]}" if version else ""
        self.ok(f"{name} CLI found at {path}{suffix}")

    def docker_status(self) -> None:
        docker = shutil.which("docker")
        if not docker:
            self.warn("Docker CLI not found (optional runtime dependency)")
            return
        self.ok(f"Docker CLI found at {docker}")
        result = subprocess.run(
            [docker, "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            self.ok("Docker daemon reachable")
        else:
            self.warn("Docker daemon off or unreachable (optional runtime dependency)")

    def check_tools(self) -> None:
        tools = sorted((ROOT / "tools").glob("*.py"))
        tools = [path for path in tools if path.name != "__init__.py"]
        if tools:
            self.ok(f"tools/*.py present ({len(tools)} files)")
        else:
            self.fail("tools/*.py missing")

    def check_agents_generation(self) -> None:
        required = [
            "config/deploy.sh",
            "config/CLAUDE.base.md",
            "config/mac/env.md",
            "config/windows/env.md",
        ]
        if all((ROOT / item).is_file() for item in required):
            self.ok("AGENTS.md generation is available through config/deploy.sh")
        else:
            self.fail("AGENTS.md generation prerequisites are incomplete")

    def check_mcp_names(self) -> None:
        server = (ROOT / "server.py").read_text(encoding="utf-8")
        if f'FastMCP("{CANONICAL_MCP_NAME}")' in server:
            self.ok(f"server.py MCP name is {CANONICAL_MCP_NAME}")
        else:
            self.fail(f"server.py MCP name is not {CANONICAL_MCP_NAME}")

        checked_paths = [
            ROOT / "README.md",
            ROOT / "GUIDE.md",
            ROOT / "install.sh",
            ROOT / "server.py",
            ROOT / "config" / "CLAUDE.base.md",
        ]
        docs_dir = ROOT / "docs"
        if docs_dir.is_dir():
            checked_paths.extend(sorted(docs_dir.glob("*.md")))

        stale = []
        for path in checked_paths:
            if path.is_file() and LEGACY_MCP_NAME in path.read_text(encoding="utf-8", errors="replace"):
                stale.append(str(path.relative_to(ROOT)))
        if stale:
            self.warn(
                f"legacy MCP server name {LEGACY_MCP_NAME} detected; "
                f"prefer {CANONICAL_MCP_NAME}: " + ", ".join(stale)
            )
        else:
            self.ok("MCP server-name strings are consistent")

    def summary(self) -> int:
        print("")
        print(f"Hard failures: {len(self.failures)}")
        print(f"Optional warnings: {len(self.warnings)}")
        return 1 if self.failures else 0


def main() -> int:
    doctor = Doctor()
    if not (ROOT / ".git").is_dir():
        doctor.fail(f"{ROOT} is not a git repo")
    else:
        doctor.ok(f"repo root: {ROOT}")

    for relative in [
        "install.sh",
        "config/deploy.sh",
        "config/CLAUDE.base.md",
        "config/mac/env.md",
        "config/windows/env.md",
        "Dockerfile.ctf",
        "server.py",
    ]:
        doctor.require_file(relative)

    doctor.check_agents_generation()
    doctor.run_syntax("install.sh")
    doctor.run_syntax("config/deploy.sh")
    doctor.check_tools()
    doctor.docker_status()
    doctor.command_version("codex", optional=True)
    doctor.command_version("claude", optional=True)
    doctor.check_mcp_names()

    return doctor.summary()


if __name__ == "__main__":
    raise SystemExit(main())
