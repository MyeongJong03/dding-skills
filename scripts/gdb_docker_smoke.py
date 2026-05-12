#!/usr/bin/env python3
"""Optional Docker GDB runtime smoke validation with a local toy crash binary."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.gdb_session import (
    DEFAULT_IMAGE,
    GdbSessionError,
    backtrace,
    close_gdb,
    registers,
    start_gdb,
    telescope,
    vmmap,
    wait_crash,
)
from ctf_solver_core.paths import gdb_artifact_root, gdb_root, is_inside_repo
from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.sessions import ensure_private_dir


CRASH_SOURCE = """int main(void) {
    volatile int *p = 0;
    *p = 0x41414141;
    return 0;
}
"""


def _run(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _base_summary(image: str, keep_artifacts: bool) -> dict[str, object]:
    return {
        "ok": False,
        "status": "failed",
        "reason": "",
        "image": image,
        "workspace_kept": keep_artifacts,
        "workspace_name": "",
        "docker": {
            "cli": False,
            "daemon": False,
            "image": False,
            "gdb": False,
            "compiler": "",
        },
        "compile": {
            "ok": False,
            "compiler": "",
            "binary": "",
        },
        "gdb": {
            "session_started": False,
            "session_closed": False,
            "crashed": False,
            "signal": "",
            "runtime_issue": "",
            "pc_present": False,
            "register_count": 0,
            "backtrace_frame_count": 0,
            "vmmap_count": 0,
            "telescope_ran": False,
            "telescope_line_count": 0,
        },
        "roots": {
            "gdb_root_inside_repo": is_inside_repo(gdb_root()),
            "gdb_artifact_root_inside_repo": is_inside_repo(gdb_artifact_root()),
        },
        "errors": [],
    }


def _mark(summary: dict[str, object], status: str, reason: str) -> dict[str, object]:
    summary["status"] = status
    summary["ok"] = status == "passed"
    summary["reason"] = reason
    return summary


def _docker_base_args(docker: str, image: str) -> list[str]:
    return [
        docker,
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--network",
        "none",
        image,
    ]


def _check_container_tool(docker: str, image: str, names: tuple[str, ...]) -> str:
    script = " || ".join(f"command -v {name} >/dev/null 2>&1 && echo {name}" for name in names)
    result = _run([*_docker_base_args(docker, image), "bash", "-lc", script], timeout=20)
    if result.returncode != 0:
        return ""
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if candidate in names:
            return candidate
    return ""


def _check_prereqs(summary: dict[str, object], image: str) -> tuple[bool, str, str]:
    docker = shutil.which("docker")
    docker_summary = summary["docker"]
    assert isinstance(docker_summary, dict)
    if not docker:
        _mark(summary, "skipped", "Docker CLI not found")
        return False, "", ""
    docker_summary["cli"] = True

    info = _run([docker, "info"], timeout=10)
    if info.returncode != 0:
        _mark(summary, "skipped", "Docker daemon is not reachable")
        return False, docker, ""
    docker_summary["daemon"] = True

    inspect = _run([docker, "image", "inspect", image], timeout=10)
    if inspect.returncode != 0:
        _mark(summary, "skipped", f"Docker image {image} is not available")
        return False, docker, ""
    docker_summary["image"] = True

    gdb = _check_container_tool(docker, image, ("gdb",))
    if not gdb:
        _mark(summary, "skipped", f"gdb is not available inside {image}")
        return False, docker, ""
    docker_summary["gdb"] = True

    compiler = _check_container_tool(docker, image, ("gcc", "cc"))
    if not compiler:
        _mark(summary, "skipped", f"gcc/cc is not available inside {image}")
        return False, docker, ""
    docker_summary["compiler"] = compiler
    return True, docker, compiler


def _workspace_parent() -> Path:
    raw = os.environ.get("CTF_GDB_SMOKE_TMP_ROOT")
    parent = Path(raw).expanduser() if raw else gdb_artifact_root().parent / "tmp"
    parent = parent.resolve()
    ensure_private_dir(parent)
    return parent


def _compile_crash(
    *,
    docker: str,
    image: str,
    compiler: str,
    workspace: Path,
    summary: dict[str, object],
) -> bool:
    source = workspace / "crash.c"
    source.write_text(CRASH_SOURCE, encoding="utf-8")
    source.chmod(0o600)
    command = f"{compiler} -g -no-pie -o crash crash.c"
    result = _run(
        [
            docker,
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--network",
            "none",
            "-v",
            f"{workspace}:/workspace",
            "-w",
            "/workspace",
            image,
            "bash",
            "-lc",
            command,
        ],
        timeout=60,
    )
    compile_summary = summary["compile"]
    assert isinstance(compile_summary, dict)
    compile_summary["compiler"] = compiler
    if result.returncode != 0:
        reason = (result.stderr or result.stdout or "compile failed").strip().splitlines()
        _mark(summary, "failed", reason[-1] if reason else "compile failed")
        return False
    binary = workspace / "crash"
    if not binary.is_file():
        _mark(summary, "failed", "compile command succeeded but crash binary was not created")
        return False
    compile_summary["ok"] = True
    compile_summary["binary"] = binary.name
    return True


def _run_gdb_flow(
    *,
    workspace: Path,
    image: str,
    timeout_ms: int,
    max_bytes: int,
    summary: dict[str, object],
) -> None:
    gdb_summary = summary["gdb"]
    assert isinstance(gdb_summary, dict)
    sid = ""
    try:
        started = start_gdb(
            binary_path=str(workspace / "crash"),
            mode="docker",
            workspace=str(workspace),
            run_id="docker-gdb-smoke",
            challenge_id="local-toy-crash",
            image=image,
            timeout_ms=timeout_ms,
            max_bytes=max_bytes,
        )
        sid = str((started.get("gdb_session") or {}).get("gdb_session_id") or "")
        gdb_summary["session_started"] = bool(sid)

        crash = wait_crash(sid, timeout_ms=timeout_ms, max_bytes=max_bytes)
        crash_output = str(crash.get("output") or "")
        if "couldn't get registers" in crash_output.lower():
            gdb_summary["runtime_issue"] = "GDB could not read registers in this Docker runtime"
        crash_info = crash.get("crash_info") if isinstance(crash.get("crash_info"), dict) else {}
        gdb_summary["crashed"] = bool(crash.get("crashed"))
        gdb_summary["signal"] = str(crash_info.get("signal") or "")
        gdb_summary["pc_present"] = bool(crash_info.get("pc"))

        regs = registers(sid, timeout_ms=timeout_ms, max_bytes=max_bytes)
        reg_output = str(regs.get("output") or "")
        if "couldn't get registers" in reg_output.lower():
            gdb_summary["runtime_issue"] = "GDB could not read registers in this Docker runtime"
        parsed_regs = regs.get("registers") if isinstance(regs.get("registers"), dict) else {}
        gdb_summary["register_count"] = len(parsed_regs)

        bt = backtrace(sid, timeout_ms=timeout_ms, max_bytes=max_bytes)
        bt_output = str(bt.get("output") or "")
        if "couldn't get registers" in bt_output.lower():
            gdb_summary["runtime_issue"] = "GDB could not read registers in this Docker runtime"
        bt_summary = bt.get("backtrace") if isinstance(bt.get("backtrace"), dict) else {}
        gdb_summary["backtrace_frame_count"] = int(bt_summary.get("frame_count") or 0)

        mappings = vmmap(sid, timeout_ms=timeout_ms, max_bytes=max_bytes).get("mappings")
        if isinstance(mappings, list):
            gdb_summary["vmmap_count"] = len(mappings)

        address = str(parsed_regs.get("rip") or parsed_regs.get("pc") or crash_info.get("pc") or "")
        if address:
            tel = telescope(sid, address=address, count=4, timeout_ms=timeout_ms, max_bytes=max_bytes)
            tel_summary = tel.get("telescope") if isinstance(tel.get("telescope"), dict) else {}
            gdb_summary["telescope_ran"] = True
            gdb_summary["telescope_line_count"] = int(tel_summary.get("line_count") or 0)
    finally:
        if sid:
            try:
                close_gdb(sid, reason="docker_gdb_smoke")
                gdb_summary["session_closed"] = True
            except Exception as exc:  # pragma: no cover - best-effort cleanup
                errors = summary["errors"]
                assert isinstance(errors, list)
                errors.append(f"gdb_close failed: {exc}")


def run_smoke(
    *,
    image: str,
    keep_artifacts: bool,
    timeout_ms: int,
    max_bytes: int,
) -> dict[str, object]:
    summary = _base_summary(image, keep_artifacts)
    if summary["roots"]["gdb_root_inside_repo"] or summary["roots"]["gdb_artifact_root_inside_repo"]:  # type: ignore[index]
        return _mark(summary, "failed", "GDB roots must resolve outside the repo")

    ok, docker, compiler = _check_prereqs(summary, image)
    if not ok:
        return summary

    workspace = Path(tempfile.mkdtemp(prefix="gdb-docker-smoke-", dir=_workspace_parent()))
    summary["workspace_name"] = workspace.name
    try:
        if not _compile_crash(docker=docker, image=image, compiler=compiler, workspace=workspace, summary=summary):
            return summary
        try:
            _run_gdb_flow(workspace=workspace, image=image, timeout_ms=timeout_ms, max_bytes=max_bytes, summary=summary)
        except (GdbSessionError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            errors = summary["errors"]
            assert isinstance(errors, list)
            errors.append(str(exc))
            return _mark(summary, "failed", str(exc))

        gdb_summary = summary["gdb"]
        assert isinstance(gdb_summary, dict)
        if gdb_summary.get("runtime_issue"):
            return _mark(summary, "skipped", str(gdb_summary["runtime_issue"]))
        if not gdb_summary.get("crashed") or gdb_summary.get("signal") != "SIGSEGV":
            return _mark(summary, "failed", "GDB did not report the expected SIGSEGV")
        if not (
            int(gdb_summary.get("register_count") or 0)
            or int(gdb_summary.get("backtrace_frame_count") or 0)
            or int(gdb_summary.get("vmmap_count") or 0)
        ):
            return _mark(summary, "failed", "GDB did not return registers, backtrace, or vmmap data")
        return _mark(summary, "passed", "Docker GDB smoke detected SIGSEGV on local toy binary")
    finally:
        if keep_artifacts:
            summary["workspace_kept"] = True
        else:
            shutil.rmtree(workspace, ignore_errors=True)


def _print_text(summary: dict[str, object]) -> None:
    print(f"status: {summary['status']}")
    print(f"reason: {summary['reason']}")
    gdb = summary.get("gdb") if isinstance(summary.get("gdb"), dict) else {}
    print(
        "gdb: "
        f"crashed={gdb.get('crashed')} "
        f"signal={gdb.get('signal') or '-'} "
        f"registers={gdb.get('register_count')} "
        f"backtrace_frames={gdb.get('backtrace_frame_count')} "
        f"vmmap={gdb.get('vmmap_count')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument("--max-bytes", type=int, default=12000)
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = run_smoke(
        image=args.image,
        keep_artifacts=args.keep_artifacts,
        timeout_ms=args.timeout_ms,
        max_bytes=args.max_bytes,
    )
    if args.json:
        print(json_dumps(summary), end="")
    else:
        _print_text(summary)
    return 1 if summary.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
