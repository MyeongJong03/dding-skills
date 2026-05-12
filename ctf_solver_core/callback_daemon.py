"""Loopback-first web callback listener daemon."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from .callbacks import (
    CONTROL_PREFIX,
    MAX_REQUEST_BODY_BYTES,
    CallbackError,
    all_hits,
    append_hit,
    build_callback_url,
    callback_root,
    callbackd_root,
    callbackd_status_path,
    ensure_private_dir,
    list_listener_metadata,
    load_listener_metadata,
    make_hit,
    make_listener_id,
    new_listener_metadata,
    normalize_bind_host,
    normalize_external_base_url,
    normalize_port,
    normalize_token_path,
    public_listener_metadata,
    read_hits,
    save_listener_metadata,
    validate_callback_roots,
    write_private_json,
)
from .schemas import iso_now, read_json


class CallbackManager:
    def __init__(self, *, bind_host: str, port: int) -> None:
        validate_callback_roots()
        ensure_private_dir(callback_root())
        self.bind_host = bind_host
        self.port = int(port)
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)

    def start(self, payload: dict[str, Any]) -> dict[str, object]:
        listener_id = make_listener_id()
        metadata = new_listener_metadata(
            listener_id=listener_id,
            run_id=payload.get("run_id"),
            challenge_id=payload.get("challenge_id"),
            worker_id=payload.get("worker_id"),
            bind_host=self.bind_host,
            port=self.port,
            external_base_url=payload.get("external_base_url"),
            token_path=payload.get("token_path"),
            status="running",
        )
        with self.lock:
            save_listener_metadata(metadata)
        return {
            "listener": public_listener_metadata(metadata),
            "listener_id": listener_id,
            "local_url": metadata["local_url"],
            "external_url": metadata.get("external_url") or "",
        }

    def callback_url(self, payload: dict[str, Any]) -> dict[str, object]:
        listener_id = str(payload.get("listener_id") or "")
        metadata = load_listener_metadata(listener_id)
        if not metadata:
            raise CallbackError(f"unknown listener_id: {listener_id}")
        url = build_callback_url(metadata, external=bool(payload.get("external", False)), path=payload.get("path"))
        return {"listener_id": listener_id, "url": url, "external": bool(payload.get("external", False))}

    def hits(self, payload: dict[str, Any]) -> dict[str, object]:
        listener_id = str(payload.get("listener_id") or "")
        if not load_listener_metadata(listener_id):
            raise CallbackError(f"unknown listener_id: {listener_id}")
        hits = read_hits(
            listener_id,
            since_hit_id=str(payload.get("since_hit_id") or "") or None,
            limit=int(payload.get("limit") or 20),
        )
        return {"listener_id": listener_id, "hits": hits, "count": len(hits)}

    def wait(self, payload: dict[str, Any]) -> dict[str, object]:
        listener_id = str(payload.get("listener_id") or "")
        if not load_listener_metadata(listener_id):
            raise CallbackError(f"unknown listener_id: {listener_id}")
        timeout_sec = max(0.0, float(payload.get("timeout_sec") or 30))
        min_hits = max(1, int(payload.get("min_hits") or 1))
        pattern = str(payload.get("pattern") or "")
        started = time.monotonic()
        deadline = started + timeout_sec
        matched: list[dict[str, object]] = []
        with self.condition:
            while True:
                hits = all_hits(listener_id)
                if pattern:
                    matched = [hit for hit in hits if pattern in json.dumps(hit, ensure_ascii=False, sort_keys=True)]
                else:
                    matched = hits
                if len(matched) >= min_hits:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(timeout=min(0.2, remaining))
        selected = matched[-min_hits:] if len(matched) >= min_hits else matched
        return {
            "listener_id": listener_id,
            "ok": len(matched) >= min_hits,
            "timed_out": len(matched) < min_hits,
            "count": len(matched),
            "hits": selected,
            "duration_sec": round(time.monotonic() - started, 3),
        }

    def close(self, payload: dict[str, Any]) -> dict[str, object]:
        listener_id = str(payload.get("listener_id") or "")
        reason = str(payload.get("reason") or "closed")
        with self.lock:
            metadata = load_listener_metadata(listener_id)
            if not metadata:
                raise CallbackError(f"unknown listener_id: {listener_id}")
            already_closed = metadata.get("status") in {"closed", "failed"}
            if not already_closed:
                metadata["status"] = "closed"
                metadata["closed_at"] = iso_now()
                metadata["close_reason"] = reason
                metadata["updated_at"] = iso_now()
                save_listener_metadata(metadata)
            return {
                "listener_id": listener_id,
                "status": metadata.get("status"),
                "already_closed": already_closed,
                "hit_count": int(metadata.get("hit_count") or 0),
                "bytes_received": int(metadata.get("bytes_received") or 0),
            }

    def list_listeners(self, payload: dict[str, Any]) -> dict[str, object]:
        listeners = list_listener_metadata(
            run_id=str(payload.get("run_id") or "") or None,
            challenge_id=str(payload.get("challenge_id") or "") or None,
            include_closed=bool(payload.get("include_closed", False)),
        )
        return {"listeners": listeners, "count": len(listeners)}

    def _listener_for_path(self, raw_path: str) -> tuple[dict[str, object] | None, bool | None]:
        parsed = urlsplit(raw_path)
        segments = [unquote(item) for item in parsed.path.strip("/").split("/") if item]
        if not segments:
            return None, None
        listener_id = segments[0]
        metadata = load_listener_metadata(listener_id)
        if not metadata or metadata.get("status") != "running":
            return None, None
        token_path = normalize_token_path(str(metadata.get("token_path") or ""))
        if not token_path:
            return metadata, None
        expected = [part for part in token_path.split("/") if part]
        actual = segments[1 : 1 + len(expected)]
        matched = actual == expected
        return (metadata, True) if matched else (None, False)

    def record_callback(
        self,
        *,
        method: str,
        raw_path: str,
        headers: dict[str, Any],
        body: bytes,
    ) -> bool:
        parsed = urlsplit(raw_path)
        with self.condition:
            metadata, matched_token = self._listener_for_path(raw_path)
            if not metadata:
                return False
            listener_id = str(metadata["listener_id"])
            content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
            hit = make_hit(
                listener_id=listener_id,
                method=method,
                path=parsed.path,
                query=parsed.query,
                headers=headers,
                body=body,
                content_type=content_type,
                matched_token=matched_token,
            )
            append_hit(listener_id, hit)
            metadata["hit_count"] = int(metadata.get("hit_count") or 0) + 1
            metadata["bytes_received"] = int(metadata.get("bytes_received") or 0) + len(body)
            metadata["last_hit_at"] = hit["timestamp"]
            metadata["updated_at"] = iso_now()
            save_listener_metadata(metadata)
            self.condition.notify_all()
            return True


class CallbackHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], token: str) -> None:
        super().__init__(server_address, handler_cls)
        host, port = self.server_address[:2]
        self.manager = CallbackManager(bind_host=str(host), port=int(port))
        self.token = token


class Handler(BaseHTTPRequestHandler):
    server: CallbackHTTPServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_callback_response(self, status: int = 204) -> None:
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.server.token}"

    def _read_json_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, MAX_REQUEST_BODY_BYTES))
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise CallbackError("request payload must be a JSON object")
        return data

    def _read_callback_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(min(length, MAX_REQUEST_BODY_BYTES))

    def _handle_control_get(self) -> None:
        if not self._authorized():
            self._send_json(403, {"ok": False, "error": "forbidden"})
            return
        if self.path.rstrip("/") == f"{CONTROL_PREFIX}/ping":
            self._send_json(200, {"ok": True, "pid": os.getpid()})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def _handle_control_post(self) -> None:
        if not self._authorized():
            self._send_json(403, {"ok": False, "error": "forbidden"})
            return
        try:
            payload = self._read_json_payload()
            result = self._dispatch(payload)
            self._send_json(200, {"ok": True, **result})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def _dispatch(self, payload: dict[str, Any]) -> dict[str, object]:
        path = self.path.rstrip("/")
        manager = self.server.manager
        if path == f"{CONTROL_PREFIX}/start":
            return manager.start(payload)
        if path == f"{CONTROL_PREFIX}/url":
            return manager.callback_url(payload)
        if path == f"{CONTROL_PREFIX}/hits":
            return manager.hits(payload)
        if path == f"{CONTROL_PREFIX}/wait":
            return manager.wait(payload)
        if path == f"{CONTROL_PREFIX}/close":
            return manager.close(payload)
        if path == f"{CONTROL_PREFIX}/list":
            return manager.list_listeners(payload)
        if path == f"{CONTROL_PREFIX}/stop":
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"stopping": True}
        raise CallbackError(f"unknown endpoint: {self.path}")

    def _record_callback(self, method: str) -> None:
        body = b"" if method in {"GET", "HEAD", "OPTIONS"} else self._read_callback_body()
        ok = self.server.manager.record_callback(
            method=method,
            raw_path=self.path,
            headers={str(key): str(value) for key, value in self.headers.items()},
            body=body,
        )
        self._send_callback_response(204 if ok else 404)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith(CONTROL_PREFIX):
            self._handle_control_get()
            return
        self._record_callback("GET")

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith(CONTROL_PREFIX):
            self._handle_control_post()
            return
        self._record_callback("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._record_callback("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._record_callback("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._record_callback("DELETE")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._record_callback("OPTIONS")

    def do_HEAD(self) -> None:  # noqa: N802
        self._record_callback("HEAD")


def _host_from_env() -> str:
    allow_public = os.environ.get("CTF_CALLBACKD_ALLOW_PUBLIC_BIND") == "1"
    return normalize_bind_host(os.environ.get("CTF_CALLBACKD_HOST", "127.0.0.1"), allow_public_bind=allow_public)


def _port_from_env() -> int:
    return normalize_port(os.environ.get("CTF_CALLBACKD_PORT", "0"))


def serve_forever() -> int:
    validate_callback_roots()
    ensure_private_dir(callbackd_root())
    token = secrets.token_urlsafe(32)
    server = CallbackHTTPServer((_host_from_env(), _port_from_env()), Handler, token)
    host, port = server.server_address[:2]
    write_private_json(
        callbackd_status_path(),
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
        try:
            status = Path(callbackd_status_path())
            current = read_json(status, default={})
            if isinstance(current, dict) and int(current.get("pid") or -1) == os.getpid():
                status.unlink(missing_ok=True)
        except Exception:
            pass
        server.server_close()
    return 0
