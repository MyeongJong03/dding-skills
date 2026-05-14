#!/usr/bin/env python3
"""Fixture-only end-to-end platform lifecycle smoke test."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps, read_jsonl, validate_public_record


STAGE_KEYS = (
    "discovery_ok",
    "queue_ok",
    "download_ok",
    "init_ok",
    "verifier_ok",
    "finalize_ok",
    "writeup_ok",
    "metrics_ok",
    "cleanup_ok",
    "public_safe_ok",
)
EVENT = "offline-e2e"
SAFE_REASON_RE = re.compile(r"(/Users/[^\\s'\"]+|/home/[^\\s'\"]+|/private/[^\\s'\"]+|/var/[^\\s'\"]+)")
CURRENT_SUMMARY: dict[str, Any] | None = None


class SmokeFailure(RuntimeError):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
        self.progress = dict(CURRENT_SUMMARY or {})


def _is_url(value: str | None) -> bool:
    if not value:
        return False
    return urlparse(value).scheme in {"http", "https"}


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _safe_reason(reason: object) -> str:
    text = str(reason or "unknown_failure").strip() or "unknown_failure"
    text = SAFE_REASON_RE.sub("<local-path>", text)
    return text[:240]


def _parse_json(text: str) -> dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("json_output_not_object")
    return data


def _run(script: str, args: list[str], env: dict[str, str], *, json_output: bool = True) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / script), *args]
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    parsed: dict[str, Any] = {}
    if json_output and result.stdout.strip():
        try:
            parsed = _parse_json(result.stdout)
        except Exception:
            parsed = {}
    if result.returncode != 0:
        reason = parsed.get("reason") or f"{Path(script).name}_failed_rc_{result.returncode}"
        raise SmokeFailure(Path(script).stem, _safe_reason(reason))
    if json_output and not parsed:
        raise SmokeFailure(Path(script).stem, "json_output_missing")
    return parsed


def _write_policy(path: Path, platform: str) -> None:
    auth_mode = "manual" if platform == "dreamhack" else "none"
    max_active = 1 if platform == "dreamhack" else 0
    provisioning = "false"
    path.write_text(
        f"""platforms:
  - platform: {platform}
    event: {EVENT}
    adapter: {platform}
    auth:
      mode: {auth_mode}
    resources:
      remote_server:
        provisioning: {provisioning}
        max_active_leases: {max_active}
        lease_scope: platform_event
        release_required_before_next: true
        sharing:
          allowed: false
          max_workers: 1
          mode: exclusive
          destructive_actions_require_primary: true
    automation:
      allow_problem_discovery: true
      allow_file_download: true
      allow_server_create: false
      allow_submission: false
