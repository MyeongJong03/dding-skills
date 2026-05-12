"""Loopback-only persistent session daemon."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

try:
    import fcntl
    import pty
    import select
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None
    pty = None
    select = None

from ctf_solver_core.paths import session_root, sessiond_root
from ctf_solver_core.schemas import iso_now, read_json
from ctf_solver_core.sessions import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_MS,
    SessionError,
    bounded_text,
    build_command_spec,
    daemon_status_path,
    ensure_private_dir,
    initial_metadata,
    make_session_id,
    session_metadata_path,
    write_private_json,
)


class ManagedSession:
    def __init__(self, metadata: dict[str, object], process: subprocess.Popen[bytes], master_fd: int | None) -> None:
        self.metadata = metadata
        self.process = process
        self.master_fd = master_fd
        self.lock = threading.RLock()
        self.pipe_buffer = bytearray()
        self.pipe_lock = threading.RLock()
        self.reader_thread: threading.Thread | None = None
        stdout = process.stdout
        if master_fd is None and stdout is not None:
            self.reader_thread = threading.Thread(target=self._pipe_reader, args=(stdout,), daemon=True)
            self.reader_thread.start()

    @property
    def session_id(self) -> str:
        return str(self.metadata["session_id"])

    def _pipe_reader(self, stream: Any) -> None:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            with self.pipe_lock:
                self.pipe_buffer.extend(chunk)

    def _persist(self) -> None:
        write_private_json(session_metadata_path(self.session_id), self.metadata)

    def _touch(self) -> None:
        self.metadata["updated_at"] = iso_now()

    def refresh_status(self) -> None:
        with self.lock:
            if self.metadata.get("status") not in {"running", "starting"}:
                return
            code = self.process.poll()
            if code is None:
                if self.metadata.get("status") == "starting":
                    self.metadata["status"] = "running"
                    self._touch()
                    self._persist()
                return
            self.metadata["status"] = "closed" if code == 0 else "failed"
            self.metadata["closed_at"] = iso_now()
            self.metadata["close_reason"] = f"process_exited:{code}"
            self._touch()
            self._persist()

    def write(self, data: bytes) -> dict[str, object]:
        with self.lock:
            self.refresh_status()
            if self.metadata.get("status") not in {"running", "starting"}:
                raise SessionError(f"session is not running: {self.metadata.get('status')}")
            if self.master_fd is not None:
                os.write(self.master_fd, data)
            else:
                if self.process.stdin is None:
                    raise SessionError("session stdin is not available")
                self.process.stdin.write(data)
                self.process.stdin.flush()
            self.metadata["bytes_written"] = int(self.metadata.get("bytes_written") or 0) + len(data)
            self._touch()
            self._persist()
            return {"session_id": self.session_id, "bytes_written": len(data), "status": self.metadata["status"]}

    def read(self, *, timeout_ms: int = DEFAULT_TIMEOUT_MS, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
        with self.lock:
            self.refresh_status()
            if self.master_fd is not None:
                raw = self._read_pty(timeout_ms=timeout_ms, max_bytes=max_bytes)
            else:
                raw = self._read_pipe(timeout_ms=timeout_ms, max_bytes=max_bytes)
            if raw:
                self.metadata["bytes_read"] = int(self.metadata.get("bytes_read") or 0) + len(raw)
                self.metadata["last_read_at"] = iso_now()
                self._touch()
                self._persist()
            return {
                "session_id": self.session_id,
                "output": bounded_text(raw, max_bytes=max_bytes),
                "bytes_read": len(raw),
                "status": self.metadata.get("status"),
            }

    def _read_pty(self, *, timeout_ms: int, max_bytes: int) -> bytes:
        if self.master_fd is None or select is None:
            return b""
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        chunks: list[bytes] = []
        total = 0
        while total < max_bytes:
            remaining = deadline - time.monotonic()
            if remaining < 0:
                remaining = 0
            readable, _, _ = select.select([self.master_fd], [], [], remaining)
            if not readable:
                break
            try:
                chunk = os.read(self.master_fd, min(4096, max_bytes - total))
            except BlockingIOError:
                continue
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if timeout_ms == 0:
                break
        return b"".join(chunks)

    def _read_pipe(self, *, timeout_ms: int, max_bytes: int) -> bytes:
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        while True:
            with self.pipe_lock:
                if self.pipe_buffer:
                    chunk = bytes(self.pipe_buffer[:max_bytes])
                    del self.pipe_buffer[:max_bytes]
                    return chunk
            if time.monotonic() >= deadline:
                return b""
            time.sleep(0.02)

    def expect(
        self,
        *,
        patterns: list[str],
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> dict[str, object]:
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        collected = ""
        raw_len = 0
        matched: str | None = None
        matched_index: int | None = None
        while raw_len < max_bytes:
            remaining_ms = int(max(0, deadline - time.monotonic()) * 1000)
            result = self.read(timeout_ms=min(100, remaining_ms), max_bytes=max_bytes - raw_len)
            output = str(result.get("output") or "")
            if output:
                collected += output
                raw_len += int(result.get("bytes_read") or len(output.encode("utf-8", errors="replace")))
                for index, pattern in enumerate(patterns):
                    if pattern in collected:
                        matched = pattern
                        matched_index = index
                        break
            if matched is not None or time.monotonic() >= deadline:
                break
            if not output:
                time.sleep(0.02)
        return {
            "session_id": self.session_id,
            "matched": matched,
            "matched_index": matched_index,
            "timed_out": matched is None,
            "output": bounded_text(collected, max_bytes=max_bytes),
            "status": self.metadata.get("status"),
        }

    def close(self, reason: str = "closed") -> dict[str, object]:
        with self.lock:
            if self.metadata.get("status") in {"closed", "failed"}:
                return {"session_id": self.session_id, "status": self.metadata.get("status"), "already_closed": True}
            self._terminate_process()
            self.metadata["status"] = "closed"
            self.metadata["closed_at"] = iso_now()
            self.metadata["close_reason"] = reason
            self._touch()
            self._persist()
            if self.master_fd is not None:
                try:
                    os.close(self.master_fd)
                except OSError:
                    pass
                self.master_fd = None
            return {"session_id": self.session_id, "status": "closed", "already_closed": False}

    def _terminate_process(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(self.process.pid, signal.SIGTERM)
            else:  # pragma: no cover - Windows fallback
                self.process.terminate()
            self.process.wait(timeout=2)
            return
        except Exception:
            pass
        try:
            if os.name != "nt":
                os.killpg(self.process.pid, signal.SIGKILL)
            else:  # pragma: no cover - Windows fallback
                self.process.kill()
            self.process.wait(timeout=2)
        except Exception:
            pass


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, ManagedSession] = {}
        self.lock = threading.RLock()
        ensure_private_dir(session_root())

    def start(self, payload: dict[str, Any]) -> dict[str, object]:
        kind = str(payload.get("kind") or "")
        explicit_env = payload.get("env")
        if explicit_env is not None and not isinstance(explicit_env, dict):
            raise SessionError("env must be a JSON object when provided")
        spec = build_command_spec(
            kind=kind,
            command=payload.get("command"),
            cwd=payload.get("cwd"),
            host=payload.get("host"),
            port=payload.get("port"),
            image=payload.get("image"),
            workspace=payload.get("workspace"),
            env={str(k): str(v) for k, v in (explicit_env or {}).items()},
        )
        session_id = make_session_id()
        metadata = initial_metadata(
            session_id=session_id,
            kind=kind,
            spec=spec,
            run_id=payload.get("run_id"),
            challenge_id=payload.get("challenge_id"),
            worker_id=payload.get("worker_id"),
        )
        write_private_json(session_metadata_path(session_id), metadata)
        try:
            process, master_fd = self._spawn(spec.argv, cwd=spec.cwd, env=spec.env)
        except Exception as exc:
            metadata["status"] = "failed"
            metadata["closed_at"] = iso_now()
            metadata["close_reason"] = str(exc)
            metadata["updated_at"] = iso_now()
            write_private_json(session_metadata_path(session_id), metadata)
            raise
        metadata["pid"] = process.pid
        metadata["status"] = "running"
        metadata["updated_at"] = iso_now()
        write_private_json(session_metadata_path(session_id), metadata)
        managed = ManagedSession(metadata, process, master_fd)
        with self.lock:
            self.sessions[session_id] = managed
        return {"session": dict(metadata)}

    def _spawn(self, argv: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[subprocess.Popen[bytes], int | None]:
        if os.name != "nt" and pty is not None and fcntl is not None:
            master_fd, slave_fd = pty.openpty()
            try:
                flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
                fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                process = subprocess.Popen(
                    argv,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    cwd=str(cwd),
                    env=env,
                    start_new_session=True,
                    close_fds=True,
                )
            finally:
                os.close(slave_fd)
            return process, master_fd
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            env=env,
        )
        return process, None

    def _get(self, session_id: str) -> ManagedSession:
        with self.lock:
            session = self.sessions.get(session_id)
        if not session:
            raise SessionError(f"unknown or inactive session: {session_id}")
        session.refresh_status()
        return session

    def write(self, payload: dict[str, Any]) -> dict[str, object]:
        session_id = str(payload.get("session_id") or "")
        data = payload.get("data")
        if data is None:
            raise SessionError("data is required")
        encoding = str(payload.get("encoding") or "text")
        if encoding == "base64":
            raw = base64.b64decode(str(data).encode("ascii"), validate=True)
        elif encoding == "text":
            raw = str(data).encode("utf-8")
        else:
            raise SessionError("encoding must be text or base64")
        if bool(payload.get("newline", True)):
            raw += b"\n"
        return self._get(session_id).write(raw)

    def read(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("session_id") or "")).read(
            timeout_ms=int(payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS),
            max_bytes=int(payload.get("max_bytes") or DEFAULT_MAX_BYTES),
        )

    def expect(self, payload: dict[str, Any]) -> dict[str, object]:
        patterns = payload.get("patterns")
        if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
            raise SessionError("patterns must be a list of strings")
        return self._get(str(payload.get("session_id") or "")).expect(
            patterns=patterns,
            timeout_ms=int(payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS),
            max_bytes=int(payload.get("max_bytes") or DEFAULT_MAX_BYTES),
        )

    def close(self, payload: dict[str, Any]) -> dict[str, object]:
        return self._get(str(payload.get("session_id") or "")).close(str(payload.get("reason") or "closed"))

    def list_sessions(self, payload: dict[str, Any]) -> dict[str, object]:
        run_id = str(payload.get("run_id") or "")
        challenge_id = str(payload.get("challenge_id") or "")
        include_closed = bool(payload.get("include_closed", False))
        for session in list(self.sessions.values()):
            session.refresh_status()
        records: dict[str, dict[str, object]] = {}
        with self.lock:
            live_ids = set(self.sessions.keys())
        for path in sorted(session_root().glob("*/session.json")):
            data = read_json(path, default={})
            if isinstance(data, dict) and data.get("session_id"):
                session_id = str(data["session_id"])
                if session_id not in live_ids and data.get("status") in {"starting", "running"}:
                    data["status"] = "failed"
                    data["closed_at"] = data.get("closed_at") or iso_now()
                    data["close_reason"] = data.get("close_reason") or "daemon_restarted"
                    data["updated_at"] = iso_now()
                    write_private_json(path, data)
                records[str(data["session_id"])] = data
        with self.lock:
            for session_id, session in self.sessions.items():
                records[session_id] = dict(session.metadata)
        filtered: list[dict[str, object]] = []
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

    def close_all(self, reason: str = "daemon_stop") -> None:
        with self.lock:
            sessions = list(self.sessions.values())
        for session in sessions:
            try:
                session.close(reason)
            except Exception:
                pass


class SessionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], token: str) -> None:
        super().__init__(server_address, handler_cls)
        self.manager = SessionManager()
        self.token = token


class Handler(BaseHTTPRequestHandler):
    server: SessionHTTPServer

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
            raise SessionError("request payload must be a JSON object")
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
        if path == "/write":
            return manager.write(payload)
        if path == "/read":
            return manager.read(payload)
        if path == "/expect":
            return manager.expect(payload)
        if path == "/close":
            return manager.close(payload)
        if path == "/list":
            return manager.list_sessions(payload)
        if path == "/stop":
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"stopping": True}
        raise SessionError(f"unknown endpoint: {self.path}")


def _host_from_env() -> str:
    host = os.environ.get("CTF_SESSIOND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host != "127.0.0.1":
        raise SessionError("CTF_SESSIOND_HOST must be 127.0.0.1")
    return host


def _port_from_env() -> int:
    raw = os.environ.get("CTF_SESSIOND_PORT", "0").strip() or "0"
    try:
        port = int(raw)
    except ValueError as exc:
        raise SessionError("CTF_SESSIOND_PORT must be an integer") from exc
    if port < 0 or port > 65535:
        raise SessionError("CTF_SESSIOND_PORT must be between 0 and 65535")
    return port


def serve_forever() -> int:
    ensure_private_dir(sessiond_root())
    token = secrets.token_urlsafe(32)
    server = SessionHTTPServer((_host_from_env(), _port_from_env()), Handler, token)
    host, port = server.server_address[:2]
    write_private_json(
        daemon_status_path(),
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
        server.manager.close_all("daemon_stop")
        try:
            status = Path(daemon_status_path())
            current = read_json(status, default={})
            if isinstance(current, dict) and int(current.get("pid") or -1) == os.getpid():
                status.unlink(missing_ok=True)
        except Exception:
            pass
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_forever())
