"""Client for the local persistent session daemon."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from ctf_solver_core.schemas import read_json
from ctf_solver_core.sessions import SessionError, daemon_status_path, ensure_private_dir
from ctf_solver_core.paths import sessiond_root


class SessionClientError(RuntimeError):
    """Raised when the local session daemon cannot be reached."""


def _code_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_status() -> dict[str, object] | None:
    data = read_json(daemon_status_path(), default={})
    return data if isinstance(data, dict) and data.get("host") and data.get("port") and data.get("token") else None


def _url(status: dict[str, object], endpoint: str) -> str:
    return f"http://{status['host']}:{status['port']}{endpoint}"


def _request(status: dict[str, object], endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
    token = str(status.get("token") or "")
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(_url(status, endpoint), data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            raise SessionClientError(str(exc)) from exc
        raise SessionClientError(str(parsed.get("error") or exc)) from exc
    except Exception as exc:
        raise SessionClientError(str(exc)) from exc
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise SessionClientError("invalid daemon response")
    if not parsed.get("ok"):
        raise SessionClientError(str(parsed.get("error") or "daemon request failed"))
    parsed.pop("ok", None)
    return parsed


def ping(status: dict[str, object] | None = None) -> bool:
    status = status or _load_status()
    if not status:
        return False
    try:
        _request(status, "/ping")
        return True
    except Exception:
        return False


def _start_daemon() -> None:
    ensure_private_dir(sessiond_root())
    status = Path(daemon_status_path())
    try:
        status.unlink(missing_ok=True)
    except OSError:
        pass
    script = _code_root() / "scripts" / "session_daemon.py"
    if not script.is_file():
        raise SessionClientError(f"session daemon script missing: {script}")
    kwargs: dict[str, object] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "cwd": str(_code_root()),
        "env": os.environ.copy(),
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    else:  # pragma: no cover - Windows fallback
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([sys.executable, str(script), "serve"], **kwargs)


def ensure_daemon(timeout_seconds: float = 5.0) -> dict[str, object]:
    status = _load_status()
    if status and ping(status):
        return status

    _start_daemon()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = _load_status()
        if status and ping(status):
            return status
        time.sleep(0.05)
    raise SessionClientError("session daemon did not start")


def request(endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
    status = ensure_daemon()
    try:
        return _request(status, endpoint, payload)
    except SessionClientError:
        status = ensure_daemon()
        return _request(status, endpoint, payload)


def start_session(**kwargs: Any) -> dict[str, object]:
    if not kwargs.get("cwd"):
        kwargs["cwd"] = str(Path.cwd())
    return request("/start", {key: value for key, value in kwargs.items() if value is not None})


def write_session(
    session_id: str,
    data: str,
    *,
    newline: bool = True,
    encoding: str = "text",
) -> dict[str, object]:
    return request(
        "/write",
        {
            "session_id": session_id,
            "data": data,
            "newline": newline,
            "encoding": encoding,
        },
    )


def read_session(session_id: str, *, timeout_ms: int = 1000, max_bytes: int = 8000) -> dict[str, object]:
    return request(
        "/read",
        {
            "session_id": session_id,
            "timeout_ms": timeout_ms,
            "max_bytes": max_bytes,
        },
    )


def expect_session(
    session_id: str,
    patterns: list[str],
    *,
    timeout_ms: int = 1000,
    max_bytes: int = 8000,
) -> dict[str, object]:
    return request(
        "/expect",
        {
            "session_id": session_id,
            "patterns": patterns,
            "timeout_ms": timeout_ms,
            "max_bytes": max_bytes,
        },
    )


def close_session(session_id: str, *, reason: str = "closed") -> dict[str, object]:
    return request("/close", {"session_id": session_id, "reason": reason})


def list_sessions(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    include_closed: bool = False,
) -> dict[str, object]:
    return request(
        "/list",
        {
            "run_id": run_id or "",
            "challenge_id": challenge_id or "",
            "include_closed": include_closed,
        },
    )


def stop_daemon() -> dict[str, object]:
    status = _load_status()
    if not status:
        return {"running": False}
    try:
        result = _request(status, "/stop", {})
    except Exception as exc:
        return {"running": False, "warning": str(exc)}
    return {"running": True, **result}


def status() -> dict[str, object]:
    status_data = _load_status()
    running = ping(status_data)
    public = {
        "running": running,
        "status_path": str(daemon_status_path()),
    }
    if status_data:
        public.update(
            {
                "host": status_data.get("host"),
                "port": status_data.get("port"),
                "pid": status_data.get("pid"),
                "created_at": status_data.get("created_at"),
            }
        )
    return public


def close_sessions_for_run(run_id: str) -> dict[str, object]:
    if not run_id:
        raise SessionError("run_id is required")
    status_data = _load_status()
    if not status_data or not ping(status_data):
        return {
            "reason": "daemon_not_running",
            "session_count": 0,
            "closed_session_count": 0,
            "session_bytes_read": 0,
            "session_bytes_written": 0,
            "errors": [],
        }
    sessions = _request(
        status_data,
        "/list",
        {"run_id": run_id, "challenge_id": "", "include_closed": False},
    ).get("sessions") or []
    closed = 0
    errors: list[str] = []
    bytes_read = 0
    bytes_written = 0
    for item in sessions:
        if not isinstance(item, dict):
            continue
        session_id = str(item.get("session_id") or "")
        bytes_read += int(item.get("bytes_read") or 0)
        bytes_written += int(item.get("bytes_written") or 0)
        try:
            _request(status_data, "/close", {"session_id": session_id, "reason": "challenge_finalized"})
            closed += 1
        except Exception as exc:
            errors.append(f"{session_id}: {exc}")
    return {
        "session_count": len(sessions),
        "closed_session_count": closed,
        "session_bytes_read": bytes_read,
        "session_bytes_written": bytes_written,
        "errors": errors,
    }
