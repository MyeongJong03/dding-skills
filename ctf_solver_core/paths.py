"""Portable path resolution for lifecycle scripts."""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    path = Path(raw).expanduser() if raw else default
    return path.resolve()


def repo_root() -> Path:
    raw = os.environ.get("CTF_SOLVER_REPO_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def work_root() -> Path:
    return _env_path("CTF_WORK_ROOT", Path.home() / "CTF" / "work")


def local_run_root() -> Path:
    return _env_path("CTF_LOCAL_RUN_ROOT", Path.home() / ".ctf-solver" / "runs")


def lock_root() -> Path:
    return _env_path("CTF_LOCK_ROOT", Path.home() / ".ctf-solver" / "locks")


def lease_root() -> Path:
    return _env_path("CTF_LEASE_ROOT", Path.home() / ".ctf-solver" / "leases")


def queue_root() -> Path:
    return _env_path("CTF_QUEUE_ROOT", Path.home() / ".ctf-solver" / "queue")


def solved_writeup_root() -> Path:
    return _env_path("CTF_SOLVED_WRITEUP_ROOT", Path.home() / "SolvedWriteUp")


def metrics_root() -> Path:
    return repo_root() / "metrics"


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def is_inside_repo(path: Path) -> bool:
    return is_relative_to(path, repo_root())


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    try:
        return str(Path("~") / resolved.relative_to(home))
    except ValueError:
        return str(resolved)
