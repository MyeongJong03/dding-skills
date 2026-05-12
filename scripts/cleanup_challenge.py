#!/usr/bin/env python3
"""Safely clean challenge scratch files."""

from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.paths import display_path, is_relative_to, repo_root, resolve_path
from ctf_solver_core.schemas import atomic_write_json, iso_now, json_dumps


DELETE_DIR_NAMES = {"__pycache__", ".pytest_cache", "scratch"}
DELETE_FILE_PATTERNS = ("*.tmp", "core", "core.*", "*.core", "*.fuzz", "fuzz-*.log")
PROTECTED_NAMES = {
    "writeup.md",
    "metadata.json",
    "challenge.json",
    "notes.md",
    "Dockerfile",
    "docker-compose.yml",
    "cleanup.json",
    "finalize.json",
    "run.json",
    "verifier.json",
    "verifier-output.txt",
}
PROTECTED_NAME_HINTS = ("final", "payload", "exploit", "solve", "solver", "original", "challenge")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="challenge workspace to clean")
    parser.add_argument("--run-dir", help="private run directory to clean")
    parser.add_argument("--apply", action="store_true", help="perform deletion; default is dry-run")
    parser.add_argument("--dry-run", action="store_true", help="force dry-run")
    return parser


def _dangerous_root(path: Path) -> bool:
    resolved = path.resolve()
    home = Path.home().resolve()
    return resolved in {Path(resolved.anchor), home, repo_root().resolve()}


def _protected(path: Path) -> bool:
    if path.name in PROTECTED_NAMES:
        return True
    lowered = path.name.lower()
    return any(hint in lowered for hint in PROTECTED_NAME_HINTS)


def _contains_protected(path: Path) -> bool:
    if _protected(path):
        return True
    if path.is_dir():
        for child in path.rglob("*"):
            if _protected(child):
                return True
    return False


def _candidate(path: Path) -> bool:
    if path.is_dir() and path.name in DELETE_DIR_NAMES:
        return True
    if path.is_file():
        return any(fnmatch.fnmatch(path.name, pattern) for pattern in DELETE_FILE_PATTERNS)
    return False


def _size(path: Path) -> int:
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file() or child.is_symlink():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def _collect_candidates(base: Path) -> tuple[list[Path], list[Path]]:
    candidates: list[Path] = []
    preserved: list[Path] = []
    for path in sorted(base.rglob("*"), key=lambda item: (len(item.parts), str(item))):
        if any(is_relative_to(path, parent) for parent in candidates if parent.is_dir()):
            continue
        if not _candidate(path):
            continue
        if _contains_protected(path):
            preserved.append(path)
            continue
        candidates.append(path)
    return candidates, preserved


def cleanup(args: argparse.Namespace) -> dict[str, object]:
    roots: list[Path] = []
    if args.workspace:
        roots.append(resolve_path(args.workspace))
    if args.run_dir:
        roots.append(resolve_path(args.run_dir))
    if not roots:
        raise ValueError("at least one of --workspace or --run-dir is required")

    dry_run = args.dry_run or not args.apply
    candidates: list[Path] = []
    preserved: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if _dangerous_root(root):
            raise ValueError(f"refusing to clean dangerous root: {root}")
        found, kept = _collect_candidates(root)
        for path in found + kept:
            if not is_relative_to(path, root):
                raise ValueError(f"refusing path outside cleanup root: {path}")
        candidates.extend(found)
        preserved.extend(kept)

    bytes_estimate = sum(_size(path) for path in candidates)
    deleted: list[Path] = []
    if not dry_run:
        for path in sorted(candidates, key=lambda item: len(item.parts), reverse=True):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            deleted.append(path)

    result = {
        "generated_at": iso_now(),
        "dry_run": dry_run,
        "bytes_deleted": 0 if dry_run else bytes_estimate,
        "bytes_estimate": bytes_estimate,
        "files_deleted": [str(path) for path in deleted],
        "delete_candidates": [str(path) for path in candidates],
        "preserved_files": [str(path) for path in preserved],
    }

    output_root = resolve_path(args.run_dir) if args.run_dir else roots[0]
    if not dry_run or args.run_dir:
        atomic_write_json(output_root / "cleanup.json", result)
    return {
        **result,
        "display_roots": [display_path(path) for path in roots],
    }


def main() -> int:
    args = build_parser().parse_args()
    result = cleanup(args)
    print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
