"""GDB-specific pwn debug session scaffold.

The implementation stores metadata and bounded logs in local-only GDB roots and
uses the existing persistent session daemon for real local/Docker processes.
"""

from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess
import uuid

from ctf_solver_core.gdb_parsers import (
    parse_crash,
    parse_registers,
    parse_vmmap,
    summarize_backtrace,
    summarize_telescope,
)
from ctf_solver_core.paths import display_path, gdb_artifact_root, gdb_root, resolve_path
from ctf_solver_core.schemas import atomic_write_json, iso_now, read_json, utc_now
from ctf_solver_core.session_client import close_session, expect_session, start_session, write_session
from ctf_solver_core.sessions import bounded_text, ensure_private_dir, redact_text


GDB_MODES = ("docker", "local", "mock")
GDB_STATUSES = ("starting", "running", "stopped", "crashed", "closed", "failed")
DEFAULT_IMAGE = "ctf-pwn:latest"
DEFAULT_TIMEOUT_MS = 2000
DEFAULT_MAX_BYTES = 8000
PROMPT = "(gdb)"


class GdbSessionError(RuntimeError):
    """Raised when a GDB session operation cannot be completed."""


def make_gdb_session_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"gdb-{stamp}-{uuid.uuid4().hex[:8]}"


def gdb_session_dir(gdb_session_id: str) -> Path:
    return gdb_root() / gdb_session_id


def gdb_metadata_path(gdb_session_id: str) -> Path:
    return gdb_session_dir(gdb_session_id) / "gdb_session.json"


def gdb_log_path(gdb_session_id: str) -> Path:
    return gdb_session_dir(gdb_session_id) / "gdb.log"


def gdb_artifact_dir(gdb_session_id: str) -> Path:
    return gdb_artifact_root() / gdb_session_id


def _write_private_json(path: Path, data: dict[str, object]) -> None:
    ensure_private_dir(path.parent)
    atomic_write_json(path, data)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _append_log(gdb_session_id: str, text: str) -> None:
    log = gdb_log_path(gdb_session_id)
    ensure_private_dir(log.parent)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(redact_text(text))
        if not text.endswith("\n"):
            handle.write("\n")
    try:
        log.chmod(0o600)
    except OSError:
        pass


def load_gdb_session(gdb_session_id: str) -> dict[str, object]:
    data = read_json(gdb_metadata_path(gdb_session_id), default={})
    if not isinstance(data, dict) or not data.get("gdb_session_id"):
        raise GdbSessionError(f"unknown GDB session: {gdb_session_id}")
    return data


def save_gdb_session(metadata: dict[str, object]) -> None:
    metadata["updated_at"] = iso_now()
    _write_private_json(gdb_metadata_path(str(metadata["gdb_session_id"])), metadata)


def _public_session(metadata: dict[str, object]) -> dict[str, object]:
    crash = metadata.get("crash_info") if isinstance(metadata.get("crash_info"), dict) else {}
    return {
        "gdb_session_id": metadata.get("gdb_session_id"),
        "run_id": metadata.get("run_id"),
        "challenge_id": metadata.get("challenge_id"),
        "worker_id": metadata.get("worker_id"),
        "mode": metadata.get("mode"),
        "status": metadata.get("status"),
        "created_at": metadata.get("created_at"),
        "updated_at": metadata.get("updated_at"),
        "binary": Path(str(metadata.get("binary_path") or "")).name,
        "command_count": int(metadata.get("command_count") or 0),
        "bytes_read": int(metadata.get("bytes_read") or 0),
        "bytes_written": int(metadata.get("bytes_written") or 0),
        "crash_info": {
            "signal": crash.get("signal", ""),
            "pc": crash.get("pc", ""),
            "fault_addr": crash.get("fault_addr", ""),
            "summary": crash.get("summary", ""),
        }
        if crash
        else {},
    }


