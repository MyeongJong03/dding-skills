from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _policy_value(value: bool | str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_platform_config(
    path: Path,
    *,
    platform: str = "thcon",
    event: str = "THCON",
    adapter: str = "mock",
    base_url: str = "",
    auth_mode: str = "browser_profile",
    sharing: bool = False,
    max_active: int = 1,
    provisioning: bool = True,
    allow_problem_discovery: bool | str = True,
    allow_file_download: bool | str = True,
    allow_server_create: bool | str = True,
    allow_submission: bool | str = "ask",
) -> None:
    allowed = "true" if sharing else "false"
    max_workers = 3 if sharing else 1
    base_url_line = f"    base_url: {base_url}\n" if base_url else ""
    path.write_text(
        f"""platforms:
  - platform: {platform}
    event: {event}
    adapter: {adapter}
{base_url_line}    auth:
      mode: {auth_mode}
      session_profile: local-profile-placeholder
    resources:
      remote_server:
        provisioning: {_policy_value(provisioning)}
        max_active_leases: {max_active}
        lease_scope: event
        release_required_before_next: true
        sharing:
          allowed: {allowed}
          max_workers: {max_workers}
          mode: {"multi_client_read_only" if sharing else "exclusive"}
          destructive_actions_require_primary: true
    automation:
      allow_problem_discovery: {_policy_value(allow_problem_discovery)}
      allow_file_download: {_policy_value(allow_file_download)}
      allow_server_create: {_policy_value(allow_server_create)}
      allow_submission: {_policy_value(allow_submission)}
""",
        encoding="utf-8",
    )


@pytest.fixture()
def temp_ctf_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    home = tmp_path / "home"
    work = tmp_path / "work"
    runs = tmp_path / "runs"
    locks = tmp_path / "locks"
    writeups = tmp_path / "writeups"
    leases = tmp_path / "leases"
    queue = tmp_path / "queue"
    workers = tmp_path / "workers"
    sessions = tmp_path / "sessions"
    sessiond = tmp_path / "sessiond"
    browser_states = tmp_path / "browser-states"
    platform_auto = tmp_path / "platforms"
    downloads = tmp_path / "downloads"
    solver_repo = tmp_path / "solver-repo"
    policy = tmp_path / "platforms.yaml"

    for path in (
        home,
        work,
        runs,
        locks,
        writeups,
        leases,
        queue,
        workers,
        sessions,
        sessiond,
        browser_states,
        platform_auto,
        downloads,
        solver_repo / "metrics",
    ):
        path.mkdir(parents=True, exist_ok=True)
    _write_platform_config(policy)

    env_values = {
        "HOME": str(home),
        "CTF_WORK_ROOT": str(work),
        "CTF_LOCAL_RUN_ROOT": str(runs),
        "CTF_LOCK_ROOT": str(locks),
        "CTF_SOLVED_WRITEUP_ROOT": str(writeups),
        "CTF_LEASE_ROOT": str(leases),
        "CTF_QUEUE_ROOT": str(queue),
        "CTF_WORKER_ROOT": str(workers),
        "CTF_SESSION_ROOT": str(sessions),
        "CTF_SESSIOND_ROOT": str(sessiond),
        "CTF_BROWSER_STATE_ROOT": str(browser_states),
        "CTF_PLATFORM_AUTOMATION_ROOT": str(platform_auto),
        "CTF_DOWNLOAD_ROOT": str(downloads),
        "CTF_SOLVER_REPO_ROOT": str(solver_repo),
        "CTF_PLATFORM_CONFIG": str(policy),
        "CTF_METRICS_MODE": "public",
    }
    for key, value in env_values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CTF_AUTO_PUSH", raising=False)

    return SimpleNamespace(
        base=tmp_path,
        home=home,
        work=work,
        runs=runs,
        locks=locks,
        writeups=writeups,
        leases=leases,
        queue=queue,
        workers=workers,
        sessions=sessions,
        sessiond=sessiond,
        browser_states=browser_states,
        platform_auto=platform_auto,
        downloads=downloads,
        solver_repo=solver_repo,
        policy=policy,
        env={**os.environ, **env_values},
        write_platform_config=lambda **kwargs: _write_platform_config(policy, **kwargs),
    )


@pytest.fixture()
def run_cli(temp_ctf_env: SimpleNamespace):
    def _run(args: list[str], *, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, *args]
        result = subprocess.run(
            command,
            cwd=cwd or REPO_ROOT,
            env=temp_ctf_env.env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"command failed: {' '.join(command)}\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        return result

    return _run


def parse_json_output(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)
