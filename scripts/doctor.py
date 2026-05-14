#!/usr/bin/env python3
"""Consistency doctor for the ctf-solver repo."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.paths import (
    browser_artifact_root,
    browser_root,
    browser_state_root,
    callback_root,
    callbackd_root,
    download_root,
    display_path,
    dreamhack_fixture_root,
    gdb_artifact_root,
    gdb_root,
    ai_usage_root,
    is_inside_repo,
    lease_root,
    live_smoke_root,
    local_run_root,
    lock_root,
    metrics_root,
    private_benchmark_root,
    private_benchmark_run_root,
    private_metrics_root,
    platform_automation_root,
    queue_root,
    session_root,
    sessiond_root,
    solved_writeup_root,
    web_workflow_root,
    worker_root,
)
from ctf_solver_core.browser_actions import active_browser_session_count
from ctf_solver_core.browser_client import status as browser_daemon_status
from ctf_solver_core.browser_state import browser_profile_count
from ctf_solver_core.callback_client import status as callback_daemon_status
from ctf_solver_core.callbacks import active_listener_count
from ctf_solver_core.gdb_session import active_gdb_session_count
from ctf_solver_core.live_smoke import live_smoke_result_count
from ctf_solver_core.platform_automation import download_metadata_count, platform_server_record_count
from ctf_solver_core.platform_adapters import get_adapter
from ctf_solver_core.platforms import platform_config_path, validate_platform_config
from ctf_solver_core.resources import detect_stale_leases, list_leases
from ctf_solver_core.performance import validate_public_metrics_files
from ctf_solver_core.session_client import status as session_daemon_status
from ctf_solver_core.web_workflow import active_web_workflow_count
from ctf_solver_core.worker import detect_stale_claims, list_claims

HOME = Path.home()
CTF_DIR = HOME / "CTF"
CANONICAL_MCP_NAME = "ctf_solver"
LEGACY_MCP_NAME = "".join(("dreamhack", "_solver"))
OPERATOR_SHORTCUTS = ("ctf-status", "ctf-check", "ctf-regression")
EXTERNAL_SKILL_NAMES = {
    "ctf-ai-ml",
    "ctf-crypto",
    "ctf-forensics",
    "ctf-malware",
    "ctf-misc",
    "ctf-osint",
    "ctf-pwn",
    "ctf-reverse",
    "ctf-web",
    "ctf-writeup",
    "solve-challenge",
}
LIFECYCLE_RULES_MARKER = "## Challenge Lifecycle Rules"


class Doctor:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, message: str) -> None:
        print(f"[OK] {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"[WARN] {message}")

    def info(self, message: str) -> None:
        print(f"[INFO] {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"[FAIL] {message}")

    def require_file(self, relative: str) -> bool:
        path = ROOT / relative
        if path.is_file():
            self.ok(f"{relative} exists")
            return True
        self.fail(f"{relative} missing")
        return False

    def require_contains(self, path: Path, needle: str, label: str, *, hard: bool = True) -> bool:
        if not path.exists():
            message = f"{label} missing"
            if hard:
                self.fail(message)
            else:
                self.warn(message)
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle in text:
            self.ok(f"{label} contains lifecycle enforcement rules")
            return True
        message = f"{label} missing lifecycle enforcement rules"
        if hard:
            self.fail(message)
        else:
            self.warn(message)
        return False

    def run_syntax(self, relative: str) -> None:
        path = ROOT / relative
        if not path.is_file():
            self.fail(f"{relative} missing")
            return
        result = subprocess.run(
            ["bash", "-n", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            self.ok(f"{relative} syntax ok")
        else:
            self.fail(f"{relative} syntax failed: {result.stderr.strip()}")

    def command_version(self, name: str, optional: bool) -> None:
        path = shutil.which(name)
        if not path:
            if optional:
                self.warn(f"{name} CLI not found (optional)")
            else:
                self.fail(f"{name} CLI not found")
            return

        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = (result.stdout or result.stderr).strip().splitlines()
        suffix = f": {version[0]}" if version else ""
        self.ok(f"{name} CLI found at {path}{suffix}")

    def docker_status(self) -> None:
        docker = shutil.which("docker")
        if not docker:
            self.warn("Docker CLI not found (optional runtime dependency)")
            return
        self.ok(f"Docker CLI found at {docker}")
        result = subprocess.run(
            [docker, "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            self.ok("Docker daemon reachable")
        else:
            self.warn("Docker daemon off or unreachable (optional runtime dependency)")

    def docker_image_exists(self, docker: str, image: str) -> bool:
        candidates = [
            [docker, "image", "inspect", image],
            [docker, "inspect", image],
        ]
        if ":" in image:
            candidates.append([docker, "image", "inspect", image.split(":", 1)[0]])
        for command in candidates:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return True
        return False

    def check_docker_gdb_smoke_availability(self) -> None:
        enabled = os.environ.get("CTF_RUN_DOCKER_GDB_TESTS") == "1"
        self.info(f"CTF_RUN_DOCKER_GDB_TESTS={'1' if enabled else 'not set'}")
        docker = shutil.which("docker")
        if not docker:
            self.info("Docker GDB smoke unavailable: Docker CLI not found")
            return
        info = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=10)
        if info.returncode != 0:
            self.info("Docker GDB smoke unavailable: Docker daemon is not reachable")
            return
        if not self.docker_image_exists(docker, "ctf-pwn:latest"):
            self.info("Docker GDB smoke unavailable: ctf-pwn:latest image not found")
            return
        self.ok("ctf-pwn:latest Docker image is available")
        compiler = subprocess.run(
            [
                docker,
                "run",
                "--rm",
                "--platform",
                "linux/amd64",
                "--network",
                "none",
                "ctf-pwn:latest",
                "bash",
                "-lc",
                "command -v gcc >/dev/null 2>&1 && echo gcc || { command -v cc >/dev/null 2>&1 && echo cc; }",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        found = compiler.stdout.strip().splitlines()
        if compiler.returncode == 0 and found:
            self.ok(f"Docker GDB smoke compiler inside ctf-pwn:latest: {found[0]}")
        else:
            self.info("Docker GDB smoke will skip until gcc/cc is available inside ctf-pwn:latest")

    def check_playwright_runtime(self) -> None:
        script = ROOT / "scripts" / "browser_playwright_check.py"
        if not script.is_file():
            self.warn("browser Playwright runtime check script missing (optional)")
            return
        try:
            result = subprocess.run(
                [sys.executable, str(script), "--use-uv", "--timeout-seconds", "12", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.warn("Playwright runtime check timed out (optional browser automation)")
            return
        if result.returncode != 0:
            self.warn("Playwright runtime check failed to run (optional browser automation)")
            return
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.warn("Playwright runtime check returned invalid JSON (optional browser automation)")
            return

        if data.get("current_python_playwright_available"):
            self.ok("current Python can import Playwright")
        else:
            self.info("current Python cannot import Playwright (optional browser automation)")

        if data.get("uv_available"):
            self.ok("uv executable found for optional Playwright runtime")
        else:
            self.warn("uv executable not found; use a repo-external venv for optional Playwright runtime")

        uv_available = data.get("uv_playwright_available")
        if uv_available is True:
            self.ok("uv can provide Playwright from local cache without installing")
        elif uv_available is False:
            self.info("uv offline Playwright check did not find a cached package; documented uv command can install it")
        else:
            self.info(f"uv Playwright check status: {data.get('uv_check_mode')}")

        current_chromium = data.get("current_python_chromium_available")
        uv_chromium = data.get("uv_chromium_available")
        if current_chromium is True:
            self.ok("current Python Playwright Chromium binary is installed")
        elif current_chromium is False:
            self.warn("current Python Playwright package exists but Chromium browser binary is missing")
        else:
            self.info("current Python Chromium binary check skipped because Playwright is not importable")

        if uv_chromium is True:
            self.ok("uv Playwright Chromium binary is installed")
        elif uv_chromium is False:
            self.warn("uv Playwright is available but Chromium browser binary is missing")
        else:
            self.info("uv Chromium binary check not available in no-install mode")

        if (
            not data.get("current_python_playwright_available")
            and data.get("uv_playwright_available") is not True
        ):
            self.warn("Playwright runtime missing from current Python and uv offline cache (optional)")
        else:
            self.info(f"Playwright recommendation: {data.get('recommendation')}")

    def check_tools(self) -> None:
        tools = sorted((ROOT / "tools").glob("*.py"))
        tools = [path for path in tools if path.name != "__init__.py"]
        if tools:
            self.ok(f"tools/*.py present ({len(tools)} files)")
        else:
            self.fail("tools/*.py missing")

    def check_lifecycle(self) -> None:
        scripts = [
            "scripts/challenge_init.py",
            "scripts/challenge_finalize.py",
            "scripts/generate_writeup.py",
            "scripts/cleanup_challenge.py",
            "scripts/update_metrics.py",
            "scripts/git_sync_metrics.py",
            "scripts/platform_config_init.py",
            "scripts/resource_acquire.py",
            "scripts/resource_heartbeat.py",
            "scripts/resource_release.py",
            "scripts/resource_reclaim_stale.py",
            "scripts/queue_next.py",
            "scripts/queue_update.py",
            "scripts/queue_history.py",
            "scripts/worker_next.py",
            "scripts/worker_run_once.py",
            "scripts/worker_loop.py",
            "scripts/worker_status.py",
            "scripts/secret_scan.py",
            "scripts/doctor.py",
            "scripts/session_daemon.py",
            "scripts/session_start.py",
            "scripts/session_write.py",
            "scripts/session_read.py",
            "scripts/session_expect.py",
            "scripts/session_close.py",
            "scripts/session_list.py",
            "scripts/gdb_start.py",
            "scripts/gdb_cmd.py",
            "scripts/gdb_continue.py",
            "scripts/gdb_wait_crash.py",
            "scripts/gdb_registers.py",
            "scripts/gdb_backtrace.py",
            "scripts/gdb_vmmap.py",
            "scripts/gdb_telescope.py",
            "scripts/gdb_close.py",
            "scripts/gdb_list.py",
            "scripts/gdb_docker_smoke.py",
            "scripts/verify_run.py",
            "scripts/browser_daemon.py",
            "scripts/browser_start.py",
            "scripts/browser_goto.py",
            "scripts/browser_click.py",
            "scripts/browser_fill.py",
            "scripts/browser_eval.py",
            "scripts/browser_upload.py",
            "scripts/browser_screenshot.py",
            "scripts/browser_console.py",
            "scripts/browser_network.py",
            "scripts/browser_cookies.py",
            "scripts/browser_close.py",
            "scripts/browser_list.py",
            "scripts/callback_daemon.py",
            "scripts/callback_start.py",
            "scripts/callback_url.py",
            "scripts/callback_hits.py",
            "scripts/callback_wait.py",
            "scripts/callback_close.py",
            "scripts/callback_list.py",
            "scripts/web_payload_helper.py",
            "scripts/web_workflow_init.py",
            "scripts/web_payload_generate.py",
            "scripts/web_browser_probe.py",
            "scripts/web_callback_probe.py",
            "scripts/web_evidence_collect.py",
            "scripts/web_workflow_close.py",
            "scripts/web_workflow_list.py",
            "scripts/browser_state_init.py",
            "scripts/browser_state_check.py",
            "scripts/platform_discover.py",
            "scripts/platform_download.py",
            "scripts/platform_server_acquire.py",
            "scripts/platform_server_release.py",
            "scripts/platform_server_status.py",
            "scripts/platform_submit.py",
            "scripts/dreamhack_vm_control.py",
            "scripts/platform_smoke_test.py",
            "scripts/platform_live_smoke.py",
            "scripts/ctfd_live_smoke_runbook.py",
            "scripts/offline_e2e_smoke.py",
            "scripts/status_summary.py",
            "scripts/regression_check.py",
            "scripts/install_shortcuts.py",
            "scripts/benchmark_init.py",
            "scripts/benchmark_record_result.py",
            "scripts/benchmark_report.py",
            "scripts/benchmark_pack_init.py",
            "scripts/benchmark_pack_validate.py",
            "scripts/benchmark_export_public.py",
            "scripts/benchmark_compare.py",
            "scripts/performance_report.py",
            "scripts/ai_usage_record.py",
            "scripts/ai_usage_import.py",
            "scripts/ai_usage_report.py",
        ]
        for relative in scripts:
            self.require_file(relative)

        self.require_contains(
            ROOT / "config" / "CLAUDE.base.md",
            LIFECYCLE_RULES_MARKER,
            "config/CLAUDE.base.md",
            hard=True,
        )

        if (ROOT / "ctf_solver_core" / "paths.py").is_file():
            self.ok("ctf_solver_core path helpers exist")
        else:
            self.fail("ctf_solver_core path helpers missing")
        for relative in [
            "ctf_solver_core/platforms.py",
            "ctf_solver_core/resources.py",
            "ctf_solver_core/queue.py",
            "ctf_solver_core/worker.py",
            "ctf_solver_core/sessions.py",
            "ctf_solver_core/session_daemon.py",
            "ctf_solver_core/session_client.py",
            "ctf_solver_core/gdb_session.py",
            "ctf_solver_core/gdb_client.py",
            "ctf_solver_core/gdb_parsers.py",
            "ctf_solver_core/verifier.py",
            "ctf_solver_core/browser_actions.py",
            "ctf_solver_core/browser_client.py",
            "ctf_solver_core/browser_daemon.py",
            "ctf_solver_core/callbacks.py",
            "ctf_solver_core/callback_client.py",
            "ctf_solver_core/callback_daemon.py",
            "ctf_solver_core/web_workflow.py",
            "ctf_solver_core/web_payloads.py",
            "ctf_solver_core/benchmarks.py",
            "ctf_solver_core/performance.py",
            "ctf_solver_core/ai_usage.py",
            "ctf_solver_core/browser_state.py",
            "ctf_solver_core/platform_automation.py",
            "ctf_solver_core/platform_adapters.py",
            "ctf_solver_core/live_smoke.py",
            "ctf_solver_core/adapters/ctfd.py",
            "ctf_solver_core/adapters/dreamhack.py",
            "config/platforms.example.yaml",
            "docs/platform-automation.md",
            "docs/browser-platform-automation.md",
            "docs/browser-actions.md",
            "docs/callback-listener.md",
            "docs/web-exploit-workflow.md",
            "docs/ctfd-adapter.md",
            "docs/dreamhack-adapter.md",
            "docs/live-smoke.md",
            "docs/ctfd-live-smoke-runbook.md",
            "docs/offline-e2e-smoke.md",
            "docs/operator-mode.md",
            "docs/regression.md",
            "docs/worker-runner.md",
            "docs/sessions.md",
            "docs/gdb-session.md",
            "docs/verifier.md",
            "docs/benchmarking.md",
            "docs/private-benchmarks.md",
            "docs/ai-usage-metrics.md",
        ]:
            self.require_file(relative)

        try:
            adapter = get_adapter("ctfd")
            if adapter.name == "ctfd":
                self.ok("CTFd adapter is importable")
            else:
                self.fail("CTFd adapter registry returned the wrong adapter")
        except Exception as exc:
            self.fail(f"CTFd adapter import failed: {exc}")

        ctfd_adapter = ROOT / "ctf_solver_core" / "adapters" / "ctfd.py"
        ctfd_text = ctfd_adapter.read_text(encoding="utf-8", errors="replace") if ctfd_adapter.is_file() else ""
        if "/api/v1/challenges" in ctfd_text and "CTF_CTFD_COOKIE_HEADER" in ctfd_text:
            self.ok("CTFd live read-only discovery scaffold is present")
        else:
            self.fail("CTFd live read-only discovery scaffold missing")
        if "CTFD_LIVE_MAX_DOWNLOAD_BYTES" in ctfd_text and "ctfd_download_private_host_blocked" in ctfd_text:
            self.ok("CTFd live download opt-in scaffold is present")
        else:
            self.fail("CTFd live download opt-in scaffold missing")
        self.info("CTFd live credentials are optional local-only inputs and are not inspected by doctor")

        ctfd_doc = ROOT / "docs" / "ctfd-adapter.md"
        if ctfd_doc.is_file() and "CTFd adapter" in ctfd_doc.read_text(encoding="utf-8", errors="replace"):
            self.ok("docs/ctfd-adapter.md mentions CTFd adapter")
        else:
            self.fail("docs/ctfd-adapter.md missing CTFd adapter documentation")

        try:
            adapter = get_adapter("dreamhack")
            if adapter.name == "dreamhack":
                self.ok("Dreamhack adapter is importable")
            else:
                self.fail("Dreamhack adapter registry returned the wrong adapter")
        except Exception as exc:
            self.fail(f"Dreamhack adapter import failed: {exc}")
        if (ROOT / "tools" / "dreamhack_vm.py").is_file():
            self.ok("tools/dreamhack_vm.py remains available")
        else:
            self.fail("tools/dreamhack_vm.py missing")
        dreamhack_adapter = ROOT / "ctf_solver_core" / "adapters" / "dreamhack.py"
        dreamhack_text = (
            dreamhack_adapter.read_text(encoding="utf-8", errors="replace")
            if dreamhack_adapter.is_file()
            else ""
        )
        if "dreamhack_live_required" in dreamhack_text and "dreamhack_auth_required" in dreamhack_text:
            self.ok("Dreamhack VM live/auth opt-in scaffold is present")
        else:
            self.fail("Dreamhack VM live/auth opt-in scaffold missing")
        self.info("Dreamhack live auth values are optional local-only inputs and are not inspected by doctor")

        runbook_script = ROOT / "scripts" / "ctfd_live_smoke_runbook.py"
        runbook_doc = ROOT / "docs" / "ctfd-live-smoke-runbook.md"
        runbook_text = runbook_doc.read_text(encoding="utf-8", errors="replace") if runbook_doc.is_file() else ""
        if runbook_script.is_file() and "dry-run" in runbook_text and "no submit" in runbook_text.lower():
            self.ok("CTFd live smoke runbook helper and docs are present")
        else:
            self.fail("CTFd live smoke runbook helper/docs missing dry-run and no-submit guidance")

        offline_script = ROOT / "scripts" / "offline_e2e_smoke.py"
        offline_doc = ROOT / "docs" / "offline-e2e-smoke.md"
        offline_text = offline_script.read_text(encoding="utf-8", errors="replace") if offline_script.is_file() else ""
        offline_doc_text = offline_doc.read_text(encoding="utf-8", errors="replace") if offline_doc.is_file() else ""
        if (
            "--platform" in offline_text
            and "fixture_root_must_be_local" in offline_text
            and "challenge_finalize.py" in offline_text
            and "external network" in offline_doc_text
        ):
            self.ok("offline E2E platform flow smoke scaffold is present")
        else:
            self.fail("offline E2E platform flow smoke scaffold missing fixture-only lifecycle checks")
        self.info("offline E2E smoke uses fixture-only temp roots and does not require live credentials")

        status_script = ROOT / "scripts" / "status_summary.py"
        regression_script = ROOT / "scripts" / "regression_check.py"
        regression_doc = ROOT / "docs" / "regression.md"
        status_text = status_script.read_text(encoding="utf-8", errors="replace") if status_script.is_file() else ""
        regression_text = regression_script.read_text(encoding="utf-8", errors="replace") if regression_script.is_file() else ""
        regression_doc_text = regression_doc.read_text(encoding="utf-8", errors="replace") if regression_doc.is_file() else ""
        if (
            "CTF_SOLVER_STATUS_BEGIN" in status_text
            and "mcp_server_names" in status_text
            and ".claude.json" in status_text
            and "CTF_SOLVER_REGRESSION_BEGIN" in regression_text
            and "offline_e2e_ctfd" in regression_text
            and "--quick" in regression_text
            and "skip-offline-e2e" in regression_text
            and "ctf-status" in regression_doc_text
            and "install_shortcuts.py" in regression_doc_text
            and "no live network" in regression_doc_text.lower()
            and "`~/.claude.json` is never printed" in regression_doc_text
        ):
            self.ok("regression/status command pack scaffold is present")
        else:
            self.fail("regression/status command pack scaffold missing marker, redaction, or no-live guidance")

        operator_doc = ROOT / "docs" / "operator-mode.md"
        readme = ROOT / "README.md"
        guide = ROOT / "GUIDE.md"
        claude_base = ROOT / "config" / "CLAUDE.base.md"
        operator_doc_text = operator_doc.read_text(encoding="utf-8", errors="replace") if operator_doc.is_file() else ""
        readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
        guide_text = guide.read_text(encoding="utf-8", errors="replace") if guide.is_file() else ""
        claude_text = claude_base.read_text(encoding="utf-8", errors="replace") if claude_base.is_file() else ""
        if (
            "# Operator Mode Runbook" in operator_doc_text
            and "ctf-status" in operator_doc_text
            and "ctf-check" in operator_doc_text
            and "ctf-regression" in operator_doc_text
            and "challenge_init.py" in operator_doc_text
            and "worker_next.py" in operator_doc_text
            and "verify_run.py" in operator_doc_text
            and "challenge_finalize.py --run-dir <run-dir> --status solved --require-verifier --generate-writeup --cleanup --update-metrics"
            in operator_doc_text
            and "CTFd" in operator_doc_text
            and "Dreamhack" in operator_doc_text
            and "~/SolvedWriteUp" in operator_doc_text
            and "metrics/" in operator_doc_text
            and "docs/operator-mode.md" in readme_text
            and "docs/operator-mode.md" in guide_text
            and "## Operator Mode Rules" in claude_text
        ):
            self.ok("operator mode runbook and README/GUIDE/CLAUDE links are present")
        else:
            self.fail("operator mode runbook missing key commands, storage rules, or docs/config links")

        installer = ROOT / "scripts" / "install_shortcuts.py"
        installer_text = installer.read_text(encoding="utf-8", errors="replace") if installer.is_file() else ""
        if "--dry-run" in installer_text and "--uninstall" in installer_text and "ctf-check" in installer_text:
            self.ok("operator shortcut installer scaffold is present")
        else:
            self.fail("operator shortcut installer scaffold missing shortcut or dry-run support")

        self.check_operator_shortcuts()

        platform_errors = validate_platform_config(ROOT / "config" / "platforms.example.yaml")
        if platform_errors:
            for error in platform_errors:
                self.fail(f"platform example invalid: {error}")
        else:
            self.ok("config/platforms.example.yaml loads successfully")
        if os.environ.get("CTF_PLATFORM_CONFIG"):
            env_config = platform_config_path()
            env_errors = validate_platform_config(env_config)
            if env_errors:
                for error in env_errors:
                    self.fail(f"CTF_PLATFORM_CONFIG invalid: {error}")
            else:
                self.ok(f"CTF_PLATFORM_CONFIG loads successfully: {display_path(env_config)}")

        metrics = metrics_root()
        if metrics == ROOT / "metrics":
            self.ok("metrics root is repo-local")
        else:
            self.warn(f"metrics root resolved outside repo default: {metrics}")
        if metrics.is_dir():
            self.ok("metrics directory exists")
        else:
            self.fail("metrics directory missing")
        if (metrics / "dashboard.md").is_file():
            self.ok("metrics/dashboard.md exists")
        else:
            self.warn("metrics/dashboard.md missing; update_metrics.py will generate it")
        metric_errors = validate_public_metrics_files(metrics)
        if metric_errors:
            for error in metric_errors:
                self.fail(f"public metrics unsafe: {error}")
        else:
            self.ok("public metrics safety check passed")

        secret_scan = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "secret_scan.py"), "--strict"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if secret_scan.returncode == 0:
            self.ok("secret scan passed")
        else:
            output = (secret_scan.stdout or secret_scan.stderr).strip()
            self.fail(f"secret scan failed: {output}")

        writeup_root = solved_writeup_root()
        run_root = local_run_root()
        private_metrics = private_metrics_root()
        ai_usage = ai_usage_root()
        private_benchmarks = private_benchmark_root()
        benchmark_runs = private_benchmark_run_root()
        locks = lock_root()
        leases = lease_root()
        queue = queue_root()
        workers = worker_root()
        sessions = session_root()
        sessiond = sessiond_root()
        gdb = gdb_root()
        gdb_artifacts = gdb_artifact_root()
        browser = browser_root()
        browser_artifacts = browser_artifact_root()
        browser_states = browser_state_root()
        callbacks = callback_root()
        callbackd = callbackd_root()
        web_workflows = web_workflow_root()
        live_smoke = live_smoke_root()
        platform_auto = platform_automation_root()
        downloads = download_root()
        self.info(f"writeup root: {display_path(writeup_root)}")
        self.info(f"private run root: {display_path(run_root)}")
        self.info(f"private metrics root: {display_path(private_metrics)}")
        self.info(f"AI usage root: {display_path(ai_usage)}")
        self.info(f"private benchmark root: {display_path(private_benchmarks)}")
        self.info(f"private benchmark run root: {display_path(benchmark_runs)}")
        self.info(f"lock root: {display_path(locks)}")
        self.info(f"lease root: {display_path(leases)}")
        self.info(f"queue root: {display_path(queue)}")
        self.info(f"worker root: {display_path(workers)}")
        self.info(f"session root: {display_path(sessions)}")
        self.info(f"session daemon root: {display_path(sessiond)}")
        self.info(f"GDB root: {display_path(gdb)}")
        self.info(f"GDB artifact root: {display_path(gdb_artifacts)}")
        self.info(f"browser root: {display_path(browser)}")
        self.info(f"browser artifact root: {display_path(browser_artifacts)}")
        self.info(f"browser state root: {display_path(browser_states)}")
        self.info(f"callback root: {display_path(callbacks)}")
        self.info(f"callback daemon root: {display_path(callbackd)}")
        self.info(f"web workflow root: {display_path(web_workflows)}")
        self.info(f"live smoke root: {display_path(live_smoke)}")
        self.info(f"platform automation root: {display_path(platform_auto)}")
        self.info(f"download root: {display_path(downloads)}")

        if is_inside_repo(writeup_root):
            self.fail("writeup root is inside repo; local-only writeups could be staged accidentally")
        if is_inside_repo(run_root):
            self.fail("private run root is inside repo; private logs could be staged accidentally")
        if is_inside_repo(private_metrics):
            self.warn("private metrics root is inside repo; prefer ~/.ctf-solver/metrics-private or CTF_PRIVATE_METRICS_ROOT outside repo")
        if is_inside_repo(ai_usage):
            self.warn("AI usage root is inside repo; prefer ~/.ctf-solver/ai-usage or CTF_AI_USAGE_ROOT outside repo")
        if is_inside_repo(private_benchmarks):
            self.warn("private benchmark root is inside repo; prefer ~/.ctf-solver/benchmarks or CTF_BENCHMARK_ROOT outside repo")
        if is_inside_repo(benchmark_runs):
            self.warn(
                "private benchmark run root is inside repo; "
                "prefer ~/.ctf-solver/benchmark-runs or CTF_BENCHMARK_RUN_ROOT outside repo"
            )
        if is_inside_repo(locks):
            self.warn("lock root is inside repo; prefer ~/.ctf-solver/locks or CTF_LOCK_ROOT outside repo")
        if is_inside_repo(leases):
            self.warn("lease root is inside repo; prefer ~/.ctf-solver/leases or CTF_LEASE_ROOT outside repo")
        if is_inside_repo(queue):
            self.warn("queue root is inside repo; prefer ~/.ctf-solver/queue or CTF_QUEUE_ROOT outside repo")
        if is_inside_repo(workers):
            self.warn("worker root is inside repo; prefer ~/.ctf-solver/workers or CTF_WORKER_ROOT outside repo")
        if is_inside_repo(sessions):
            self.warn("session root is inside repo; prefer ~/.ctf-solver/sessions or CTF_SESSION_ROOT outside repo")
        if is_inside_repo(sessiond):
            self.warn("session daemon root is inside repo; prefer ~/.ctf-solver/sessiond or CTF_SESSIOND_ROOT outside repo")
        if is_inside_repo(gdb):
            self.warn("GDB root is inside repo; prefer ~/.ctf-solver/gdb or CTF_GDB_ROOT outside repo")
        if is_inside_repo(gdb_artifacts):
            self.warn(
                "GDB artifact root is inside repo; prefer ~/.ctf-solver/gdb-artifacts "
                "or CTF_GDB_ARTIFACT_ROOT outside repo"
            )
        if is_inside_repo(browser):
            self.warn("browser root is inside repo; prefer ~/.ctf-solver/browser or CTF_BROWSER_ROOT outside repo")
        if is_inside_repo(browser_artifacts):
            self.warn(
                "browser artifact root is inside repo; prefer ~/.ctf-solver/browser-artifacts "
                "or CTF_BROWSER_ARTIFACT_ROOT outside repo"
            )
        if is_inside_repo(browser_states):
            self.warn("browser state root is inside repo; prefer ~/.ctf-solver/browser-states or CTF_BROWSER_STATE_ROOT outside repo")
        if is_inside_repo(callbacks):
            self.warn("callback root is inside repo; prefer ~/.ctf-solver/callbacks or CTF_CALLBACK_ROOT outside repo")
        if is_inside_repo(callbackd):
            self.warn("callback daemon root is inside repo; prefer ~/.ctf-solver/callbackd or CTF_CALLBACKD_ROOT outside repo")
        if is_inside_repo(web_workflows):
            self.warn("web workflow root is inside repo; prefer ~/.ctf-solver/web-workflows or CTF_WEB_WORKFLOW_ROOT outside repo")
        if is_inside_repo(live_smoke):
            self.warn("live smoke root is inside repo; prefer ~/.ctf-solver/live-smoke or CTF_LIVE_SMOKE_ROOT outside repo")
        if is_inside_repo(platform_auto):
            self.warn("platform automation root is inside repo; prefer ~/.ctf-solver/platforms or CTF_PLATFORM_AUTOMATION_ROOT outside repo")
        if is_inside_repo(downloads):
            self.warn("download root is inside repo; prefer ~/CTF/downloads or CTF_DOWNLOAD_ROOT outside repo")
        self.check_dreamhack_fixture_root()
        try:
            daemon = session_daemon_status()
            if daemon.get("running"):
                self.info(f"session daemon running pid={daemon.get('pid')} {daemon.get('host')}:{daemon.get('port')}")
            else:
                self.info("session daemon not running (optional)")
        except Exception as exc:
            self.warn(f"could not inspect session daemon safely: {exc}")
        try:
            self.info(f"active GDB session metadata count: {active_gdb_session_count()}")
        except Exception as exc:
            self.warn(f"could not inspect GDB sessions safely: {exc}")
        self.command_version("gdb", optional=True)
        docker = shutil.which("docker")
        if docker:
            if self.docker_image_exists(docker, "ctf-pwn:latest"):
                self.ok("ctf-pwn:latest Docker image is available")
            else:
                self.info("ctf-pwn:latest Docker image not found (optional GDB Docker mode)")
        self.check_playwright_runtime()
        self.info("live AI provider credentials are not required for benchmark or AI usage metrics scaffolds")
        try:
            daemon = browser_daemon_status()
            if daemon.get("running"):
                self.info(f"browser daemon running pid={daemon.get('pid')} {daemon.get('host')}:{daemon.get('port')}")
            else:
                self.info("browser daemon not running (optional)")
            self.info(f"active browser session metadata count: {active_browser_session_count()}")
        except Exception as exc:
            self.warn(f"could not inspect browser daemon safely: {exc}")
        try:
            daemon = callback_daemon_status()
            if daemon.get("running"):
                self.info(f"callback daemon running pid={daemon.get('pid')} {daemon.get('host')}:{daemon.get('port')}")
            else:
                self.info("callback daemon not running (optional)")
            self.info(f"active callback listener metadata count: {active_listener_count()}")
        except Exception as exc:
            self.warn(f"could not inspect callback daemon safely: {exc}")
        try:
            self.info(f"active web workflow metadata count: {active_web_workflow_count()}")
        except Exception as exc:
            self.warn(f"could not inspect web workflows safely: {exc}")
        try:
            active_claims = list_claims(include_stale=False)
            stale_claims = detect_stale_claims()
            if active_claims:
                self.info(f"active worker claim count: {len(active_claims)}")
            else:
                self.ok("active worker claim count: 0")
            if stale_claims:
                self.warn(f"stale worker claim count: {len(stale_claims)}")
            else:
                self.ok("stale worker claim count: 0")
        except Exception as exc:
            self.warn(f"could not inspect worker claim counts safely: {exc}")
        try:
            active_leases = list_leases()
            if active_leases:
                self.info(f"active lease count: {len(active_leases)}")
            else:
                self.ok("active lease count: 0")
            stale_leases = detect_stale_leases()
            if stale_leases:
                self.warn(f"stale lease count: {len(stale_leases)}")
            else:
                self.ok("stale lease count: 0")
        except Exception as exc:
            self.warn(f"could not inspect lease counts safely: {exc}")
        try:
            self.info(f"browser profile metadata count: {browser_profile_count()}")
            self.info(f"live smoke result count: {live_smoke_result_count()}")
            self.info(f"platform server record count: {platform_server_record_count()}")
            self.info(f"download metadata count: {download_metadata_count()}")
        except Exception as exc:
            self.warn(f"could not inspect platform automation counts safely: {exc}")
        self.ok("metrics are repo-local public-safe targets; writeups/private runs are local-only targets")

    def check_dreamhack_fixture_root(self) -> None:
        fixture_root = dreamhack_fixture_root()
        self.info(f"Dreamhack private fixture root: {display_path(fixture_root)}")
        if is_inside_repo(fixture_root):
            self.warn(
                "Dreamhack private fixture root is inside repo; "
                "prefer ~/.ctf-solver/fixtures/dreamhack or CTF_DREAMHACK_FIXTURE_ROOT outside repo"
            )

    def check_operator_shortcuts(self) -> None:
        raw_bin_dir = os.environ.get("CTF_SHORTCUT_BIN_DIR")
        bin_dir = Path(raw_bin_dir).expanduser() if raw_bin_dir else HOME / ".local" / "bin"
        missing: list[str] = []
        unmanaged: list[str] = []
        for name in OPERATOR_SHORTCUTS:
            path = bin_dir / name
            if not path.exists():
                missing.append(name)
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                unmanaged.append(name)
                continue
            if "ctf-solver-shortcut:" not in text or "scripts/install_shortcuts.py" not in text:
                unmanaged.append(name)
        if not missing and not unmanaged:
            self.ok(f"operator shortcuts installed in {display_path(bin_dir)}")
            return
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unmanaged:
            details.append(f"unmanaged={','.join(unmanaged)}")
        self.warn(
            "operator shortcuts are optional; "
            + "; ".join(details)
            + "; run python3 scripts/install_shortcuts.py to install"
        )

    def check_agents_generation(self) -> None:
        required = [
            "config/deploy.sh",
            "config/CLAUDE.base.md",
            "config/mac/env.md",
            "config/windows/env.md",
        ]
        if all((ROOT / item).is_file() for item in required):
            self.ok("AGENTS.md generation is available through config/deploy.sh")
        else:
            self.fail("AGENTS.md generation prerequisites are incomplete")

    def check_ctf_workspace(self) -> None:
        claude_md = CTF_DIR / "CLAUDE.md"
        agents_md = CTF_DIR / "AGENTS.md"

        if claude_md.is_file():
            self.ok(f"{claude_md} exists")
            self.require_contains(claude_md, LIFECYCLE_RULES_MARKER, "~/CTF/CLAUDE.md", hard=False)
        else:
            self.fail(f"{claude_md} missing; run bash install.sh")

        if not agents_md.exists():
            self.fail(f"{agents_md} missing; Codex launched from ~/CTF will not load project instructions")
            return

        self.ok(f"{agents_md} exists")
        self.require_contains(agents_md, LIFECYCLE_RULES_MARKER, "~/CTF/AGENTS.md", hard=False)
        if agents_md.is_symlink():
            target = agents_md.resolve()
            if target == claude_md.resolve():
                self.ok("~/CTF/AGENTS.md is a symlink to ~/CTF/CLAUDE.md")
            else:
                self.warn(f"~/CTF/AGENTS.md symlink points to {target}, not ~/CTF/CLAUDE.md")
            return

        if claude_md.is_file() and agents_md.is_file():
            if agents_md.read_bytes() == claude_md.read_bytes():
                self.ok("~/CTF/AGENTS.md content is synchronized with ~/CTF/CLAUDE.md")
            else:
                self.warn("~/CTF/AGENTS.md exists but is not synchronized with ~/CTF/CLAUDE.md")

    def check_personal_skill(self) -> None:
        skill = HOME / ".agents" / "skills" / "ctf-personal"
        skill_file = skill / "SKILL.md"
        if skill_file.is_file():
            self.ok("~/.agents/skills/ctf-personal exists")
        else:
            self.fail("~/.agents/skills/ctf-personal missing; run bash install.sh")

    def _external_skills_under(self, base: Path) -> set[str]:
        found: set[str] = set()
        for name in sorted(EXTERNAL_SKILL_NAMES):
            if (base / name / "SKILL.md").is_file():
                found.add(name)
        return found

    def check_external_skills(self) -> None:
        locations = {
            "~/.agents/skills": HOME / ".agents" / "skills",
            "~/CTF/.agents/skills": CTF_DIR / ".agents" / "skills",
            "~/ctf-solver/.agents/skills": ROOT / ".agents" / "skills",
        }
        found_by_label: dict[str, set[str]] = {}
        for label, base in locations.items():
            found = self._external_skills_under(base)
            found_by_label[label] = found
            if found:
                self.info(f"external CTF skills detected under {label}: {len(found)} skills")
            else:
                self.info(f"external CTF skills not detected under {label}")

        global_skills = found_by_label["~/.agents/skills"]
        repo_local = found_by_label["~/ctf-solver/.agents/skills"]
        missing_global = EXTERNAL_SKILL_NAMES - global_skills

        if not missing_global:
            self.ok("all optional external CTF skills are available under ~/.agents/skills")

        repo_only = repo_local - global_skills
        if repo_only:
            self.warn(
                "Some external CTF skills are present only under repo-local .agents; "
                "Codex launched from ~/CTF may not see: " + ", ".join(sorted(repo_only))
            )

    def _collect_mcp_server_names(self, node: object) -> set[str]:
        names: set[str] = set()
        if isinstance(node, dict):
            servers = node.get("mcpServers")
            if isinstance(servers, dict):
                names.update(str(name) for name in servers.keys())
            for value in node.values():
                names.update(self._collect_mcp_server_names(value))
        elif isinstance(node, list):
            for item in node:
                names.update(self._collect_mcp_server_names(item))
        return names

    def check_claude_mcp_registration(self) -> None:
        if os.environ.get("CTF_DOCTOR_INSPECT_CLAUDE_CONFIG") != "1":
            self.info("Claude MCP registration not inspected by default; set CTF_DOCTOR_INSPECT_CLAUDE_CONFIG=1 to opt in")
            return
        config = HOME / ".claude.json"
        if not config.is_file():
            self.info("Claude config not found; Claude MCP registration is optional")
            return

        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.warn(f"Could not inspect Claude MCP registration safely: {exc}")
            return

        names = self._collect_mcp_server_names(data)
        if CANONICAL_MCP_NAME in names:
            self.info(f"Claude MCP {CANONICAL_MCP_NAME} appears registered (optional)")
        else:
            self.info(f"Claude MCP {CANONICAL_MCP_NAME} not registered (optional)")

        if LEGACY_MCP_NAME in names:
            self.warn(
                f"legacy Claude MCP {LEGACY_MCP_NAME} appears registered; "
                f"prefer {CANONICAL_MCP_NAME} after manual migration review"
            )

    def check_mcp_names(self) -> None:
        server = (ROOT / "server.py").read_text(encoding="utf-8")
        if f'FastMCP("{CANONICAL_MCP_NAME}")' in server:
            self.ok(f"server.py MCP name is {CANONICAL_MCP_NAME}")
        else:
            self.fail(f"server.py MCP name is not {CANONICAL_MCP_NAME}")
        tools_doc = ROOT / "docs" / "tools.md"
        if tools_doc.is_file() and "`verify_run`" in tools_doc.read_text(encoding="utf-8", errors="replace"):
            self.ok("docs/tools.md includes verify_run")
        else:
            self.fail("docs/tools.md missing verify_run; run scripts/dump_mcp_tools.py --write")

        checked_paths = [
            ROOT / "server.py",
            ROOT / "config" / "CLAUDE.base.md",
        ]
        docs_dir = ROOT / "docs"
        if docs_dir.is_dir():
            checked_paths.extend(sorted(docs_dir.glob("*.md")))

        stale = []
        for path in checked_paths:
            if path.is_file() and LEGACY_MCP_NAME in path.read_text(encoding="utf-8", errors="replace"):
                stale.append(str(path.relative_to(ROOT)))
        if stale:
            self.warn(
                f"legacy MCP server name {LEGACY_MCP_NAME} detected in runtime docs/config; "
                f"prefer {CANONICAL_MCP_NAME}: " + ", ".join(stale)
            )
        else:
            self.ok("runtime MCP server-name strings are consistent")

    def summary(self) -> int:
        print("")
        print(f"Hard failures: {len(self.failures)}")
        print(f"Optional warnings: {len(self.warnings)}")
        return 1 if self.failures else 0


def main() -> int:
    doctor = Doctor()
    if not (ROOT / ".git").is_dir():
        doctor.fail(f"{ROOT} is not a git repo")
    else:
        doctor.ok(f"repo root: {ROOT}")

    for relative in [
        "install.sh",
        "config/deploy.sh",
        "config/CLAUDE.base.md",
        "config/mac/env.md",
        "config/windows/env.md",
        "Dockerfile.ctf",
        "server.py",
    ]:
        doctor.require_file(relative)

    doctor.check_agents_generation()
    doctor.run_syntax("install.sh")
    doctor.run_syntax("config/deploy.sh")
    doctor.check_tools()
    doctor.check_lifecycle()
    doctor.check_ctf_workspace()
    doctor.check_personal_skill()
    doctor.check_external_skills()
    doctor.docker_status()
    doctor.check_docker_gdb_smoke_availability()
    doctor.command_version("codex", optional=True)
    doctor.command_version("claude", optional=True)
    doctor.check_claude_mcp_registration()
    doctor.check_mcp_names()

    return doctor.summary()


if __name__ == "__main__":
    raise SystemExit(main())
