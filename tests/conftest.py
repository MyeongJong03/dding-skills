from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_HOME = Path.home()


def _existing_playwright_browser_path() -> str | None:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        return configured
    candidates = []
    if sys.platform == "darwin":
        candidates.append(REAL_HOME / "Library" / "Caches" / "ms-playwright")
    candidates.extend(
        [
            REAL_HOME / ".cache" / "ms-playwright",
            REAL_HOME / "AppData" / "Local" / "ms-playwright",
        ]
    )
    for path in candidates:
        if path.is_dir():
            return str(path)
    return None


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
    gdb = tmp_path / "gdb"
    gdb_artifacts = tmp_path / "gdb-artifacts"
    browser = tmp_path / "browser"
    browser_artifacts = tmp_path / "browser-artifacts"
    browser_states = tmp_path / "browser-states"
    callbacks = tmp_path / "callbacks"
    callbackd = tmp_path / "callbackd"
    web_workflows = tmp_path / "web-workflows"
    live_smoke = home / ".ctf-solver" / "live-smoke"
    private_metrics = tmp_path / "metrics-private"
    ai_usage = tmp_path / "ai-usage"
    private_benchmarks = tmp_path / "benchmarks-private"
    private_benchmark_runs = tmp_path / "benchmark-runs-private"
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
        gdb,
        gdb_artifacts,
        browser,
        browser_artifacts,
        browser_states,
        callbacks,
        callbackd,
        web_workflows,
        live_smoke,
        private_metrics,
        ai_usage,
        private_benchmarks,
        private_benchmark_runs,
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
        "CTF_GDB_ROOT": str(gdb),
        "CTF_GDB_ARTIFACT_ROOT": str(gdb_artifacts),
        "CTF_BROWSER_ROOT": str(browser),
        "CTF_BROWSER_ARTIFACT_ROOT": str(browser_artifacts),
        "CTF_BROWSER_STATE_ROOT": str(browser_states),
        "CTF_CALLBACK_ROOT": str(callbacks),
        "CTF_CALLBACKD_ROOT": str(callbackd),
        "CTF_WEB_WORKFLOW_ROOT": str(web_workflows),
        "CTF_LIVE_SMOKE_ROOT": str(live_smoke),
        "CTF_PRIVATE_METRICS_ROOT": str(private_metrics),
        "CTF_AI_USAGE_ROOT": str(ai_usage),
        "CTF_BENCHMARK_ROOT": str(private_benchmarks),
        "CTF_BENCHMARK_RUN_ROOT": str(private_benchmark_runs),
        "CTF_PLATFORM_AUTOMATION_ROOT": str(platform_auto),
        "CTF_DOWNLOAD_ROOT": str(downloads),
        "CTF_SOLVER_REPO_ROOT": str(solver_repo),
        "CTF_PLATFORM_CONFIG": str(policy),
        "CTF_METRICS_MODE": "public",
    }
    playwright_browsers = _existing_playwright_browser_path()
    if playwright_browsers:
        env_values["PLAYWRIGHT_BROWSERS_PATH"] = playwright_browsers
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
        gdb=gdb,
        gdb_artifacts=gdb_artifacts,
        browser=browser,
        browser_artifacts=browser_artifacts,
        browser_states=browser_states,
        callbacks=callbacks,
        callbackd=callbackd,
        web_workflows=web_workflows,
        live_smoke=live_smoke,
        private_metrics=private_metrics,
        ai_usage=ai_usage,
        private_benchmarks=private_benchmarks,
        private_benchmark_runs=private_benchmark_runs,
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


@pytest.fixture()
def ctfd_mock_server():
    servers: list[HTTPServer] = []

    def _start(*, required_cookie: str | None = None) -> SimpleNamespace:
        hits: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, status: int, payload: dict[str, object]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                hits.append(self.path)
                if required_cookie and self.headers.get("Cookie") != required_cookie:
                    self._send_json(403, {"success": False, "error": "auth required"})
                    return
                if self.path == "/api/v1/challenges":
                    self._send_json(
                        200,
                        {
                            "success": True,
                            "data": [
                                {
                                    "id": 1,
                                    "name": "web baby",
                                    "category": "web",
                                    "value": 100,
                                    "solves": 3,
                                    "tags": [{"name": "starter"}],
                                }
                            ],
                        },
                    )
                    return
                if self.path == "/api/v1/challenges/1":
                    self._send_json(
                        200,
                        {
                            "success": True,
                            "data": {
                                "id": 1,
                                "name": "web baby",
                                "category": "web",
                                "description": "local mock detail",
                                "connection_info": "nc example.invalid 31337",
                                "value": 100,
                                "solves": 3,
                                "tags": [{"name": "starter"}],
                                "files": [],
                                "state": "visible",
                            },
                        },
                    )
                    return
                self._send_json(404, {"success": False})

            def log_message(self, format: str, *args: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        host, port = server.server_address
        return SimpleNamespace(base_url=f"http://{host}:{port}", hits=hits)

    yield _start

    for server in servers:
        server.shutdown()
        server.server_close()


def parse_json_output(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)
