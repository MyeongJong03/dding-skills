from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from conftest import REPO_ROOT


def _git_init_and_add(root: Path, files: list[Path]) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "--", *[str(path.relative_to(root)) for path in files]], cwd=root, check=True)


def test_secret_scan_detects_tracked_secret_without_printing_value(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    secret_file = repo / "leak.txt"
    secret_value = "sk-testaaaaaaaaaaaaaaaaaaaaaaaa"
    secret_file.write_text(f"OPENAI_API_KEY={secret_value}\n", encoding="utf-8")
    _git_init_and_add(repo, [secret_file])

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "secret_scan.py"), "--root", str(repo), "--strict"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "leak.txt:1:" in result.stdout
    assert "openai_api_key_assignment" in result.stdout
    assert secret_value not in result.stdout
    assert secret_value not in result.stderr


def test_secret_scan_allows_redaction_self_test_and_scan_test_fixtures(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    fixture_path = repo / "tests" / "test_secret_scan.py"
    fixture_path.parent.mkdir(parents=True)
    fixture_path.write_text(
        "DUMMY = 'OPENAI_API_KEY=sk-testbbbbbbbbbbbbbbbbbbbb'\n"
        "DUMMY_COOKIE = 'Cookie: session=fake_session_cookie'\n",
        encoding="utf-8",
    )
    _git_init_and_add(repo, [fixture_path])

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "secret_scan.py"), "--root", str(repo), "--strict"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    assert "OK: secret scan clean" in result.stdout


def test_current_repo_secret_scan_strict_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "secret_scan.py"), "--strict"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