""",
        encoding="utf-8",
    )


def _env(temp_root: Path, platform: str) -> dict[str, str]:
    home = temp_root / "home"
    public_repo = temp_root / "public-repo"
    policy = temp_root / "platforms.yaml"
    for path in (
        home,
        temp_root / "work",
        temp_root / "runs",
        temp_root / "locks",
        temp_root / "writeups",
        temp_root / "leases",
        temp_root / "queue",
        temp_root / "workers",
        temp_root / "sessions",
        temp_root / "sessiond",
        temp_root / "gdb",
        temp_root / "gdb-artifacts",
        temp_root / "browser",
        temp_root / "browser-artifacts",
        temp_root / "browser-states",
        temp_root / "callbacks",
        temp_root / "callbackd",
        temp_root / "web-workflows",
        temp_root / "platforms",
        temp_root / "downloads",
        temp_root / "metrics-private",
        public_repo / "metrics",
    ):
        path.mkdir(parents=True, exist_ok=True)
    _write_policy(policy, platform)
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(home),
            "CTF_WORK_ROOT": str(temp_root / "work"),
            "CTF_LOCAL_RUN_ROOT": str(temp_root / "runs"),
            "CTF_LOCK_ROOT": str(temp_root / "locks"),
            "CTF_SOLVED_WRITEUP_ROOT": str(temp_root / "writeups"),
            "CTF_LEASE_ROOT": str(temp_root / "leases"),
            "CTF_QUEUE_ROOT": str(temp_root / "queue"),
            "CTF_WORKER_ROOT": str(temp_root / "workers"),
            "CTF_SESSION_ROOT": str(temp_root / "sessions"),
            "CTF_SESSIOND_ROOT": str(temp_root / "sessiond"),
            "CTF_GDB_ROOT": str(temp_root / "gdb"),
            "CTF_GDB_ARTIFACT_ROOT": str(temp_root / "gdb-artifacts"),
            "CTF_BROWSER_ROOT": str(temp_root / "browser"),
            "CTF_BROWSER_ARTIFACT_ROOT": str(temp_root / "browser-artifacts"),
            "CTF_BROWSER_STATE_ROOT": str(temp_root / "browser-states"),
            "CTF_CALLBACK_ROOT": str(temp_root / "callbacks"),
            "CTF_CALLBACKD_ROOT": str(temp_root / "callbackd"),
            "CTF_WEB_WORKFLOW_ROOT": str(temp_root / "web-workflows"),
            "CTF_PLATFORM_AUTOMATION_ROOT": str(temp_root / "platforms"),
            "CTF_DOWNLOAD_ROOT": str(temp_root / "downloads"),
            "CTF_PRIVATE_METRICS_ROOT": str(temp_root / "metrics-private"),
            "CTF_SOLVER_REPO_ROOT": str(public_repo),
            "CTF_PLATFORM_CONFIG": str(policy),
            "CTF_METRICS_MODE": "public",
        }
    )
    for key in (
        "CTF_CTFD_COOKIE_FILE",
        "CTF_CTFD_COOKIE_HEADER",
        "CTF_DREAMHACK_SESSION_ID",
        "CTF_DREAMHACK_CSRF_TOKEN",
        "DREAMHACK_SESSION_ID",
        "DREAMHACK_CSRF_TOKEN",
    ):
        env.pop(key, None)
    return env


def _write_default_ctfd_fixture(root: Path, category: str, challenge_id: str | None) -> tuple[Path, Path]:
    fixture = root / "ctfd"
    attachments = fixture / "attachments"
    attachments.mkdir(parents=True, exist_ok=True)
    (attachments / "handout.txt").write_text("offline e2e ctfd attachment\n", encoding="utf-8")
    item: dict[str, Any] = {
        "id": 9001,
        "name": "Offline CTFd Smoke",
        "category": category,
        "value": 100,
        "solves": 0,
        "tags": [{"name": "offline-e2e"}],
        "files": [{"name": "handout.txt", "path": "attachments/handout.txt"}],
        "local_capable": True,
        "remote_required": False,
    }
    if challenge_id:
        item["challenge_id"] = challenge_id
    discovery = fixture / "discovery.json"
    discovery.write_text(json.dumps({"success": True, "data": [item]}, sort_keys=True), encoding="utf-8")
    detail = fixture / "detail.json"
    detail.write_text(
        json.dumps(
            {
                "success": True,
                "data": {
                    **item,
                    "description": "offline e2e parser detail",
                    "connection_info": "",
                    "hints": [],
                    "state": "visible",
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return discovery, detail


def _write_default_dreamhack_fixture(root: Path, category: str, challenge_id: str | None) -> tuple[Path, Path]:
    fixture = root / "dreamhack"
    attachments = fixture / "attachments"
    attachments.mkdir(parents=True, exist_ok=True)
    (attachments / "handout.txt").write_text("offline e2e dreamhack attachment\n", encoding="utf-8")
    item: dict[str, Any] = {
        "wargame_id": 424242,
        "title": "Offline Dreamhack Smoke",
        "category": {"name": category},
        "points": 100,
        "solves": 0,
        "tags": [{"name": "offline-e2e"}],
        "attachments": [{"name": "handout.txt", "path": "attachments/handout.txt"}],
        "has_vm": False,
        "local_capable": True,
        "remote_required": False,
    }
    if challenge_id:
        item["challenge_id"] = challenge_id
    discovery = fixture / "discovery.json"
    discovery.write_text(json.dumps({"success": True, "data": {"results": [item]}}, sort_keys=True), encoding="utf-8")
    detail = fixture / "detail.json"
    detail.write_text(
        json.dumps(
            {
                "success": True,
                "data": {
                    **item,
                    "description": "offline e2e parser detail",
                    "connection_info": "",
                    "hints": [],
                    "state": "visible",
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return discovery, detail


def _first_existing(root: Path, names: tuple[str, ...]) -> Path:
    for name in names:
        path = root / name
        if path.is_file():
            return path
    raise SmokeFailure("fixture", "fixture_file_missing")


def _fixture_paths(
    *,
    platform: str,
    fixture_root: str | None,
    temp_root: Path,
    category: str,
    challenge_id: str | None,
) -> tuple[Path, Path]:
    if fixture_root:
        if _is_url(fixture_root):
            raise SmokeFailure("fixture", "fixture_root_must_be_local")
        root = Path(fixture_root).expanduser().resolve()
        if not root.is_dir():
            raise SmokeFailure("fixture", "fixture_root_not_found")
        platform_root = root / platform
        if platform_root.is_dir():
            root = platform_root
        discovery = _first_existing(
            root,
            ("discovery.json", f"{platform}-discovery.json", "challenges.json", f"{platform}-challenges.json"),
        )
        detail = _first_existing(
            root,
            ("detail.json", f"{platform}-detail.json", "challenge-detail.json", f"{platform}-challenge.json"),
        )
        return discovery, detail
    if platform == "ctfd":
        return _write_default_ctfd_fixture(temp_root / "fixtures", category, challenge_id)
    return _write_default_dreamhack_fixture(temp_root / "fixtures", category, challenge_id)


def _choose_challenge(discovery: dict[str, Any], requested_id: str | None) -> dict[str, Any]:
    challenges = discovery.get("challenges")
    if not isinstance(challenges, list) or not challenges:
        raise SmokeFailure("discovery", "no_challenges_discovered")
    if requested_id:
        for item in challenges:
            if not isinstance(item, dict):
                continue
            candidates = {
                str(item.get("challenge_id") or ""),
                str(item.get("external_id") or ""),
                str(item.get("name") or ""),
                str(item.get("title") or ""),
            }
            if requested_id in candidates:
                return item
        raise SmokeFailure("discovery", "requested_challenge_not_found")
    first = challenges[0]
    if not isinstance(first, dict):
        raise SmokeFailure("discovery", "challenge_record_invalid")
    return first


def _check_public_metrics(metrics_root: Path, run_id: str) -> bool:
    summary = metrics_root / "summary.jsonl"
    records = read_jsonl(summary)
    if not any(record.get("run_id") == run_id for record in records):
        return False
    return all(not validate_public_record(record) for record in records)


def _run_flow(args: argparse.Namespace, temp_root: Path) -> dict[str, Any]:
    global CURRENT_SUMMARY
    summary: dict[str, Any] = {key: False for key in STAGE_KEYS}
    summary.update({"ok": False, "platform": args.platform})
    CURRENT_SUMMARY = summary
    env = _env(temp_root, args.platform)
    public_repo = temp_root / "public-repo"
    writeup_root = temp_root / "writeups"
    discovery_fixture, detail_fixture = _fixture_paths(
        platform=args.platform,
        fixture_root=args.fixture_root,
        temp_root=temp_root,
        category=args.category,
        challenge_id=args.challenge_id,
    )

    discovery = _run(
        "scripts/platform_discover.py",
        [
            "--platform",
            args.platform,
            "--event",
            EVENT,
            "--adapter",
            args.platform,
            "--source",
            str(discovery_fixture),
            "--json",
        ],
        env,
    )
    if not discovery.get("ok"):
        raise SmokeFailure("discovery", discovery.get("reason") or "discovery_failed")
    challenge = _choose_challenge(discovery, args.challenge_id)
    challenge_id = str(challenge.get("challenge_id") or args.challenge_id or "").strip()
    external_id = str(challenge.get("external_id") or "").strip()
    challenge_name = str(challenge.get("name") or challenge.get("title") or "Offline E2E Smoke")
    category = str(args.category or challenge.get("category") or "unknown")
    if not challenge_id:
        raise SmokeFailure("discovery", "challenge_id_missing")
    summary["discovery_ok"] = True
    summary["challenge_id"] = challenge_id

    queue = _run(
        "scripts/queue_update.py",
        [
            "--platform",
            args.platform,
            "--event",
            EVENT,
            "--challenge-id",
            challenge_id,
            "--category",
            category,
            "--state",
            "discovered",
            "--local-capable",
            "true",
            "--remote-required",
            "false",
            "--local-exploit-ready",
            "false",
            "--confidence",
            "0.5",
            "--destructive-risk",
            "0",
            "--reason",
            "offline_e2e_discovery",
        ],
        env,
    )
    if not queue.get("ok"):
        raise SmokeFailure("queue", "queue_update_failed")
    summary["queue_ok"] = True

    download_dest = temp_root / "downloads" / args.platform / "offline-e2e"
    download = _run(
        "scripts/platform_download.py",
        [
            "--platform",
            args.platform,
            "--event",
            EVENT,
            "--challenge-id",
            challenge_id if challenge_id else external_id,
            "--adapter",
            args.platform,
            "--source",
            str(detail_fixture),
            "--dest",
            str(download_dest),
            "--queue",
            "--json",
        ],
        env,
    )
    metadata = download.get("metadata") if isinstance(download.get("metadata"), dict) else {}
    if not download.get("ok") or int(metadata.get("file_count") or 0) < 1:
        raise SmokeFailure("download", download.get("reason") or "download_failed")
    summary["download_ok"] = True
    summary["downloaded_file_count"] = int(metadata.get("file_count") or 0)

    init = _run(
        "scripts/challenge_init.py",
        [
            "--platform",
            args.platform,
            "--event",
            EVENT,
            "--challenge-id",
            challenge_id,
            "--challenge-name",
            challenge_name,
            "--category",
            category,
            "--workspace",
            str(download_dest),
            "--json",
        ],
        env,
    )
    run_id = str(init.get("run_id") or "")
    run_dir = Path(str(init.get("run_dir") or ""))
    workspace = Path(str(init.get("workspace") or ""))
    if init.get("challenge_id") != challenge_id or not run_id or not run_dir.is_dir():
        raise SmokeFailure("init", "challenge_init_failed")
    summary["init_ok"] = True
    summary["run_id"] = run_id

    _run(
        "scripts/queue_update.py",
        [
            "--platform",
            args.platform,
            "--event",
            EVENT,
            "--challenge-id",
            challenge_id,
            "--run-id",
            run_id,
            "--category",
            category,
            "--state",
            "local_triage",
            "--local-capable",
            "true",
            "--remote-required",
            "false",
            "--local-exploit-ready",
            "false",
            "--confidence",
            "0.75",
            "--destructive-risk",
            "0",
            "--reason",
            "offline_e2e_run_bound",
        ],
        env,
    )

    (run_dir / "scratch" / "offline-e2e.tmp").write_text("delete me\n", encoding="utf-8")
    workspace_scratch = workspace / "scratch"
    workspace_scratch.mkdir(exist_ok=True)
    (workspace_scratch / "offline-e2e.tmp").write_text("delete me\n", encoding="utf-8")

    verifier = _run(
        "scripts/verify_run.py",
        [
            "--run-dir",
            str(run_dir),
            "--mode",
            "manual",
            "--evidence-text",
            "offline-e2e-ok",
            "--success-regex",
            "offline-e2e-ok",
            "--local",
            "--label",
            "offline-e2e",
            "--json",
        ],
        env,
    )
    if not verifier.get("success"):
        raise SmokeFailure("verifier", "verifier_failed")
    summary["verifier_ok"] = True

    finalized = _run(
        "scripts/challenge_finalize.py",
        [
            "--run-dir",
            str(run_dir),
            "--status",
            "solved",
            "--reason",
            "offline-e2e-smoke",
            "--generate-writeup",
            "--cleanup",
            "--update-metrics",
            "--require-verifier",
        ],
        env,
    )
    if finalized.get("status") != "solved":
        raise SmokeFailure("finalize", "finalize_failed")
    summary["finalize_ok"] = True

    writeup = finalized.get("writeup") if isinstance(finalized.get("writeup"), dict) else {}
    writeup_path = Path(str(writeup.get("writeup_path") or ""))
    writeup_ok = (
        bool(writeup.get("generated"))
        and writeup_path.is_file()
        and _is_relative_to(writeup_path, writeup_root)
        and not _is_relative_to(writeup_path, public_repo)
    )
    if not writeup_ok:
        raise SmokeFailure("writeup", "writeup_policy_check_failed")
    summary["writeup_ok"] = True

    metrics_result = finalized.get("metrics") if isinstance(finalized.get("metrics"), dict) else {}
    metrics_ok = bool(metrics_result.get("public_summary_updated")) and _check_public_metrics(
        public_repo / "metrics",
        run_id,
    )
    if not metrics_ok:
        raise SmokeFailure("metrics", "metrics_check_failed")
    _run("scripts/update_metrics.py", ["--check"], env, json_output=False)
    summary["metrics_ok"] = True

    cleanup = finalized.get("cleanup") if isinstance(finalized.get("cleanup"), dict) else {}
    cleanup_ok = bool(cleanup) and not (run_dir / "scratch").exists() and not workspace_scratch.exists()
    if not cleanup_ok:
        raise SmokeFailure("cleanup", "cleanup_policy_check_failed")
    summary["cleanup_ok"] = True

    public_errors = validate_public_record(summary)
    if public_errors:
        raise SmokeFailure("public_safe", "summary_not_public_safe")
    summary["public_safe_ok"] = True
    summary["ok"] = True
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=("ctfd", "dreamhack"))
    parser.add_argument("--fixture-root", help="local fixture directory; defaults to generated temp fixtures")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--category", default="web", choices=("web", "pwn", "crypto", "rev", "forensics", "misc", "osint", "unknown"))
    parser.add_argument("--challenge-id", help="explicit fixture challenge_id to carry through queue/init/finalize")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    temp_root = Path(tempfile.mkdtemp(prefix="ctf-offline-e2e-")).resolve()
    summary: dict[str, Any] = {key: False for key in STAGE_KEYS}
    summary.update({"ok": False, "platform": args.platform})
    try:
        summary = _run_flow(args, temp_root)
    except SmokeFailure as exc:
        if exc.progress:
            summary.update(exc.progress)
        summary[exc.stage + "_stage"] = False
        summary["reason"] = f"{exc.stage}:{_safe_reason(exc.reason)}"
    except Exception as exc:  # noqa: BLE001 - keep CLI failure bounded and public-safe.
        summary["reason"] = "unexpected:" + _safe_reason(exc.__class__.__name__)
    finally:
        if args.keep_temp:
            summary["temp_kept"] = True
        else:
            shutil.rmtree(temp_root, ignore_errors=True)
            summary["temp_kept"] = False
    if not summary.get("public_safe_ok"):
        if not validate_public_record({key: value for key, value in summary.items() if key != "reason"}):
            summary.setdefault("public_safe_ok", False)
    if args.json:
        print(json_dumps(summary), end="")
    else:
        status = "ok" if summary.get("ok") else f"failed: {summary.get('reason', 'unknown')}"
        print(f"offline e2e smoke {status}")
        for key in STAGE_KEYS:
            print(f"{key}: {bool(summary.get(key))}")
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
