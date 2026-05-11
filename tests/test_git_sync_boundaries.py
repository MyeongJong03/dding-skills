from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

from conftest import REPO_ROOT, parse_json_output


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Regression Test"], cwd=path, check=True)


def test_git_sync_dry_run_limits_allowed_paths_and_warns_private_roots(temp_ctf_env, run_cli) -> None:
    repo = temp_ctf_env.solver_repo
    _init_git_repo(repo)
    (repo / "metrics").mkdir(exist_ok=True)
    (repo / "metrics" / "summary.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "timestamp": "2026-01-01T00:00:00Z",
                "run_id": "RUN-GIT-1",
                "platform": "thcon",
                "event": "THCON",
                "category": "web",
                "status": "solved",
                "duration_sec": 1,
                "tool_call_counts": {},
                "cleanup_bytes_saved": 0,
                "writeup_generated": False,
                "exploit_included": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "metrics" / "dashboard.md").write_text("# dashboard\n", encoding="utf-8")
    (repo / "SolvedWriteUp").mkdir()
    (repo / ".ctf-solver").mkdir()

    result = parse_json_output(run_cli(["scripts/git_sync_metrics.py", "--dry-run"]))
    assert "metrics" in result["allowed_paths"]
    assert "SolvedWriteUp" not in result["allowed_paths"]
    assert ".ctf-solver" not in result["allowed_paths"]
    assert any("SolvedWriteUp" in warning for warning in result["warnings"])
    assert any(".ctf-solver" in warning for warning in result["warnings"])


def test_no_push_takes_precedence_over_push(monkeypatch, temp_ctf_env) -> None:
    spec = importlib.util.spec_from_file_location("git_sync_metrics_for_test", REPO_ROOT / "scripts/git_sync_metrics.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls: list[list[str]] = []

    def fake_git(args, *, capture=True):
        calls.append(list(args))
        stdout = ""
        if args[:2] == ["diff", "--cached"] and "--name-only" in args:
            stdout = "metrics/summary.jsonl\n"
        elif args[:2] == ["diff", "--cached"]:
            stdout = "diff --git a/metrics/summary.jsonl b/metrics/summary.jsonl\n+public metrics\n"
        elif args and args[0] == "commit":
            stdout = "[test] commit\n"
        return subprocess.CompletedProcess(["git", *args], 0, stdout, "")

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module, "check_public_metrics", lambda: [])
    monkeypatch.setattr(module, "_existing_allowed_paths", lambda: ["metrics"])
    monkeypatch.setattr(module, "_private_path_warnings", lambda: [])

    result = module.git_sync(
        argparse.Namespace(commit_message="test", push=True, no_push=True, dry_run=False)
    )
    assert result["committed"] is True
    assert result["pushed"] is False
    assert ["push"] not in calls
