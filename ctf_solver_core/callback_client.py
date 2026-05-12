"""Client helpers for the local web callback daemon."""

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

from .callbacks import (
    CONTROL_PREFIX,
    CallbackError,
    build_callback_url,
    callback_summary_for_run,
    callbackd_status_path,
    ensure_private_dir,
    generate_payload_snippets,
    list_listener_metadata,
    load_listener_metadata,
    mark_orphaned_listeners_for_run,
    normalize_bind_host,
    normalize_port,
    read_hits,
    save_listener_metadata,
    validate_callback_roots,
)
from .paths import callbackd_root
from .schemas import iso_now, read_json


class CallbackClientError(RuntimeError):
    """Raised when the local callback daemon cannot be reached."""


def _code_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_status() -> dict[str, object] | None:
    data = read_json(callbackd_status_path(), default={})
    return data if isinstance(data, dict) and data.get("host") and data.get("port") and data.get("token") else None


def _url(status: dict[str, object], endpoint: str) -> str:
    return f"http://{status['host']}:{status['port']}{CONTROL_PREFIX}{endpoint}"


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
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            raise CallbackClientError(str(exc)) from exc
        raise CallbackClientError(str(parsed.get("error") or exc)) from exc
    except Exception as exc:
        raise CallbackClientError(str(exc)) from exc
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise CallbackClientError("invalid daemon response")
    if not parsed.get("ok") and parsed.get("error"):
        raise CallbackClientError(str(parsed.get("error") or "daemon request failed"))
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


def _start_daemon(*, host: str, port: int, allow_public_bind: bool) -> None:
    validate_callback_roots()
    ensure_private_dir(callbackd_root())
    status_path = Path(callbackd_status_path())
    try:
        status_path.unlink(missing_ok=True)
    except OSError:
        pass
    script = _code_root() / "scripts" / "callback_daemon.py"
    if not script.is_file():
        raise CallbackClientError(f"callback daemon script missing: {script}")
    env = os.environ.copy()
    env["CTF_CALLBACKD_HOST"] = host
    env["CTF_CALLBACKD_PORT"] = str(port)
    if allow_public_bind:
        env["CTF_CALLBACKD_ALLOW_PUBLIC_BIND"] = "1"
    kwargs: dict[str, object] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "cwd": str(_code_root()),
        "env": env,
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    else:  # pragma: no cover - Windows fallback
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([sys.executable, str(script), "serve"], **kwargs)