def list_gdb_sessions(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    include_closed: bool = False,
) -> dict[str, object]:
    sessions: list[dict[str, object]] = []
    root = gdb_root()
    for path in sorted(root.glob("*/gdb_session.json")):
        data = read_json(path, default={})
        if not isinstance(data, dict):
            continue
        if run_id and data.get("run_id") != run_id:
            continue
        if challenge_id and data.get("challenge_id") != challenge_id:
            continue
        if not include_closed and data.get("status") in {"closed", "failed"}:
            continue
        sessions.append(_public_session(data))
    sessions.sort(key=lambda item: str(item.get("created_at") or ""))
    return {"sessions": sessions, "count": len(sessions)}


def active_gdb_session_count() -> int:
    return int(list_gdb_sessions(include_closed=False).get("count") or 0)


def _docker_available(image: str) -> tuple[bool, str]:
    docker = shutil.which("docker")
    if not docker:
        return False, "Docker CLI not found; install Docker or use --mode local/mock"
    info = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=10)
    if info.returncode != 0:
        return False, "Docker daemon is not reachable; start Docker Desktop or use --mode local/mock"
    inspect = subprocess.run([docker, "image", "inspect", image], capture_output=True, text=True, timeout=10)
    if inspect.returncode != 0:
        return False, f"Docker image {image!r} is not available; build Dockerfile.ctf first"
    return True, ""


def _resolve_workspace(binary: Path, workspace: str | None) -> tuple[Path, str]:
    workspace_path = resolve_path(workspace) if workspace else binary.parent.resolve()
    try:
        rel = binary.resolve().relative_to(workspace_path.resolve())
    except ValueError:
        workspace_path = binary.parent.resolve()
        rel = binary.name
    else:
        rel = rel.as_posix()
    return workspace_path, f"/workspace/{rel}"


def _gdb_argv(binary: str, args: str | None) -> list[str]:
    argv = ["gdb", "-q", "--nx", "--args", binary]
    if args:
        argv.extend(shlex.split(args))
    return argv


def _mock_output(cmd: str) -> str:
    stripped = cmd.strip()
    if stripped in {"continue", "c", "run", "r"}:
        return (
            "Continuing.\n\n"
            "Program received signal SIGSEGV, Segmentation fault.\n"
            "0x0000000000401234 in vuln ()\n"
            "rip            0x401234            0x401234 <vuln+52>\n"
            "rsp            0x7fffffffdde0      0x7fffffffdde0\n"
            f"{PROMPT} "
        )
    if "info registers" in stripped:
        return (
            "rax            0x0                 0\n"
            "rbx            0x4141414141414141  4702111234474983745\n"
            "rip            0x401234            0x401234 <vuln+52>\n"
            "rsp            0x7fffffffdde0      0x7fffffffdde0\n"
            f"{PROMPT} "
        )
    if stripped == "bt" or stripped.startswith("backtrace"):
        return (
            "#0  0x0000000000401234 in vuln ()\n"
            "#1  0x0000000000401299 in main ()\n"
            f"{PROMPT} "
        )
    if "vmmap" in stripped or "info proc mappings" in stripped:
        return (
            "0x0000000000400000 0x0000000000410000 r-xp 00000000 /workspace/chall\n"
            "0x00007ffff7dd0000 0x00007ffff7ffd000 r-xp 00000000 /lib/x86_64-linux-gnu/libc.so.6\n"
            "0x00007ffffffde000 0x00007ffffffff000 rw-p 00000000 [stack]\n"
            f"{PROMPT} "
        )
    if "telescope" in stripped or stripped.startswith("x/"):
        return (
            "00:0000| rsp 0x7fffffffdde0 -> 0x4141414141414141\n"
            "01:0008|     0x7fffffffdde8 -> 0x0000000000401299\n"
            f"{PROMPT} "
        )
    return f"{stripped}\n{PROMPT} "


