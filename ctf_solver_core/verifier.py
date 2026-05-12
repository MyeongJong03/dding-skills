"""Solve evidence verifier for local-only challenge runs."""

from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid
from typing import Any

from ctf_solver_core.paths import resolve_path
from ctf_solver_core.schemas import atomic_write_json, iso_now, read_json, utc_now
from ctf_solver_core.session_client import expect_session, read_session, write_session
from ctf_solver_core.sessions import redact_text


VERIFIER_MODES = ("command", "session", "manual")
VERIFIER_TARGETS = ("local", "remote", "unknown")
DEFAULT_TIMEOUT_SEC = 30
DEFAULT_MAX_OUTPUT_BYTES = 8000
ENV_ALLOWLIST = (
    "PATH",
    "TERM",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PYTHONIOENCODING",
)
GENERIC_FLAG_RE = re.compile(r"\b(?:DH|FLAG|flag)\{[^}\r\n]{3,512}\}", re.IGNORECASE)
ESCAPED_FLAG_RE = re.compile(r"\b(?:DH|FLAG|flag)\\\{[^}\r\n]{3,512}\\\}", re.IGNORECASE)


class VerifierError(RuntimeError):
    """Raised when verifier configuration is invalid."""


def make_verifier_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _load_challenge(run_dir: Path | None) -> dict[str, object]:
    if not run_dir:
        return {}
    data = read_json(run_dir / "challenge.json", default={})
    return data if isinstance(data, dict) else {}


def _compile(pattern: str | None, errors: list[str], label: str) -> re.Pattern[str] | None:
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        errors.append(f"invalid {label}: {exc}")
        return None


def _allowed_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


def _bounded_bytes(data: bytes | str, max_bytes: int) -> bytes:
    raw = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
    if max_bytes <= 0:
        return b""
    return raw[-max_bytes:] if len(raw) > max_bytes else raw


def redact_verifier_output(text: str, flag_regex: str | None = None) -> str:
    output = redact_text(text)
    if flag_regex:
        try:
            output = re.sub(flag_regex, "<FLAG_REDACTED>", output, flags=re.MULTILINE)
        except re.error:
            pass
    output = GENERIC_FLAG_RE.sub("<FLAG_REDACTED>", output)
    return ESCAPED_FLAG_RE.sub("<FLAG_REDACTED>", output)


def _preview(stdout: bytes, stderr: bytes, *, max_output_bytes: int, flag_regex: str | None) -> str:
    combined = b""
    if stdout:
        combined += b"[stdout]\n" + stdout
    if stderr:
        if combined:
            combined += b"\n"
        combined += b"[stderr]\n" + stderr
    clipped = _bounded_bytes(combined, max_output_bytes)
    return redact_verifier_output(clipped.decode("utf-8", errors="replace"), flag_regex)


def _evaluate(
    output: str,
    *,
    flag_re: re.Pattern[str] | None,
    success_re: re.Pattern[str] | None,
    fail_re: re.Pattern[str] | None,
    base_success: bool,
) -> tuple[bool, bool, bool, bool]:
    fail_matched = bool(fail_re.search(output)) if fail_re else False
    flag_found = bool(flag_re.search(output)) if flag_re else False
    success_matched = bool(success_re.search(output)) if success_re else False
    has_positive_check = bool(flag_re or success_re)

    if fail_matched:
        success = False
    elif has_positive_check:
        success = bool(flag_found or success_matched)
    else:
        success = bool(base_success)
    return success, flag_found, success_matched, fail_matched


def _target_from_flags(target: str | None, local: bool, remote: bool) -> str:
    if local and remote:
        raise VerifierError("--local and --remote are mutually exclusive")
    if local:
        return "local"
    if remote:
        return "remote"
    value = str(target or "unknown")
    if value not in VERIFIER_TARGETS:
        raise VerifierError(f"unsupported verifier target: {value}")
    return value


def _default_cwd(run_dir: Path | None, requested_cwd: str | None, challenge: dict[str, object]) -> Path:
    if requested_cwd:
        return resolve_path(requested_cwd)
    workspace = challenge.get("workspace")
    if workspace:
        path = resolve_path(str(workspace))
        if path.exists():
            return path
    if run_dir:
        return run_dir
    return Path.cwd().resolve()


def _run_command_attempt(command: str, cwd: Path, timeout_sec: int) -> tuple[int | None, bytes, bytes, list[str]]:
    errors: list[str] = []
    popen_kwargs: dict[str, Any] = {
        "shell": True,
        "cwd": str(cwd),
        "env": _allowed_env(),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **popen_kwargs)
        try:
            stdout, stderr = process.communicate(timeout=max(1, int(timeout_sec)))
            return process.returncode, stdout or b"", stderr or b"", errors
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:  # pragma: no cover - Windows fallback
                process.kill()
            stdout, stderr = process.communicate()
            errors.append(f"timeout after {timeout_sec}s")
            return None, stdout or b"", stderr or b"", errors
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8", errors="replace")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8", errors="replace")
        errors.append(f"timeout after {timeout_sec}s")
        return None, stdout, stderr, errors


