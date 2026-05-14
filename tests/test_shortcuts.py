from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys

from conftest import REPO_ROOT


def _run_shortcut_installer(
    bin_dir: Path,
    *extra: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/install_shortcuts.py", "--bin-dir", str(bin_dir), *extra],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_install_shortcuts_dry_run_does_not_write(temp_ctf_env) -> None:
    bin_dir = temp_ctf_env.base / "operator-bin"
    result = _run_shortcut_installer(bin_dir, "--dry-run", env=temp_ctf_env.env)

    assert result.returncode == 0
    assert "[dry-run] ensure directory" in result.stdout
    assert "ctf-status" in result.stdout
    assert "ctf-check" in result.stdout
    assert "ctf-regression" in result.stdout
    assert not bin_dir.exists()


def test_install_shortcuts_install_wrappers_and_uninstall(temp_ctf_env) -> None:
    bin_dir = temp_ctf_env.base / "operator-bin"
    install = _run_shortcut_installer(bin_dir, env=temp_ctf_env.env)

    assert install.returncode == 0, install.stdout + install.stderr
    wrappers = {
        "ctf-status": "status_summary.py",
        "ctf-check": "--quick",
        "ctf-regression": "regression_check.py",
    }
    for name, expected in wrappers.items():
        path = bin_dir / name
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o755
        text = path.read_text(encoding="utf-8")
        assert f"ctf-solver-shortcut: {name}" in text
        assert "generated-by: scripts/install_shortcuts.py" in text
        assert "exec python3" in text
        assert expected in text
        for forbidden in (
            "OPENAI" + "_API_KEY",
            "ANTHROPIC" + "_API_KEY",
            "Authorization" + ": Bearer",
            "Cookie" + ":",
            "DH" + "{",
            "mcpServers",
        ):
            assert forbidden not in text

    help_env = dict(temp_ctf_env.env)
    help_env["PATH"] = str(bin_dir) + os.pathsep + help_env.get("PATH", "")
    status = subprocess.run(
        ["ctf-status", "--help"],
        cwd=REPO_ROOT,
        env=help_env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert status.returncode == 0
    assert "marker status summary" in status.stdout
    check = subprocess.run(
        ["ctf-check", "--help"],
        cwd=REPO_ROOT,
        env=help_env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert check.returncode == 0
    assert "--quick" in check.stdout

    uninstall_preview = _run_shortcut_installer(bin_dir, "--uninstall", "--dry-run", env=temp_ctf_env.env)
    assert uninstall_preview.returncode == 0
    assert "[dry-run] remove" in uninstall_preview.stdout
    assert all((bin_dir / name).exists() for name in wrappers)

    uninstall = _run_shortcut_installer(bin_dir, "--uninstall", env=temp_ctf_env.env)
    assert uninstall.returncode == 0, uninstall.stdout + uninstall.stderr
    assert all(not (bin_dir / name).exists() for name in wrappers)


def test_install_shortcuts_refuses_unmanaged_conflict_without_force(temp_ctf_env) -> None:
    bin_dir = temp_ctf_env.base / "operator-bin"
    bin_dir.mkdir(parents=True)
    conflict = bin_dir / "ctf-status"
    conflict.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")

    result = _run_shortcut_installer(bin_dir, env=temp_ctf_env.env)

    assert result.returncode == 1
    assert "not managed" in result.stdout
    assert conflict.read_text(encoding="utf-8") == "#!/bin/sh\nexit 7\n"
