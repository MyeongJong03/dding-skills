"""Persistent session metadata, command construction, and redaction helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import uuid

from ctf_solver_core.paths import session_root, sessiond_root
from ctf_solver_core.schemas import atomic_write_json, iso_now, utc_now


SESSION_KINDS = ("shell", "python", "sage", "nc", "docker-shell")
SESSION_STATUSES = ("starting", "running", "closed", "failed")
DEFAULT_IMAGE = "ctf-pwn:latest"
DEFAULT_MAX_BYTES = 8000
DEFAULT_TIMEOUT_MS = 1000
ENV_ALLOWLIST = ("PATH", "TERM", "LANG", "LC_ALL", "SAGE_PATH")

SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|cookie|authorization|api[_-]?key|oauth|private[_-]?key|session)",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
RUNTIME_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9_]{10,}|"
    r"xoxb-[A-Za-z0-9-]{10,})",
    re.IGNORECASE,
)
HEADER_SECRET_RE = re.compile(
    r"(?im)^(\s*(?:Authorization\s*:\s*Bearer|Cookie\s*:)\s+).+$"
)
ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b((?:token|secret|password|passwd|api_key|session)\s*=\s*)[^&\s;,]+"
)
REDACTED = "<REDACTED>"


class SessionError(RuntimeError):
    """Raised when a persistent session operation cannot be completed."""


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path
    env: dict[str, str]
    metadata_env: dict[str, str]
    display_command: str


def make_session_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def session_metadata_path(session_id: str) -> Path:
    return session_root() / session_id / "session.json"


def daemon_status_path() -> Path:
    return sessiond_root() / "sessiond.json"


def write_private_json(path: Path, data: object) -> None:
    ensure_private_dir(path.parent)
    atomic_write_json(path, data)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def redact_text(text: str) -> str:
    out = PRIVATE_KEY_RE.sub("<REDACTED_PRIVATE_KEY_BLOCK>", str(text))
    out = HEADER_SECRET_RE.sub(r"\1" + REDACTED, out)
    out = ASSIGNMENT_SECRET_RE.sub(r"\1" + REDACTED, out)
    out = RUNTIME_SECRET_RE.sub(REDACTED, out)
    return out


def redact_value(key: str, value: str) -> str:
    if SENSITIVE_KEY_RE.search(key):
        return REDACTED
    return redact_text(value)


def bounded_text(data: bytes | str, *, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    if isinstance(data, str):
        raw = data.encode("utf-8", errors="replace")
    else:
        raw = data
    if max_bytes < 0:
        max_bytes = DEFAULT_MAX_BYTES
    if max_bytes == 0:
        return ""
    clipped = raw[-max_bytes:] if len(raw) > max_bytes else raw
    return redact_text(clipped.decode("utf-8", errors="replace"))


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise SessionError(f"invalid command: {exc}") from exc


def _default_shell() -> list[str]:
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell:
            return [powershell, "-NoLogo"]
        return ["cmd.exe"]
    bash = shutil.which("bash")
    if bash:
        return [bash]
    sh = shutil.which("sh")
    if sh:
        return [sh]
    raise SessionError("no POSIX shell found")


def _python_command() -> list[str]:
    python = shutil.which("python3") or shutil.which("python") or sys.executable
    return [python, "-i"]


def _sage_command() -> list[str]:
    sage = os.environ.get("SAGE_PATH") or shutil.which("sage")
    if not sage:
        raise SessionError("Sage executable not found; set SAGE_PATH or install sage")
    return [sage]


def _nc_command(host: str | None, port: int | str | None) -> list[str]:
    if not host or port is None:
        raise SessionError("nc sessions require host and port")
    nc = shutil.which("nc") or shutil.which("ncat")
    if not nc:
        raise SessionError("nc executable not found")
    return [nc, str(host), str(port)]


def _docker_command(
    *,
    command: str | None,
    image: str | None,
    workspace: str | None,
    cwd: Path,
) -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        raise SessionError("Docker CLI not found")
    workspace_path = Path(workspace).expanduser().resolve() if workspace else cwd
    shell_command = _split_command(command) if command else ["bash"]
    return [
        docker,
        "run",
        "--rm",
        "-i",
        "--platform",
        "linux/amd64",
        "-v",
        f"{workspace_path}:/workspace",
        "-w",
        "/workspace",
        image or DEFAULT_IMAGE,
        *shell_command,
    ]


def build_env(explicit_env: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, str]]:
    env: dict[str, str] = {}
    for key in ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value:
            env[key] = value
    if os.name != "nt":
        env.setdefault("TERM", "xterm-256color")
    for key, value in (explicit_env or {}).items():
        env[str(key)] = str(value)
    metadata_env = {key: redact_value(key, value) for key, value in sorted(env.items())}
    return env, metadata_env


def build_command_spec(
    *,
    kind: str,
    command: str | None = None,
    cwd: str | None = None,
    host: str | None = None,
    port: int | str | None = None,
    image: str | None = None,
    workspace: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandSpec:
    if kind not in SESSION_KINDS:
        raise SessionError(f"unsupported session kind: {kind}")

    resolved_cwd = Path(cwd).expanduser().resolve() if cwd else Path.home().resolve()
    if kind == "docker-shell":
        workspace_path = Path(workspace).expanduser().resolve() if workspace else resolved_cwd
        workspace_path.mkdir(parents=True, exist_ok=True)
        resolved_cwd = workspace_path
    else:
        resolved_cwd.mkdir(parents=True, exist_ok=True)

    if kind == "shell":
        argv = _split_command(command) if command else _default_shell()
    elif kind == "python":
        argv = _split_command(command) if command else _python_command()
    elif kind == "sage":
        argv = _split_command(command) if command else _sage_command()
    elif kind == "nc":
        argv = _split_command(command) if command else _nc_command(host, port)
    elif kind == "docker-shell":
        argv = _docker_command(command=command, image=image, workspace=workspace, cwd=resolved_cwd)
    else:
        raise SessionError(f"unsupported session kind: {kind}")

    child_env, metadata_env = build_env(env)
    return CommandSpec(
        argv=argv,
        cwd=resolved_cwd,
        env=child_env,
        metadata_env=metadata_env,
        display_command=" ".join(shlex.quote(part) for part in argv),
    )


def initial_metadata(
    *,
    session_id: str,
    kind: str,
    spec: CommandSpec,
    run_id: str | None = None,
    challenge_id: str | None = None,
    worker_id: str | None = None,
) -> dict[str, object]:
    now = iso_now()
    return {
        "schema_version": 1,
        "session_id": session_id,
        "run_id": run_id or "",
        "challenge_id": challenge_id or "",
        "worker_id": worker_id or "",
        "kind": kind,
        "status": "starting",
        "created_at": now,
        "updated_at": now,
        "pid": None,
        "command": redact_text(spec.display_command),
        "cwd": str(spec.cwd),
        "env": spec.metadata_env,
        "last_read_at": None,
        "bytes_read": 0,
        "bytes_written": 0,
        "closed_at": None,
        "close_reason": "",
    }
