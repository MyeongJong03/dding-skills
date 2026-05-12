"""Loopback-only browser action daemon backed by optional Playwright."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from .browser_actions import (
    DEFAULT_BROWSER_TYPE,
    DEFAULT_MAX_EVENTS,
    DEFAULT_TIMEOUT_MS,
    BrowserActionError,
    browser_session_metadata_path,
    browserd_status_path,
    bounded_result,
    ensure_private_dir,
    list_browser_session_metadata,
    make_browser_session_id,
    new_session_metadata,
    public_session_metadata,
    redact_url,
    redacted_cookies,
    redacted_network_event,
    resolve_profile_storage_state,
    validate_local_only_root,
    write_private_json,
)
from .paths import browser_artifact_root, browser_root, display_path, resolve_path
from .schemas import iso_now, read_json, slugify


class ManagedBrowserSession:
    def __init__(
        self,
        *,
        metadata: dict[str, object],
        playwright: Any,
        browser: Any,
        context: Any,
        page: Any,
    ) -> None:
        self.metadata = metadata
        self.playwright = playwright
        self.browser = browser
        self.context = context
        self.page = page
        self.lock = threading.RLock()
        self.console_events: list[dict[str, object]] = []
        self.network_events: list[dict[str, object]] = []
        self._attach_handlers()

    @property
    def browser_session_id(self) -> str:
        return str(self.metadata["browser_session_id"])

    def _persist(self) -> None:
        write_private_json(browser_session_metadata_path(self.browser_session_id), self.metadata)

    def _touch(self) -> None:
        self.metadata["updated_at"] = iso_now()

    def _record_action(self) -> None:
        self.metadata["actions_count"] = int(self.metadata.get("actions_count") or 0) + 1
        self.metadata["pages_count"] = len(self.context.pages)
        self.metadata["current_url"] = redact_url(str(self.page.url or ""))
        self._touch()
        self._persist()

    def _append_console(self, item: dict[str, object]) -> None:
        with self.lock:
            self.console_events.append(item)
            self.console_events = self.console_events[-DEFAULT_MAX_EVENTS:]
            self.metadata["console_event_count"] = int(self.metadata.get("console_event_count") or 0) + 1
            self._touch()
            self._persist()

    def _append_network(self, item: dict[str, object]) -> None:
        with self.lock:
            self.network_events.append(redacted_network_event(item))
            self.network_events = self.network_events[-DEFAULT_MAX_EVENTS:]
            self.metadata["network_event_count"] = int(self.metadata.get("network_event_count") or 0) + 1
            self._touch()
            self._persist()

    def _attach_handlers(self) -> None:
        self.page.on(
            "console",
            lambda msg: self._append_console(
                {
                    "type": str(getattr(msg, "type", "") or ""),
                    "text": bounded_result(str(getattr(msg, "text", "") or ""), max_bytes=1000),
                    "timestamp": iso_now(),
                }
            ),
        )
        self.page.on(
            "request",
            lambda request: self._append_network(
                {
                    "type": "request",
                    "method": str(getattr(request, "method", "") or ""),
                    "url": str(getattr(request, "url", "") or ""),
                    "headers": dict(getattr(request, "headers", {}) or {}),
                    "timestamp": iso_now(),
                }
            ),
        )
        self.page.on(
            "response",
            lambda response: self._append_network(
                {
                    "type": "response",
                    "method": str(getattr(getattr(response, "request", None), "method", "") or ""),
                    "url": str(getattr(response, "url", "") or ""),
                    "status": getattr(response, "status", None),
                    "headers": dict(getattr(response, "headers", {}) or {}),
                    "timestamp": iso_now(),
                }
            ),
        )
        self.page.on(
            "requestfailed",
            lambda request: self._append_network(
                {
                    "type": "requestfailed",
                    "method": str(getattr(request, "method", "") or ""),
                    "url": str(getattr(request, "url", "") or ""),
                    "headers": dict(getattr(request, "headers", {}) or {}),
                    "error": str(getattr(request, "failure", "") or ""),
                    "timestamp": iso_now(),
                }
            ),
        )

    def goto(self, payload: dict[str, Any]) -> dict[str, object]:
        url = str(payload.get("url") or "")
        if not url:
            raise BrowserActionError("url is required")
        timeout_ms = int(payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
        wait_until = str(payload.get("wait_until") or "load")
        with self.lock:
            response = self.page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            self._record_action()
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "current_url": redact_url(str(self.page.url or "")),
                "status": getattr(response, "status", None) if response else None,
            }

    def click(self, payload: dict[str, Any]) -> dict[str, object]:
        selector = str(payload.get("selector") or "")
        if not selector:
            raise BrowserActionError("selector is required")
        timeout_ms = int(payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
        with self.lock:
            self.page.click(selector, timeout=timeout_ms)
            self._record_action()
            return {"browser_session_id": self.browser_session_id, "ok": True, "selector": selector}

    def fill(self, payload: dict[str, Any]) -> dict[str, object]:
        selector = str(payload.get("selector") or "")
        value = str(payload.get("value") or "")
        if not selector:
            raise BrowserActionError("selector is required")
        timeout_ms = int(payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
        with self.lock:
            self.page.fill(selector, value, timeout=timeout_ms)
            self._record_action()
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "selector": selector,
                "value_redacted": True,
            }

    def upload(self, payload: dict[str, Any]) -> dict[str, object]:
        selector = str(payload.get("selector") or "")
        files = payload.get("files")
        if not selector:
            raise BrowserActionError("selector is required")
        if isinstance(files, str):
            file_values = [files]
        elif isinstance(files, list):
            file_values = [str(item) for item in files]
        else:
            raise BrowserActionError("files is required")
        resolved = [resolve_path(value) for value in file_values]
        for path in resolved:
            if not path.is_file():
                raise BrowserActionError("upload_file_not_found")
        timeout_ms = int(payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
        with self.lock:
            self.page.set_input_files(selector, [str(path) for path in resolved], timeout=timeout_ms)
            self._record_action()
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "selector": selector,
                "file_count": len(resolved),
            }

    def evaluate(self, payload: dict[str, Any]) -> dict[str, object]:
        expression = str(payload.get("expression") or "")
        if not expression:
            raise BrowserActionError("expression is required")
        timeout_ms = int(payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
        max_bytes = int(payload.get("max_bytes") or 4000)
        with self.lock:
            self.page.set_default_timeout(timeout_ms)
            result = self.page.evaluate(expression)
            self._record_action()
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "result": bounded_result(result, max_bytes=max_bytes),
                "truncated": len(bounded_result(result, max_bytes=max_bytes).encode("utf-8")) >= max_bytes,
            }

    def screenshot(self, payload: dict[str, Any]) -> dict[str, object]:
        raw_name = str(payload.get("name") or "")
        name = slugify(raw_name, fallback="screenshot", max_length=80) if raw_name else f"{iso_now()}-{secrets.token_hex(4)}"
        path = Path(str(self.metadata["artifact_dir"])) / f"{name}.png"
        validate_local_only_root(path.parent, label="browser_artifact_root")
        with self.lock:
            ensure_private_dir(path.parent)
            self.page.screenshot(path=str(path), full_page=bool(payload.get("full_page", False)))
            self.metadata["screenshot_count"] = int(self.metadata.get("screenshot_count") or 0) + 1
            self._record_action()
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "screenshot_path": display_path(path),
                "screenshot_count": int(self.metadata.get("screenshot_count") or 0),
            }

    def console(self, payload: dict[str, Any]) -> dict[str, object]:
        limit = max(0, min(int(payload.get("limit") or 50), DEFAULT_MAX_EVENTS))
        with self.lock:
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "events": self.console_events[-limit:],
                "count": len(self.console_events[-limit:]),
            }

    def network(self, payload: dict[str, Any]) -> dict[str, object]:
        limit = max(0, min(int(payload.get("limit") or 50), DEFAULT_MAX_EVENTS))
        with self.lock:
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "events": self.network_events[-limit:],
                "count": len(self.network_events[-limit:]),
            }

    def cookies(self) -> dict[str, object]:
        with self.lock:
            cookies = redacted_cookies(self.context.cookies())
            self._record_action()
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "cookies": cookies,
                "count": len(cookies),
                "values_redacted": True,
            }

    def close(self, reason: str = "closed") -> dict[str, object]:
        with self.lock:
            if self.metadata.get("status") in {"closed", "failed"}:
                return {
                    "browser_session_id": self.browser_session_id,
                    "ok": True,
                    "status": self.metadata.get("status"),
                    "already_closed": True,
                }
            try:
                self.context.close()
            finally:
                try:
                    self.browser.close()
                finally:
                    self.playwright.stop()
            self.metadata["status"] = "closed"
            self.metadata["closed_at"] = iso_now()
            self.metadata["close_reason"] = reason
            self._touch()
            self._persist()
            return {
                "browser_session_id": self.browser_session_id,
                "ok": True,
                "status": "closed",
                "already_closed": False,
            }


class BrowserManager:
    def __init__(self) -> None:
        ensure_private_dir(browser_root())
        ensure_private_dir(browser_artifact_root())
        self.sessions: dict[str, ManagedBrowserSession] = {}
        self.lock = threading.RLock()

    def start(self, payload: dict[str, Any]) -> dict[str, object]:
        try:
            validate_local_only_root(browser_root(), label="browser_root")
            validate_local_only_root(browser_artifact_root(), label="browser_artifact_root")
            from playwright.sync_api import Error as PlaywrightError  # type: ignore
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            return {
                "ok": False,
                "reason": "playwright_not_installed",
                "install": (
                    "uv run --with playwright python -m playwright install chromium; "
                    "run browser tools through uv --with playwright or a repo-external venv"
                ),
            }
        except BrowserActionError as exc:
            return {"ok": False, "reason": str(exc)}

        browser_type = str(payload.get("browser_type") or DEFAULT_BROWSER_TYPE)
        headless = bool(payload.get("headless", True))
        try:
            storage_path, profile_info = resolve_profile_storage_state(
                profile_name=payload.get("profile"),
                platform=payload.get("platform"),
                event=payload.get("event"),
                explicit_storage_state=payload.get("storage_state"),
            )
        except BrowserActionError as exc:
            return {"ok": False, "reason": str(exc)}

        browser_session_id = make_browser_session_id()
        metadata = new_session_metadata(
            browser_session_id=browser_session_id,
            run_id=payload.get("run_id"),
            challenge_id=payload.get("challenge_id"),
            worker_id=payload.get("worker_id"),
            browser_type=browser_type,
            headless=headless,
            profile_info=profile_info,
        )
        write_private_json(browser_session_metadata_path(browser_session_id), metadata)

        playwright = None
        try:
            playwright = sync_playwright().start()
            browser_launcher = getattr(playwright, browser_type, None)
            if browser_launcher is None:
                raise BrowserActionError(f"unsupported_browser_type:{browser_type}")
            browser = browser_launcher.launch(headless=headless)
            context_kwargs: dict[str, object] = {}
            if storage_path:
                context_kwargs["storage_state"] = str(storage_path)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            metadata["status"] = "running"
            metadata["pages_count"] = len(context.pages)
            metadata["updated_at"] = iso_now()
            write_private_json(browser_session_metadata_path(browser_session_id), metadata)
            session = ManagedBrowserSession(
                metadata=metadata,
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
            )
            with self.lock:
                self.sessions[browser_session_id] = session
            return {"ok": True, "session": public_session_metadata(metadata)}
        except BrowserActionError as exc:
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    pass
            metadata["status"] = "failed"
            metadata["closed_at"] = iso_now()
            metadata["last_error"] = str(exc)
            metadata["close_reason"] = str(exc)
            write_private_json(browser_session_metadata_path(browser_session_id), metadata)
            return {"ok": False, "reason": str(exc), "session": public_session_metadata(metadata)}
        except PlaywrightError as exc:
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    pass
            reason = "playwright_browser_unavailable"
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                reason = "playwright_browser_not_installed"
            metadata["status"] = "failed"
            metadata["closed_at"] = iso_now()
            metadata["last_error"] = reason
            metadata["close_reason"] = reason
            write_private_json(browser_session_metadata_path(browser_session_id), metadata)
            return {
                "ok": False,
                "reason": reason,
                "install": "uv run --with playwright python -m playwright install chromium",
                "session": public_session_metadata(metadata),
            }
        except Exception as exc:
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    pass
            metadata["status"] = "failed"
            metadata["closed_at"] = iso_now()
            metadata["last_error"] = str(exc)
            metadata["close_reason"] = "browser_start_failed"
            write_private_json(browser_session_metadata_path(browser_session_id), metadata)
            return {"ok": False, "reason": "browser_start_failed", "error": str(exc), "session": public_session_metadata(metadata)}

    def _get(self, browser_session_id: str) -> ManagedBrowserSession:
        with self.lock:
            session = self.sessions.get(browser_session_id)
        if not session:
            raise BrowserActionError(f"unknown or inactive browser session: {browser_session_id}")
        if session.metadata.get("status") != "running":
            raise BrowserActionError(f"browser session is not running: {session.metadata.get('status')}")
        return session

    def goto(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).goto(payload)

    def click(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).click(payload)

    def fill(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).fill(payload)

    def upload(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).upload(payload)

    def evaluate(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).evaluate(payload)

    def screenshot(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).screenshot(payload)

    def console(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).console(payload)

    def network(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).network(payload)

    def cookies(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("browser_session_id") or "")).cookies()

    def close(self, payload: dict[str, Any]) -> dict[str, object]:
        browser_session_id = str(payload.get("browser_session_id") or "")
        result = self._get(browser_session_id).close(str(payload.get("reason") or "closed"))
        with self.lock:
            self.sessions.pop(browser_session_id, None)
        return result

    def list_sessions(self, payload: dict[str, Any]) -> dict[str, object]:
        run_id = str(payload.get("run_id") or "")
        challenge_id = str(payload.get("challenge_id") or "")
        include_closed = bool(payload.get("include_closed", False))
        records: dict[str, dict[str, object]] = {}
        for item in list_browser_session_metadata(
            run_id=run_id or None,
            challenge_id=challenge_id or None,
            include_closed=True,
        ):
            records[str(item.get("browser_session_id") or "")] = item
        with self.lock:
            live_ids = set(self.sessions.keys())
            for session_id, session in self.sessions.items():
                records[session_id] = public_session_metadata(session.metadata)
        for session_id, record in list(records.items()):
            if session_id and session_id not in live_ids and record.get("status") in {"starting", "running"}:
                path = browser_session_metadata_path(session_id)
                raw = read_json(path, default={})
                if isinstance(raw, dict):
                    raw["status"] = "failed"
                    raw["closed_at"] = raw.get("closed_at") or iso_now()
                    raw["close_reason"] = raw.get("close_reason") or "browser_daemon_restarted"
                    raw["last_error"] = raw.get("last_error") or "browser_daemon_restarted"
                    raw["updated_at"] = iso_now()
                    write_private_json(path, raw)
                    records[session_id] = public_session_metadata(raw)
        filtered = []
        for record in records.values():
            if run_id and record.get("run_id") != run_id:
                continue
            if challenge_id and record.get("challenge_id") != challenge_id:
                continue
            if not include_closed and record.get("status") not in {"starting", "running"}:
                continue
            filtered.append(record)
        filtered.sort(key=lambda item: str(item.get("created_at") or ""))
        return {"sessions": filtered, "count": len(filtered)}

    def close_all(self, reason: str = "browser_daemon_stop") -> None:
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions = {}
        for session in sessions:
            try:
                session.close(reason)
            except Exception:
                pass


class BrowserHTTPServer(HTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], token: str) -> None:
        super().__init__(server_address, handler_cls)
        self.manager = BrowserManager()
        self.token = token


class Handler(BaseHTTPRequestHandler):
    server: BrowserHTTPServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _send(self, status: int, payload: dict[str, object]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise BrowserActionError("request payload must be a JSON object")
        return data

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.token}"
        return self.headers.get("Authorization") == expected

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/ping":
            self._send(404, {"ok": False, "error": "not_found"})
            return
        if not self._authorized():
            self._send(403, {"ok": False, "error": "forbidden"})
            return
        self._send(200, {"ok": True, "pid": os.getpid()})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._send(403, {"ok": False, "error": "forbidden"})
            return
        try:
            payload = self._read_payload()
            result = self._dispatch(payload)
            self._send(200, {"ok": True, **result})
        except Exception as exc:
            self._send(400, {"ok": False, "error": str(exc)})

    def _dispatch(self, payload: dict[str, Any]) -> dict[str, object]:
        manager = self.server.manager
        path = self.path.rstrip("/")
        if path == "/start":
            return manager.start(payload)
        if path == "/goto":
            return manager.goto(payload)
        if path == "/click":
            return manager.click(payload)
        if path == "/fill":
            return manager.fill(payload)
        if path == "/upload":
            return manager.upload(payload)
        if path == "/eval":
            return manager.evaluate(payload)
        if path == "/screenshot":
            return manager.screenshot(payload)
        if path == "/console":
            return manager.console(payload)
        if path == "/network":
            return manager.network(payload)
        if path == "/cookies":
            return manager.cookies(payload)
        if path == "/close":
            return manager.close(payload)
        if path == "/list":
            return manager.list_sessions(payload)
        if path == "/stop":
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"stopping": True}
        raise BrowserActionError(f"unknown endpoint: {self.path}")


def _host_from_env() -> str:
    host = os.environ.get("CTF_BROWSERD_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host != "127.0.0.1":
        raise BrowserActionError("CTF_BROWSERD_HOST must be 127.0.0.1")
    return host


def _port_from_env() -> int:
    raw = os.environ.get("CTF_BROWSERD_PORT", "0").strip() or "0"
    try:
        port = int(raw)
    except ValueError as exc:
        raise BrowserActionError("CTF_BROWSERD_PORT must be an integer") from exc
    if port < 0 or port > 65535:
        raise BrowserActionError("CTF_BROWSERD_PORT must be between 0 and 65535")
    return port


def serve_forever() -> int:
    ensure_private_dir(browser_root())
    token = secrets.token_urlsafe(32)
    server = BrowserHTTPServer((_host_from_env(), _port_from_env()), Handler, token)
    host, port = server.server_address[:2]
    write_private_json(
        browserd_status_path(),
        {
            "schema_version": 1,
            "host": host,
            "port": port,
            "token": token,
            "pid": os.getpid(),
            "created_at": iso_now(),
        },
    )
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.manager.close_all("browser_daemon_stop")
        try:
            status = Path(browserd_status_path())
            current = read_json(status, default={})
            if isinstance(current, dict) and int(current.get("pid") or -1) == os.getpid():
                status.unlink(missing_ok=True)
        except Exception:
            pass
        server.server_close()
    return 0
