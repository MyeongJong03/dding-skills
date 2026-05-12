from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ctf-pwn:latest"


def _run(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _skip_unless_docker_gdb_ready() -> None:
    if os.environ.get("CTF_RUN_DOCKER_GDB_TESTS") != "1":
        pytest.skip("set CTF_RUN_DOCKER_GDB_TESTS=1 to run Docker GDB smoke tests")
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker CLI not found")
    if _run([docker, "info"], timeout=10).returncode != 0:
        pytest.skip("Docker daemon is not reachable")
    if _run([docker, "image", "inspect", IMAGE], timeout=10).returncode != 0:
        pytest.skip(f"Docker image {IMAGE} is not available")
    compiler = _run(
        [
            docker,
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--network",
            "none",
            IMAGE,
            "bash",
            "-lc",
            "command -v gcc >/dev/null 2>&1 || command -v cc >/dev/null 2>&1",
        ],
        timeout=20,
    )
    if compiler.returncode != 0:
        pytest.skip(f"gcc/cc is not available inside {IMAGE}")


def test_docker_gdb_smoke_runtime(tmp_path: Path) -> None:
    _skip_unless_docker_gdb_ready()
    env = os.environ.copy()
    env.update(
        {
            "CTF_GDB_ROOT": str(tmp_path / "gdb"),
            "CTF_GDB_ARTIFACT_ROOT": str(tmp_path / "gdb-artifacts"),
            "CTF_GDB_SMOKE_TMP_ROOT": str(tmp_path / "gdb-smoke-tmp"),
            "CTF_SESSION_ROOT": str(tmp_path / "sessions"),
            "CTF_SESSIOND_ROOT": str(tmp_path / "sessiond"),
        }
    )
    try:
        result = subprocess.run(
            [sys.executable, "scripts/gdb_docker_smoke.py", "--json"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        if data["status"] == "skipped":
            pytest.skip(str(data["reason"]))
        assert data["status"] == "passed"
        assert data["ok"] is True
        assert data["gdb"]["crashed"] is True
        assert data["gdb"]["signal"] == "SIGSEGV"
        assert (
            data["gdb"]["register_count"]
            or data["gdb"]["backtrace_frame_count"]
            or data["gdb"]["vmmap_count"]
        )
        assert data["roots"]["gdb_root_inside_repo"] is False
        assert data["roots"]["gdb_artifact_root_inside_repo"] is False
        assert "/Users/" not in result.stdout
        assert "\\Users\\" not in result.stdout
        for name in ("gdb", "gdb-artifacts", "gdb-smoke-tmp", "sessions", "sessiond"):
            assert not (REPO_ROOT / name).exists()
    finally:
        subprocess.run(
            [sys.executable, "scripts/session_daemon.py", "stop", "--json"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