def _verify_command(
    *,
    command: str | None,
    cwd: Path,
    timeout_sec: int,
    max_attempts: int,
    flag_re: re.Pattern[str] | None,
    success_re: re.Pattern[str] | None,
    fail_re: re.Pattern[str] | None,
) -> dict[str, Any]:
    if not command:
        raise VerifierError("command mode requires --command")

    all_stdout = b""
    all_stderr = b""
    errors: list[str] = []
    return_code: int | None = None
    success = False
    flag_found = False
    success_matched = False
    fail_matched = False
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        code, stdout, stderr, attempt_errors = _run_command_attempt(command, cwd, timeout_sec)
        return_code = code
        all_stdout += stdout
        all_stderr += stderr
        errors.extend(attempt_errors)
        output = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
        timed_out = any("timeout after" in item for item in attempt_errors)
        success, found, matched, failed = _evaluate(
            output,
            flag_re=flag_re,
            success_re=success_re,
            fail_re=fail_re,
            base_success=(code == 0 and not timed_out),
        )
        flag_found = flag_found or found
        success_matched = success_matched or matched
        fail_matched = fail_matched or failed
        if timed_out:
            success = False
        if success:
            break
    return {
        "success": success,
        "flag_found": flag_found,
        "success_regex_matched": success_matched,
        "fail_regex_matched": fail_matched,
        "attempts": attempts,
        "return_code": return_code,
        "stdout": all_stdout,
        "stderr": all_stderr,
        "errors": errors,
    }


def _verify_manual(
    *,
    evidence_text: str | None,
    flag_re: re.Pattern[str] | None,
    success_re: re.Pattern[str] | None,
    fail_re: re.Pattern[str] | None,
) -> dict[str, Any]:
    if evidence_text is None:
        raise VerifierError("manual mode requires --evidence-text")
    success, flag_found, success_matched, fail_matched = _evaluate(
        evidence_text,
        flag_re=flag_re,
        success_re=success_re,
        fail_re=fail_re,
        base_success=bool(evidence_text.strip()),
    )
    return {
        "success": success,
        "flag_found": flag_found,
        "success_regex_matched": success_matched,
        "fail_regex_matched": fail_matched,
        "attempts": 1,
        "return_code": None,
        "stdout": evidence_text.encode("utf-8", errors="replace"),
        "stderr": b"",
        "errors": [],
    }


def _verify_session(
    *,
    session_id: str | None,
    session_input: str | None,
    expect: list[str],
    timeout_sec: int,
    max_output_bytes: int,
    max_attempts: int,
    flag_re: re.Pattern[str] | None,
    success_re: re.Pattern[str] | None,
    fail_re: re.Pattern[str] | None,
) -> dict[str, Any]:
    if not session_id:
        raise VerifierError("session mode requires --session-id")

    all_stdout = b""
    errors: list[str] = []
    success = False
    flag_found = False
    success_matched = False
    fail_matched = False
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        chunks: list[str] = []
        matched_all = True
        if session_input is not None:
            write_session(session_id, session_input, newline=True)
        if expect:
            for pattern in expect:
                result = expect_session(
                    session_id,
                    [pattern],
                    timeout_ms=max(1, int(timeout_sec * 1000)),
                    max_bytes=max_output_bytes,
                )
                output = str(result.get("output") or "")
                chunks.append(output)
                if result.get("matched") != pattern:
                    matched_all = False
                    errors.append(f"expect not matched: {pattern}")
                    break
        else:
            result = read_session(
                session_id,
                timeout_ms=max(1, int(timeout_sec * 1000)),
                max_bytes=max_output_bytes,
            )
            chunks.append(str(result.get("output") or ""))
        output_text = "\n".join(chunks)
        all_stdout += output_text.encode("utf-8", errors="replace")
        success, found, matched, failed = _evaluate(
            output_text,
            flag_re=flag_re,
            success_re=success_re,
            fail_re=fail_re,
            base_success=matched_all,
        )
        flag_found = flag_found or found
        success_matched = success_matched or matched
        fail_matched = fail_matched or failed
        if success:
            break
    return {
        "success": success,
        "flag_found": flag_found,
        "success_regex_matched": success_matched,
        "fail_regex_matched": fail_matched,
        "attempts": attempts,
        "return_code": None,
        "stdout": all_stdout,
        "stderr": b"",
        "errors": errors,
    }


def _write_evidence(run_dir: Path, stdout: bytes, stderr: bytes) -> str:
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "verifier-output.txt"
    data = b""
    if stdout:
        data += b"[stdout]\n" + stdout
    if stderr:
        if data:
            data += b"\n"
        data += b"[stderr]\n" + stderr
    path.write_bytes(data)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return str(path.relative_to(run_dir))


