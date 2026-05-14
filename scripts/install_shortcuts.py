#!/usr/bin/env python3
"""Install short local operator commands for ctf-solver."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BIN_DIR = Path("~/.local/bin")
INSTALLER = "scripts/install_shortcuts.py"
MANAGED_MARKER = "# ctf-solver-shortcut:"


@dataclass(frozen=True)
class Shortcut:
    name: str
    script: str
    args: tuple[str, ...] = ()

    @property
    def command_preview(self) -> str:
        parts = ["python3", str(ROOT / self.script), *self.args]
        return " ".join(shlex.quote(part) for part in parts)


SHORTCUTS = (
    Shortcut("ctf-status", "scripts/status_summary.py"),
    Shortcut("ctf-check", "scripts/regression_check.py", ("--quick",)),
    Shortcut("ctf-regression", "scripts/regression_check.py"),
)


def _shell_quote(value: str) -> str:
    return shlex.quote(value)


def _wrapper_text(shortcut: Shortcut) -> str:
    script = ROOT / shortcut.script
    args = " ".join(_shell_quote(arg) for arg in shortcut.args)
    if args:
        args = f" {args}"
    return (
        "#!/bin/sh\n"
        f"{MANAGED_MARKER} {shortcut.name}\n"
        f"# generated-by: {INSTALLER}\n"
        f"# repo-root: {ROOT}\n"
        f'exec python3 {_shell_quote(str(script))}{args} "$@"\n'
    )


def _is_managed(path: Path, shortcut: Shortcut) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return f"{MANAGED_MARKER} {shortcut.name}" in text and f"generated-by: {INSTALLER}" in text


def _mode_string(mode: int) -> str:
    return oct(stat.S_IMODE(mode))


def install_shortcuts(bin_dir: Path, *, dry_run: bool, force: bool) -> int:
    failures = 0
    if dry_run:
        print(f"[dry-run] ensure directory {bin_dir}")
    else:
        bin_dir.mkdir(parents=True, exist_ok=True)

    for shortcut in SHORTCUTS:
        target = bin_dir / shortcut.name
        text = _wrapper_text(shortcut)
        if target.exists() and not _is_managed(target, shortcut) and not force:
            print(f"[skip] {target} exists and is not managed by {INSTALLER}; use --force to replace")
            failures += 1
            continue
        if dry_run:
            action = "replace" if target.exists() else "install"
            print(f"[dry-run] {action} {target} -> {shortcut.command_preview}")
            continue
        target.write_text(text, encoding="utf-8")
        target.chmod(0o755)
        mode = _mode_string(target.stat().st_mode)
        print(f"[ok] installed {target} -> {shortcut.command_preview} mode={mode}")

    _print_path_hint(bin_dir)
    return 1 if failures else 0


def uninstall_shortcuts(bin_dir: Path, *, dry_run: bool, force: bool) -> int:
    failures = 0
    for shortcut in SHORTCUTS:
        target = bin_dir / shortcut.name
        if not target.exists():
            print(f"[ok] absent {target}")
            continue
        if not _is_managed(target, shortcut) and not force:
            print(f"[skip] {target} exists and is not managed by {INSTALLER}; use --force to remove")
            failures += 1
            continue
        if dry_run:
            print(f"[dry-run] remove {target}")
            continue
        target.unlink()
        print(f"[ok] removed {target}")
    return 1 if failures else 0


def _print_path_hint(bin_dir: Path) -> None:
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if str(bin_dir) in path_entries:
        print(f"[info] {bin_dir} is already on PATH")
        return
    print(f"[info] add {bin_dir} to PATH if the shortcut commands are not found")
    print('       zsh example: export PATH="$HOME/.local/bin:$PATH"')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bin-dir",
        default=str(DEFAULT_BIN_DIR),
        help="directory where wrapper commands are installed (default: ~/.local/bin)",
    )
    parser.add_argument("--uninstall", action="store_true", help="remove managed shortcut wrappers")
    parser.add_argument("--dry-run", action="store_true", help="show planned changes without writing files")
    parser.add_argument("--force", action="store_true", help="replace or remove existing unmanaged files")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bin_dir = Path(args.bin_dir).expanduser().resolve()
    mode = "uninstall" if args.uninstall else "install"
    print("ctf-solver operator shortcut installer")
    print(f"mode={mode}")
    print(f"repo_root={ROOT}")
    print(f"bin_dir={bin_dir}")
    if args.uninstall:
        return uninstall_shortcuts(bin_dir, dry_run=args.dry_run, force=args.force)
    return install_shortcuts(bin_dir, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