def start_gdb(
    *,
    binary_path: str,
    mode: str = "docker",
    workspace: str | None = None,
    run_id: str | None = None,
    challenge_id: str | None = None,
    worker_id: str | None = None,
    args: str | None = None,
    breakpoint: list[str] | None = None,
    image: str = DEFAULT_IMAGE,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, object]:
    if mode not in GDB_MODES:
        raise GdbSessionError(f"unsupported GDB mode: {mode}")
    binary = resolve_path(binary_path)
    if not binary.is_file():
        raise GdbSessionError(f"binary not found: {binary}")
    gdb_session_id = make_gdb_session_id()
    now = iso_now()
    ensure_private_dir(gdb_session_dir(gdb_session_id))
    ensure_private_dir(gdb_artifact_dir(gdb_session_id))
    workspace_path = resolve_path(workspace) if workspace else binary.parent.resolve()
    command = ""
    backend_session_id = ""
    status = "running"
    startup_output = ""

    if mode == "mock":
        command = "mock-gdb " + shlex.quote(str(binary))
    elif mode == "docker":
        ok, reason = _docker_available(image)
        if not ok:
            raise GdbSessionError(reason)
        workspace_path, container_binary = _resolve_workspace(binary, workspace)
        command = shlex.join(_gdb_argv(container_binary, args))
        backend = start_session(
            kind="docker-shell",
            command=command,
            cwd=str(workspace_path),
            workspace=str(workspace_path),
            image=image,
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            timeout_ms=timeout_ms,
        )
        backend_session_id = str((backend.get("session") or {}).get("session_id") or "")
    else:
        gdb = shutil.which("gdb")
        if not gdb:
            raise GdbSessionError("local gdb executable not found; use --mode docker/mock")
        command = shlex.join([gdb, "-q", "--nx", "--args", str(binary), *shlex.split(args or "")])
        backend = start_session(
            kind="shell",
            command=command,
            cwd=str(workspace_path),
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            timeout_ms=timeout_ms,
        )
        backend_session_id = str((backend.get("session") or {}).get("session_id") or "")

    metadata: dict[str, object] = {
        "schema_version": 1,
        "gdb_session_id": gdb_session_id,
        "backend_session_id": backend_session_id,
        "run_id": run_id or "",
        "challenge_id": challenge_id or "",
        "worker_id": worker_id or "",
        "mode": mode,
        "binary_path": str(binary),
        "cwd": str(workspace_path),
        "container_id": "",
        "status": status,
        "created_at": now,
        "updated_at": now,
        "command": redact_text(command),
        "last_output_preview": "",
        "crash_info": {},
        "registers": {},
        "bytes_read": 0,
        "bytes_written": 0,
        "command_count": 0,
        "closed_at": "",
        "close_reason": "",
        "artifact_dir": str(gdb_artifact_dir(gdb_session_id)),
    }
    save_gdb_session(metadata)
    if mode != "mock":
        startup = expect_session(backend_session_id, [PROMPT], timeout_ms=timeout_ms, max_bytes=max_bytes)
        startup_output = str(startup.get("output") or "")
        _record_output(metadata, "<start>", startup_output, bytes_read=int(startup.get("bytes_read") or 0))
        if startup.get("timed_out"):
            metadata["status"] = "failed"
            metadata["close_reason"] = "gdb_prompt_timeout"
            save_gdb_session(metadata)
            raise GdbSessionError("GDB did not reach prompt; check binary, gdb, Docker, or ptrace permissions")
        run_gdb_cmd(gdb_session_id, "set pagination off", timeout_ms=timeout_ms, max_bytes=max_bytes)
        run_gdb_cmd(gdb_session_id, "set confirm off", timeout_ms=timeout_ms, max_bytes=max_bytes)
    for bp in breakpoint or []:
        run_gdb_cmd(gdb_session_id, f"break {bp}", timeout_ms=timeout_ms, max_bytes=max_bytes)
    return {
        "gdb_session": _public_session(load_gdb_session(gdb_session_id)),
        "startup_output": bounded_text(startup_output, max_bytes=max_bytes),
        "metadata_path": str(gdb_metadata_path(gdb_session_id)),
        "log_path": str(gdb_log_path(gdb_session_id)),
        "artifact_dir": str(gdb_artifact_dir(gdb_session_id)),
        "display_metadata_path": display_path(gdb_metadata_path(gdb_session_id)),
        "display_artifact_dir": display_path(gdb_artifact_dir(gdb_session_id)),
    }


