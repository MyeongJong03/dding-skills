"""Client helpers for the local browser action daemon."""

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

from .browser_actions import (
    BrowserActionError,
    browserd_status_path,
    ensure_private_dir,
    list_browser_session_metadata,
    mark_orphaned_browser_sessions_for_run,
)
from .paths import browser_root
from .schemas import read_json


class BrowserClientError(RuntimeError):
    """Raised when the local browser daemon cannot be reached."""


def _code_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_status() -> dict[str, object] | None:
    data = read_json(browserd_status_path(), default={})
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
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            raise BrowserClientError(str(exc)) from exc
        raise BrowserClientError(str(parsed.get("error") or exc)) from exc
    except Exception as exc:
        raise BrowserClientError(str(exc)) from exc
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise BrowserClientError("invalid daemon response")
    if not parsed.get("ok") and parsed.get("error"):
        raise BrowserClientError(str(parsed.get("error") or "daemon request failed"))
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
    ensure_private_dir(browser_root())
    status_path = Path(browserd_status_path())
    try:
        status_path.unlink(missing_ok=True)
    except OSError:
        pass
    script = _code_root() / "scripts" / "browser_daemon.py"
    if not script.is_file():
        raise BrowserClientError(f"browser daemon script missing: {script}")
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
    raise BrowserClientError("browser daemon did not start")


def request(endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
    status = ensure_daemon()
    try:
        return _request(status, endpoint, payload)
    except BrowserClientError:
        status = ensure_daemon()
        return _request(status, endpoint, payload)


def browser_start(**kwargs: Any) -> dict[str, object]:
    return request("/start", {key: value for key, value in kwargs.items() if value is not None})


def browser_goto(browser_session_id: str, *, url: str, timeout_ms: int = 10_000, wait_until: str = "load") -> dict[str, object]:
    return request(
        "/goto",
        {
            "browser_session_id": browser_session_id,
            "url": url,
            "timeout_ms": timeout_ms,
            "wait_until": wait_until,
        },
    )


def browser_click(browser_session_id: str, *, selector: str, timeout_ms: int = 10_000) -> dict[str, object]:
    return request("/click", {"browser_session_id": browser_session_id, "selector": selector, "timeout_ms": timeout_ms})


def browser_fill(browser_session_id: str, *, selector: str, value: str, timeout_ms: int = 10_000) -> dict[str, object]:
    return request(
        "/fill",
        {
            "browser_session_id": browser_session_id,
            "selector": selector,
            "value": value,
            "timeout_ms": timeout_ms,
        },
    )


def browser_upload(
    browser_session_id: str,
    *,
    selector: str,
    files: list[str],
    timeout_ms: int = 10_000,
) -> dict[str, object]:
    return request(
        "/upload",
        {
            "browser_session_id": browser_session_id,
            "selector": selector,
            "files": files,
            "timeout_ms": timeout_ms,
        },
    )


def browser_eval(
    browser_session_id: str,
    *,
    expression: str,
    timeout_ms: int = 10_000,
    max_bytes: int = 4000,
) -> dict[str, object]:
    return request(
        "/eval",
        {
            "browser_session_id": browser_session_id,
            "expression": expression,
            "timeout_ms": timeout_ms,
            "max_bytes": max_bytes,
        },
    )


def browser_screenshot(
    browser_session_id: str,
    *,
    name: str | None = None,
    full_page: bool = False,
) -> dict[str, object]:
    return request(
        "/screenshot",
        {
            "browser_session_id": browser_session_id,
            "name": name or "",
            "full_page": full_page,
        },
    )


def browser_console(browser_session_id: str, *, limit: int = 50) -> dict[str, object]:
    return request("/console", {"browser_session_id": browser_session_id, "limit": limit})


def browser_network(browser_session_id: str, *, limit: int = 50) -> dict[str, object]:
    return request("/network", {"browser_session_id": browser_session_id, "limit": limit})


def browser_cookies(browser_session_id: str) -> dict[str, object]:
    return request("/cookies", {"browser_session_id": browser_session_id})


def browser_close(browser_session_id: str, *, reason: str = "closed") -> dict[str, object]:
    return request("/close", {"browser_session_id": browser_session_id, "reason": reason})


def browser_list(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    include_closed: bool = False,
) -> dict[str, object]:
    status = _load_status()
    if not status or not ping(status):
        sessions = list_browser_session_metadata(
            run_id=run_id,
            challenge_id=challenge_id,
            include_closed=include_closed,
        )
        return {"sessions": sessions, "count": len(sessions), "daemon_running": False}
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
        "status_path": str(browserd_status_path()),
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


def close_browser_sessions_for_run(run_id: str) -> dict[str, object]:
    if not run_id:
        raise BrowserActionError("run_id is required")
    status_data = _load_status()
    if not status_data or not ping(status_data):
        orphaned = mark_orphaned_browser_sessions_for_run(run_id, reason="browser_daemon_not_running")
        return {
            "ok": True,
            "reason": "daemon_not_running",
            **orphaned,
        }
    sessions = _request(
        status_data,
        "/list",
        {"run_id": run_id, "challenge_id": "", "include_closed": False},
    ).get("sessions") or []
    closed = 0
    errors: list[str] = []
    actions = 0
    screenshots = 0
    network_events = 0
    for item in sessions:
        if not isinstance(item, dict):
            continue
        browser_session_id = str(item.get("browser_session_id") or "")
        actions += int(item.get("actions_count") or 0)
        screenshots += int(item.get("screenshot_count") or 0)
        network_events += int(item.get("network_event_count") or 0)
        try:
            _request(
                status_data,
                "/close",
                {"browser_session_id": browser_session_id, "reason": "challenge_finalized"},
            )
            closed += 1
        except Exception as exc:
            errors.append(f"{browser_session_id}: {exc}")
    return {
        "ok": True,
        "session_count": len(sessions),
        "closed_browser_session_count": closed,
        "browser_actions_count": actions,
        "browser_screenshot_count": screenshots,
        "browser_network_event_count": network_events,
        "errors": errors,
    }