def ensure_daemon(
    *,
    host: str | None = None,
    port: int | str | None = None,
    allow_public_bind: bool = False,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    host_requested = host is not None
    requested_host = normalize_bind_host(host if host_requested else "127.0.0.1", allow_public_bind=allow_public_bind)
    requested_port = normalize_port(port)
    status = _load_status()
    if status and ping(status):
        running_host = str(status.get("host") or "")
        running_port = int(status.get("port") or 0)
        if host_requested and running_host != requested_host:
            raise CallbackClientError(f"callback daemon already running on {running_host}:{running_port}")
        if requested_port and running_port != requested_port:
            raise CallbackClientError(f"callback daemon already running on port {running_port}")
        return status

    _start_daemon(host=requested_host, port=requested_port, allow_public_bind=allow_public_bind)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = _load_status()
        if status and ping(status):
            return status
        time.sleep(0.05)
    raise CallbackClientError("callback daemon did not start")


def request(endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
    status = ensure_daemon()
    try:
        return _request(status, endpoint, payload)
    except CallbackClientError:
        status = ensure_daemon()
        return _request(status, endpoint, payload)


def callback_start(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    worker_id: str | None = None,
    host: str = "127.0.0.1",
    port: int | str | None = None,
    external_base_url: str | None = None,
    token_path: str | None = None,
    allow_public_bind: bool = False,
) -> dict[str, object]:
    status = ensure_daemon(host=host, port=port, allow_public_bind=allow_public_bind)
    return _request(
        status,
        "/start",
        {
            "run_id": run_id or "",
            "challenge_id": challenge_id or "",
            "worker_id": worker_id or "",
            "external_base_url": external_base_url or "",
            "token_path": token_path or "",
        },
    )


def callback_url(
    listener_id: str,
    *,
    external: bool = False,
    path: str | None = None,
) -> dict[str, object]:
    status = _load_status()
    if status and ping(status):
        return _request(status, "/url", {"listener_id": listener_id, "external": external, "path": path or ""})
    metadata = load_listener_metadata(listener_id)
    if not metadata:
        raise CallbackClientError(f"unknown listener_id: {listener_id}")
    return {
        "listener_id": listener_id,
        "url": build_callback_url(metadata, external=external, path=path),
        "external": external,
        "daemon_running": False,
    }


def callback_hits(
    listener_id: str,
    *,
    since_hit_id: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    status = _load_status()
    if status and ping(status):
        return _request(status, "/hits", {"listener_id": listener_id, "since_hit_id": since_hit_id or "", "limit": limit})
    hits = read_hits(listener_id, since_hit_id=since_hit_id, limit=limit)
    return {"listener_id": listener_id, "hits": hits, "count": len(hits), "daemon_running": False}


def callback_wait(
    listener_id: str,
    *,
    timeout_sec: float = 30,
    pattern: str | None = None,
    min_hits: int = 1,
) -> dict[str, object]:
    status = ensure_daemon()
    return _request(
        status,
        "/wait",
        {
            "listener_id": listener_id,
            "timeout_sec": timeout_sec,
            "pattern": pattern or "",
            "min_hits": min_hits,
        },
    )


def callback_close(listener_id: str, *, reason: str = "closed") -> dict[str, object]:
    status = _load_status()
    if status and ping(status):
        return _request(status, "/close", {"listener_id": listener_id, "reason": reason})
    metadata = load_listener_metadata(listener_id)
    if not metadata:
        raise CallbackClientError(f"unknown listener_id: {listener_id}")
    already_closed = metadata.get("status") in {"closed", "failed"}
    if not already_closed:
        metadata["status"] = "closed"
        metadata["closed_at"] = metadata.get("closed_at") or iso_now()
        metadata["close_reason"] = reason
        metadata["updated_at"] = metadata["closed_at"]
        save_listener_metadata(metadata)
    return {
        "listener_id": listener_id,
        "status": metadata.get("status"),
        "already_closed": already_closed,
        "hit_count": int(metadata.get("hit_count") or 0),
        "bytes_received": int(metadata.get("bytes_received") or 0),
        "daemon_running": False,
    }


def callback_list(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    include_closed: bool = False,
) -> dict[str, object]:
    status = _load_status()
    if status and ping(status):
        result = _request(
            status,
            "/list",
            {
                "run_id": run_id or "",
                "challenge_id": challenge_id or "",
                "include_closed": include_closed,
            },
        )
        result["daemon_running"] = True
        return result
    listeners = list_listener_metadata(run_id=run_id, challenge_id=challenge_id, include_closed=include_closed)
    return {"listeners": listeners, "count": len(listeners), "daemon_running": False}


def web_payload_helper(callback_url_value: str) -> dict[str, object]:
    return generate_payload_snippets(callback_url_value)


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
    public: dict[str, object] = {
        "running": running,
        "status_path": str(callbackd_status_path()),
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


def close_callback_listeners_for_run(run_id: str) -> dict[str, object]:
    if not run_id:
        raise CallbackError("run_id is required")
    status_data = _load_status()
    if not status_data or not ping(status_data):
        return {
            "ok": True,
            "reason": "daemon_not_running",
            **mark_orphaned_listeners_for_run(run_id, reason="callback_daemon_not_running"),
        }
    listeners = _request(
        status_data,
        "/list",
        {"run_id": run_id, "challenge_id": "", "include_closed": False},
    ).get("listeners") or []
    closed = 0
    errors: list[str] = []
    hit_count = 0
    bytes_received = 0
    for item in listeners:
        if not isinstance(item, dict):
            continue
        listener_id = str(item.get("listener_id") or "")
        hit_count += int(item.get("hit_count") or 0)
        bytes_received += int(item.get("bytes_received") or 0)
        try:
            _request(status_data, "/close", {"listener_id": listener_id, "reason": "challenge_finalized"})
            closed += 1
        except Exception as exc:
            errors.append(f"{listener_id}: {exc}")
    return {
        "ok": True,
        "listener_count": len(listeners),
        "closed_callback_listener_count": closed,
        "callback_hit_count": hit_count,
        "callback_bytes_received": bytes_received,
        "errors": errors,
    }


def callback_summary(run_id: str) -> dict[str, object]:
    return callback_summary_for_run(run_id)