def verify_run(
    *,
    mode: str,
    run_dir: str | Path | None = None,
    command: str | None = None,
    cwd: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    retries: int = 0,
    flag_regex: str | None = None,
    success_regex: str | None = None,
    fail_regex: str | None = None,
    session_id: str | None = None,
    session_input: str | None = None,
    expect: list[str] | None = None,
    evidence_text: str | None = None,
    target: str = "unknown",
    local: bool = False,
    remote: bool = False,
    label: str | None = None,
    save_result: bool | None = None,
    save_evidence: bool = False,
    redact_output: bool = True,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, object]:
    if mode not in VERIFIER_MODES:
        raise VerifierError(f"unsupported verifier mode: {mode}")
    resolved_run_dir = resolve_path(run_dir) if run_dir else None
    challenge = _load_challenge(resolved_run_dir)
    verifier_target = _target_from_flags(target, local, remote)
    errors: list[str] = []
    flag_re = _compile(flag_regex, errors, "flag_regex")
    success_re = _compile(success_regex, errors, "success_regex")
    fail_re = _compile(fail_regex, errors, "fail_regex")
    max_attempts = max(1, int(retries) + 1)
    timeout_sec = max(1, int(timeout_sec))
    max_output_bytes = max(0, int(max_output_bytes))
    started = time.monotonic()

    if errors:
        raw = {
            "success": False,
            "flag_found": False,
            "success_regex_matched": False,
            "fail_regex_matched": False,
            "attempts": 0,
            "return_code": None,
            "stdout": b"",
            "stderr": b"",
            "errors": errors,
        }
    elif mode == "command":
        raw = _verify_command(
            command=command,
            cwd=_default_cwd(resolved_run_dir, cwd, challenge),
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
            flag_re=flag_re,
            success_re=success_re,
            fail_re=fail_re,
        )
    elif mode == "manual":
        raw = _verify_manual(
            evidence_text=evidence_text,
            flag_re=flag_re,
            success_re=success_re,
            fail_re=fail_re,
        )
    else:
        raw = _verify_session(
            session_id=session_id,
            session_input=session_input,
            expect=expect or [],
            timeout_sec=timeout_sec,
            max_output_bytes=max_output_bytes,
            max_attempts=max_attempts,
            flag_re=flag_re,
            success_re=success_re,
            fail_re=fail_re,
        )

    stdout = bytes(raw.get("stdout") or b"")
    stderr = bytes(raw.get("stderr") or b"")
    evidence_path = None
    if save_evidence and resolved_run_dir:
        evidence_path = _write_evidence(resolved_run_dir, stdout, stderr)

    preview = _preview(
        stdout,
        stderr,
        max_output_bytes=max_output_bytes,
        flag_regex=flag_regex if redact_output else None,
    )
    if not redact_output:
        preview = _bounded_bytes(stdout + b"\n" + stderr, max_output_bytes).decode("utf-8", errors="replace")

    result: dict[str, object] = {
        "schema_version": 1,
        "verifier_id": make_verifier_id(),
        "run_id": str(challenge.get("run_id") or (resolved_run_dir.name if resolved_run_dir else "")),
        "challenge_id": str(challenge.get("challenge_id") or ""),
        "label": label or "",
        "mode": mode,
        "target": verifier_target,
        "success": bool(raw.get("success")),
        "flag_found": bool(raw.get("flag_found")),
        "flag_regex": redact_verifier_output(flag_regex or ""),
        "success_regex_matched": bool(raw.get("success_regex_matched")),
        "fail_regex_matched": bool(raw.get("fail_regex_matched")),
        "attempts": int(raw.get("attempts") or 0),
        "duration_sec": round(time.monotonic() - started, 3),
        "return_code": raw.get("return_code"),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "output_preview": preview,
        "evidence_path": evidence_path,
        "created_at": iso_now(),
        "errors": list(raw.get("errors") or []),
    }

    should_save = bool(resolved_run_dir) if save_result is None else bool(save_result)
    if should_save and resolved_run_dir:
        resolved_run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(resolved_run_dir / "verifier.json", result)
    return result


def load_verifier_result(run_dir: str | Path | None) -> dict[str, object] | None:
    if not run_dir:
        return None
    data = read_json(resolve_path(run_dir) / "verifier.json", default={})
    return data if isinstance(data, dict) and data else None


def verifier_summary(verifier: dict[str, object] | None, *, include_preview: bool = False) -> dict[str, object]:
    if not verifier:
        return {}
    summary: dict[str, object] = {
        "verifier_id": str(verifier.get("verifier_id") or ""),
        "success": bool(verifier.get("success")),
        "flag_found": bool(verifier.get("flag_found")),
        "target": str(verifier.get("target") or "unknown"),
        "mode": str(verifier.get("mode") or "unknown"),
        "label": str(verifier.get("label") or ""),
        "attempts": int(verifier.get("attempts") or 0),
        "duration_sec": verifier.get("duration_sec") if isinstance(verifier.get("duration_sec"), (int, float)) else 0,
        "success_regex_matched": bool(verifier.get("success_regex_matched")),
        "fail_regex_matched": bool(verifier.get("fail_regex_matched")),
        "created_at": str(verifier.get("created_at") or ""),
    }
    if include_preview:
        summary["output_preview"] = str(verifier.get("output_preview") or "")
        path = verifier.get("evidence_path")
        summary["evidence_path"] = str(path) if path else None
    return summary