def _record_output(
    metadata: dict[str, object],
    cmd: str,
    output: str,
    *,
    bytes_read: int | None = None,
    bytes_written: int | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> None:
    metadata["last_output_preview"] = bounded_text(output, max_bytes=max_bytes)
    if bytes_read is None:
        bytes_read = len(output.encode("utf-8", errors="replace"))
    metadata["bytes_read"] = int(metadata.get("bytes_read") or 0) + max(0, int(bytes_read))
    if bytes_written is not None:
        metadata["bytes_written"] = int(metadata.get("bytes_written") or 0) + max(0, int(bytes_written))
    _append_log(str(metadata["gdb_session_id"]), f"$ {cmd}\n{output}")
    save_gdb_session(metadata)


def run_gdb_cmd(
    gdb_session_id: str,
    cmd: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, object]:
    metadata = load_gdb_session(gdb_session_id)
    if metadata.get("status") in {"closed", "failed"}:
        raise GdbSessionError(f"GDB session is not active: {metadata.get('status')}")
    metadata["command_count"] = int(metadata.get("command_count") or 0) + 1
    if metadata.get("mode") == "mock":
        output = _mock_output(cmd)
        _record_output(
            metadata,
            cmd,
            output,
            bytes_written=len(cmd.encode("utf-8")) + 1,
            max_bytes=max_bytes,
        )
        crash = parse_crash(output)
        if crash.get("crashed"):
            metadata["status"] = "crashed"
            metadata["crash_info"] = crash
            save_gdb_session(metadata)
        return {
            "gdb_session_id": gdb_session_id,
            "cmd": cmd,
            "output": bounded_text(output, max_bytes=max_bytes),
            "status": metadata.get("status"),
            "timed_out": False,
        }

    backend_session_id = str(metadata.get("backend_session_id") or "")
    if not backend_session_id:
        raise GdbSessionError("GDB backend session id missing")
    write = write_session(backend_session_id, cmd, newline=True)
    result = expect_session(backend_session_id, [PROMPT], timeout_ms=timeout_ms, max_bytes=max_bytes)
    output = str(result.get("output") or "")
    _record_output(
        metadata,
        cmd,
        output,
        bytes_read=int(result.get("bytes_read") or 0),
        bytes_written=int(write.get("bytes_written") or 0),
        max_bytes=max_bytes,
    )
    crash = parse_crash(output)
    if crash.get("crashed"):
        metadata["status"] = "crashed"
        metadata["crash_info"] = crash
        save_gdb_session(metadata)
    return {
        "gdb_session_id": gdb_session_id,
        "cmd": cmd,
        "output": bounded_text(output, max_bytes=max_bytes),
        "status": metadata.get("status"),
        "timed_out": bool(result.get("timed_out")),
    }


def continue_gdb(gdb_session_id: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    result = run_gdb_cmd(gdb_session_id, "continue", timeout_ms=timeout_ms, max_bytes=max_bytes)
    result["crash_info"] = parse_crash(str(result.get("output") or ""))
    return result


def wait_crash(gdb_session_id: str, *, timeout_ms: int = 5000, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    result = run_gdb_cmd(gdb_session_id, "continue", timeout_ms=timeout_ms, max_bytes=max_bytes)
    crash = parse_crash(str(result.get("output") or ""))
    metadata = load_gdb_session(gdb_session_id)
    if crash.get("crashed"):
        metadata["status"] = "crashed"
        metadata["crash_info"] = crash
        save_gdb_session(metadata)
    return {
        **result,
        "crashed": bool(crash.get("crashed")),
        "crash_info": crash,
    }


def registers(gdb_session_id: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    result = run_gdb_cmd(gdb_session_id, "info registers", timeout_ms=timeout_ms, max_bytes=max_bytes)
    parsed = parse_registers(str(result.get("output") or ""))
    metadata = load_gdb_session(gdb_session_id)
    metadata["registers"] = parsed
    save_gdb_session(metadata)
    return {**result, "registers": parsed}


def backtrace(gdb_session_id: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    result = run_gdb_cmd(gdb_session_id, "bt", timeout_ms=timeout_ms, max_bytes=max_bytes)
    return {**result, "backtrace": summarize_backtrace(str(result.get("output") or ""), max_bytes=max_bytes)}


def vmmap(gdb_session_id: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    result = run_gdb_cmd(gdb_session_id, "vmmap", timeout_ms=timeout_ms, max_bytes=max_bytes)
    output = str(result.get("output") or "")
    if "Undefined command" in output or "not defined" in output:
        result = run_gdb_cmd(gdb_session_id, "info proc mappings", timeout_ms=timeout_ms, max_bytes=max_bytes)
        output = str(result.get("output") or "")
    return {**result, "mappings": parse_vmmap(output)}


def telescope(
    gdb_session_id: str,
    *,
    address: str,
    count: int = 8,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, object]:
    count = max(1, min(int(count), 64))
    result = run_gdb_cmd(gdb_session_id, f"telescope {address} {count}", timeout_ms=timeout_ms, max_bytes=max_bytes)
    output = str(result.get("output") or "")
    if "Undefined command" in output or "not defined" in output:
        result = run_gdb_cmd(gdb_session_id, f"x/{count}gx {address}", timeout_ms=timeout_ms, max_bytes=max_bytes)
        output = str(result.get("output") or "")
    return {**result, "telescope": summarize_telescope(output, max_bytes=max_bytes)}


def close_gdb(gdb_session_id: str, *, reason: str = "closed") -> dict[str, object]:
    metadata = load_gdb_session(gdb_session_id)
    if metadata.get("status") == "closed":
        return {"gdb_session_id": gdb_session_id, "status": "closed", "already_closed": True}
    errors: list[str] = []
    if metadata.get("mode") != "mock" and metadata.get("backend_session_id"):
        try:
            close_session(str(metadata["backend_session_id"]), reason=reason)
        except Exception as exc:
            errors.append(str(exc))
    metadata["status"] = "closed"
    metadata["closed_at"] = iso_now()
    metadata["close_reason"] = reason
    save_gdb_session(metadata)
    _append_log(gdb_session_id, f"$ close reason={reason}")
    return {
        "gdb_session_id": gdb_session_id,
        "status": "closed",
        "already_closed": False,
        "errors": errors,
    }


def close_gdb_sessions_for_run(run_id: str) -> dict[str, object]:
    if not run_id:
        raise GdbSessionError("run_id is required")
    active = list_gdb_sessions(run_id=run_id, include_closed=False).get("sessions") or []
    closed = 0
    errors: list[str] = []
    command_count = 0
    crash_count = 0
    for item in active:
        if not isinstance(item, dict):
            continue
        gdb_session_id = str(item.get("gdb_session_id") or "")
        command_count += int(item.get("command_count") or 0)
        if item.get("crash_info"):
            crash_count += 1
        try:
            close_gdb(gdb_session_id, reason="challenge_finalized")
            closed += 1
        except Exception as exc:
            errors.append(f"{gdb_session_id}: {exc}")
    return {
        "gdb_session_count": len(active),
        "closed_gdb_session_count": closed,
        "gdb_command_count": command_count,
        "gdb_crash_count": crash_count,
        "errors": errors,
    }


def gdb_summary_for_run(run_id: str) -> dict[str, object]:
    sessions = list_gdb_sessions(run_id=run_id, include_closed=True).get("sessions") or []
    command_count = sum(int(item.get("command_count") or 0) for item in sessions if isinstance(item, dict))
    crash_count = sum(1 for item in sessions if isinstance(item, dict) and item.get("crash_info"))
    return {
        "gdb_session_count": len(sessions),
        "gdb_crash_count": crash_count,
        "gdb_command_count": command_count,
        "gdb_used": bool(sessions),
        "sessions": sessions,
    }
