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
    browser_state_root,
    download_root,
    display_path,
    is_inside_repo,
    lease_root,
    local_run_root,
    lock_root,
    metrics_root,
    platform_automation_root,
    queue_root,
    session_root,
    sessiond_root,
    solved_writeup_root,
    worker_root,
)
from ctf_solver_core.browser_state import browser_profile_count
from ctf_solver_core.platform_automation import download_metadata_count, platform_server_record_count
from ctf_solver_core.platform_adapters import get_adapter
from ctf_solver_core.platforms import platform_config_path, validate_platform_config
from ctf_solver_core.resources import detect_stale_leases, list_leases
from ctf_solver_core.schemas import read_jsonl, validate_public_record
from ctf_solver_core.session_client import status as session_daemon_status
from ctf_solver_core.worker import detect_stale_claims, list_claims

HOME = Path.home()
CTF_DIR = HOME / "CTF"
CANONICAL_MCP_NAME = "ctf_solver"
LEGACY_MCP_NAME = "".join(("dreamhack", "_solver"))
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
            "scripts/verify_run.py",
            "scripts/browser_state_init.py",
            "scripts/browser_state_check.py",
            "scripts/platform_discover.py",
            "scripts/platform_download.py",
            "scripts/platform_server_acquire.py",
            "scripts/platform_server_release.py",
            "scripts/platform_server_status.py",
            "scripts/platform_submit.py",
            "scripts/platform_smoke_test.py",
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
            "ctf_solver_core/verifier.py",
            "ctf_solver_core/browser_state.py",
            "ctf_solver_core/platform_automation.py",
            "ctf_solver_core/platform_adapters.py",
            "ctf_solver_core/adapters/ctfd.py",
            "config/platforms.example.yaml",
            "docs/platform-automation.md",
            "docs/browser-platform-automation.md",
            "docs/ctfd-adapter.md",
            "docs/worker-runner.md",
            "docs/sessions.md",
            "docs/verifier.md",
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

        ctfd_doc = ROOT / "docs" / "ctfd-adapter.md"
        if ctfd_doc.is_file() and "CTFd adapter" in ctfd_doc.read_text(encoding="utf-8", errors="replace"):
            self.ok("docs/ctfd-adapter.md mentions CTFd adapter")
        else:
            self.fail("docs/ctfd-adapter.md missing CTFd adapter documentation")

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
        summary = metrics / "summary.jsonl"
        if summary.exists():
            metric_errors: list[str] = []
            for index, record in enumerate(read_jsonl(summary), start=1):
                metric_errors.extend(f"summary.jsonl:{index}: {error}" for error in validate_public_record(record))
            if metric_errors:
                for error in metric_errors:
                    self.fail(f"public metrics unsafe: {error}")
            else:
                self.ok("public metrics safety check passed")
        else:
            self.ok("metrics/summary.jsonl absent; no public metrics to validate")

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
        locks = lock_root()
        leases = lease_root()
        queue = queue_root()
        workers = worker_root()
        sessions = session_root()
        sessiond = sessiond_root()
        browser_states = browser_state_root()
        platform_auto = platform_automation_root()
        downloads = download_root()
        self.info(f"writeup root: {display_path(writeup_root)}")
        self.info(f"private run root: {display_path(run_root)}")
        self.info(f"lock root: {display_path(locks)}")
        self.info(f"lease root: {display_path(leases)}")
        self.info(f"queue root: {display_path(queue)}")
        self.info(f"worker root: {display_path(workers)}")
        self.info(f"session root: {display_path(sessions)}")
        self.info(f"session daemon root: {display_path(sessiond)}")
        self.info(f"browser state root: {display_path(browser_states)}")
        self.info(f"platform automation root: {display_path(platform_auto)}")
        self.info(f"download root: {display_path(downloads)}")

        if is_inside_repo(writeup_root):
            self.fail("writeup root is inside repo; local-only writeups could be staged accidentally")
        if is_inside_repo(run_root):
            self.fail("private run root is inside repo; private logs could be staged accidentally")
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
        if is_inside_repo(browser_states):
            self.warn("browser state root is inside repo; prefer ~/.ctf-solver/browser-states or CTF_BROWSER_STATE_ROOT outside repo")
        if is_inside_repo(platform_auto):
            self.warn("platform automation root is inside repo; prefer ~/.ctf-solver/platforms or CTF_PLATFORM_AUTOMATION_ROOT outside repo")
        if is_inside_repo(downloads):
            self.warn("download root is inside repo; prefer ~/CTF/downloads or CTF_DOWNLOAD_ROOT outside repo")
        try:
            daemon = session_daemon_status()
            if daemon.get("running"):
                self.info(f"session daemon running pid={daemon.get('pid')} {daemon.get('host')}:{daemon.get('port')}")
            else:
                self.info("session daemon not running (optional)")
        except Exception as exc:
            self.warn(f"could not inspect session daemon safely: {exc}")
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
            self.info(f"platform server record count: {platform_server_record_count()}")
            self.info(f"download metadata count: {download_metadata_count()}")
        except Exception as exc:
            self.warn(f"could not inspect platform automation counts safely: {exc}")
        self.ok("metrics are repo-local public-safe targets; writeups/private runs are local-only targets")

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
    doctor.command_version("codex", optional=True)
    doctor.command_version("claude", optional=True)
    doctor.check_claude_mcp_registration()
    doctor.check_mcp_names()

    return doctor.summary()


if __name__ == "__main__":
    raise SystemExit(main())
