#!/usr/bin/env python3
"""Commit and optionally push public-safe ctf-solver repository changes."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ctf_solver_core.locks import DirectoryLock
from ctf_solver_core.paths import repo_root
from ctf_solver_core.schemas import json_dumps
from redact_sensitive import redact
from update_metrics import check_public_metrics


ALLOWED_PATHS = [
    "metrics",
    "skills",
    "memory",
    "docs",
    "config",
    "scripts",
    "tools",
    "ctf_solver_core",
    "Dockerfile.ctf",
    "README.md",
    "GUIDE.md",
    "install.sh",
    "requirements.txt",
    "server.py",
    ".gitignore",
]
BLOCKED_MARKERS = (
    "SolvedWriteUp",
    ".ctf-solver",
    "private-runs",
    "runs/private",
    "raw-transcript",
    "raw_transcript",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-message", default="Update public CTF solver metrics")
    parser.add_argument("--push", action="store_true", help="push after commit")
    parser.add_argument("--no-push", action="store_true", help="never push, even if CTF_AUTO_PUSH=1")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _git(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root(),
        text=True,
        capture_output=capture,
        timeout=60,
        check=False,
    )


def _existing_allowed_paths() -> list[str]:
    root = repo_root()
    return [path for path in ALLOWED_PATHS if (root / path).exists()]


def _status(paths: list[str]) -> str:
    result = _git(["status", "--porcelain", "--", *paths])
    return result.stdout


def _staged_files() -> list[str]:
    result = _git(["diff", "--cached", "--name-only"])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _scan_staged_diff() -> None:
    diff = _git(["diff", "--cached"], capture=True).stdout
    if redact(diff) != diff:
        raise RuntimeError("secret scan rejected staged diff")
    for path in _staged_files():
        if any(marker in path for marker in BLOCKED_MARKERS):
            raise RuntimeError(f"blocked private path staged for commit: {path}")


def git_sync(args: argparse.Namespace) -> dict[str, object]:
    metrics_errors = check_public_metrics()
    if metrics_errors:
        raise RuntimeError("public metrics check failed: " + "; ".join(metrics_errors))

    with DirectoryLock("git-sync", "git metrics/docs sync", wait_seconds=120):
        paths = _existing_allowed_paths()
        status_before = _status(paths)
        result: dict[str, object] = {
            "dry_run": args.dry_run,
            "allowed_paths": paths,
            "status_before": status_before,
            "committed": False,
            "pushed": False,
        }
        if args.dry_run:
            return result

        add = _git(["add", "--", *paths])
        if add.returncode != 0:
            raise RuntimeError(add.stderr.strip() or "git add failed")

        _scan_staged_diff()
        staged = _staged_files()
        result["staged_files"] = staged
        if staged:
            commit = _git(["commit", "-m", args.commit_message])
            if commit.returncode != 0:
                raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
            result["committed"] = True
            result["commit_output"] = commit.stdout.strip()

        push_allowed = args.push or (os.environ.get("CTF_AUTO_PUSH") == "1" and not args.no_push)
        if push_allowed:
            push = _git(["push"])
            if push.returncode != 0:
                raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push failed")
            result["pushed"] = True
    return result


def main() -> int:
    args = build_parser().parse_args()
    result = git_sync(args)
    print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

