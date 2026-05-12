"""Local-only browser action metadata, validation, and redaction helpers."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

from .browser_state import load_browser_profile
from .paths import (
    browser_artifact_root,
    browser_root,
    browser_state_root,
    display_path,
    is_inside_repo,
    repo_root,
    resolve_path,
)
from .schemas import atomic_write_json, iso_now, read_json, utc_now
from .sessions import REDACTED, bounded_text, redact_text


BROWSER_SESSION_STATUSES = ("starting", "running", "closed", "failed")
DEFAULT_BROWSER_TYPE = "chromium"
DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_MAX_TEXT_BYTES = 4_000
DEFAULT_MAX_EVENTS = 100

SENSITIVE_QUERY_KEY_RE = re.compile(
    r"(token|secret|password|passwd|cookie|authorization|api[_-]?key|oauth|session|code|state)",
    re.IGNORECASE,
)
SENSITIVE_HEADER_RE = re.compile(
    r"^(authorization|cookie|set-cookie|proxy-authorization|x-api-key|x-csrf-token|x-xsrf-token)$",
    re.IGNORECASE,
)


class BrowserActionError(RuntimeError):
    """Raised when browser automation cannot safely perform an operation."""


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def write_private_json(path: Path, data: object) -> None:
    ensure_private_dir(path.parent)
    atomic_write_json(path, data)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def make_browser_session_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def browserd_status_path() -> Path:
    return browser_root() / "browserd.json"


def browser_session_metadata_path(browser_session_id: str) -> Path:
    return browser_root() / "sessions" / browser_session_id / "browser_session.json"


def browser_session_artifact_dir(browser_session_id: str) -> Path:
    return browser_artifact_root() / browser_session_id


def validate_local_only_root(path: Path, *, label: str) -> None:
    if is_inside_repo(path):
        raise BrowserActionError(f"{label}_inside_repo")


def validate_storage_state_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = resolve_path(value)
    if is_inside_repo(path):
        raise BrowserActionError("storage_state_path_inside_repo")
    if not path.is_file():
        raise BrowserActionError("storage_state_path_not_found")
    return path


def _profile_matches(data: dict[str, object], profile_name: str, platform: str, event: str) -> bool:
    if str(data.get("profile_name") or "") != profile_name:
        return False
    if platform and str(data.get("platform") or "") != platform:
        return False
    if event and str(data.get("event") or "") != event:
        return False
    return True


def resolve_profile_storage_state(
    *,
    profile_name: str | None = None,
    platform: str | None = None,
    event: str | None = None,
    explicit_storage_state: str | Path | None = None,
) -> tuple[Path | None, dict[str, object]]:
    if explicit_storage_state:
        return validate_storage_state_path(explicit_storage_state), {
            "profile_name": profile_name or "",
            "profile_configured": bool(profile_name),
            "storage_state_configured": True,
            "profile_platform": platform or "",
            "profile_event": event or "",
        }

    if not profile_name:
        return None, {
            "profile_name": "",
            "profile_configured": False,
            "storage_state_configured": False,
            "profile_platform": "",
            "profile_event": "",
        }

    platform_value = platform or ""
    event_value = event or ""
    candidates: list[dict[str, object]] = []
    if platform_value and event_value:
        loaded = load_browser_profile(platform_value, event_value, profile_name)
        if loaded:
            candidates.append(loaded)
    else:
        root = browser_state_root()
        for path in sorted(root.rglob("*.json")) if root.is_dir() else []:
            data = read_json(path, default={})
            if isinstance(data, dict) and _profile_matches(data, profile_name, platform_value, event_value):
                candidates.append(data)

    if not candidates:
        raise BrowserActionError("browser_profile_not_found")
    if len(candidates) > 1:
        raise BrowserActionError("browser_profile_not_unique")
    profile = candidates[0]
    storage_value = str(profile.get("storage_state_path") or "")
    storage_path = validate_storage_state_path(storage_value) if storage_value else None
    return storage_path, {
        "profile_name": profile_name,
        "profile_configured": True,
        "storage_state_configured": bool(storage_path),
        "profile_platform": str(profile.get("platform") or ""),
        "profile_event": str(profile.get("event") or ""),
    }


def new_session_metadata(
    *,
    browser_session_id: str,
    run_id: str | None = None,
    challenge_id: str | None = None,
    worker_id: str | None = None,
    browser_type: str = DEFAULT_BROWSER_TYPE,
    headless: bool = True,
    profile_info: dict[str, object] | None = None,
) -> dict[str, object]:
    now = iso_now()
    artifact_dir = browser_session_artifact_dir(browser_session_id)
    profile = profile_info or {}
    return {
        "schema_version": 1,
        "browser_session_id": browser_session_id,
        "run_id": run_id or "",
        "challenge_id": challenge_id or "",
        "worker_id": worker_id or "",
        "profile_name": str(profile.get("profile_name") or ""),
        "profile_configured": bool(profile.get("profile_configured")),
        "profile_platform": str(profile.get("profile_platform") or ""),
        "profile_event": str(profile.get("profile_event") or ""),
        "storage_state_configured": bool(profile.get("storage_state_configured")),
        "status": "starting",
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "close_reason": "",
        "browser_type": browser_type,
        "headless": bool(headless),
        "current_url": "",
        "pages_count": 0,
        "artifact_dir": str(artifact_dir),
        "actions_count": 0,
        "screenshot_count": 0,
        "network_event_count": 0,
        "console_event_count": 0,
        "last_error": "",
    }


def redact_url(url: str) -> str:
    text = redact_text(str(url))
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if SENSITIVE_QUERY_KEY_RE.search(key):
            query.append((key, REDACTED))
        else:
            query.append((key, redact_text(value)))
    fragment = REDACTED if SENSITIVE_QUERY_KEY_RE.search(parts.fragment) else redact_text(parts.fragment)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), fragment))


def redact_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in (headers or {}).items():
        key_text = str(key)
        if SENSITIVE_HEADER_RE.search(key_text):
            redacted[key_text] = REDACTED
        else:
            redacted[key_text] = bounded_text(str(value), max_bytes=512)
    return redacted


def redacted_cookie_summary(item: dict[str, Any]) -> dict[str, object]:
    return {
        "name": str(item.get("name") or ""),
        "domain": str(item.get("domain") or ""),
        "path": str(item.get("path") or ""),
        "expires": item.get("expires"),
        "httpOnly": bool(item.get("httpOnly")),
        "secure": bool(item.get("secure")),
        "sameSite": str(item.get("sameSite") or ""),
        "value": REDACTED,
    }


def redacted_cookies(cookies: list[dict[str, Any]]) -> list[dict[str, object]]:
    return [redacted_cookie_summary(cookie) for cookie in cookies]


def redacted_network_event(event: dict[str, Any]) -> dict[str, object]:
    out: dict[str, object] = {
        "type": str(event.get("type") or ""),
        "method": str(event.get("method") or ""),
        "url": redact_url(str(event.get("url") or "")),
        "status": event.get("status"),
        "timestamp": str(event.get("timestamp") or ""),
    }
    headers = event.get("headers")
    if isinstance(headers, dict):
        out["headers"] = redact_headers(headers)
    error = str(event.get("error") or "")
    if error:
        out["error"] = bounded_text(error, max_bytes=512)
    return out


def bounded_result(value: Any, *, max_bytes: int = DEFAULT_MAX_TEXT_BYTES) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            import json

            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = repr(value)
    return bounded_text(text, max_bytes=max_bytes)


def public_session_metadata(metadata: dict[str, object]) -> dict[str, object]:
    item = dict(metadata)
    current_url = str(item.get("current_url") or "")
    if current_url:
        item["current_url"] = redact_url(current_url)
    artifact_dir = str(item.get("artifact_dir") or "")
    if artifact_dir:
        item["artifact_dir"] = display_path(Path(artifact_dir))
    item.pop("storage_state_path", None)
    item.pop("token", None)
    return item


def list_browser_session_metadata(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    include_closed: bool = False,
) -> list[dict[str, object]]:
    root = browser_root() / "sessions"
    records: list[dict[str, object]] = []
    for path in sorted(root.glob("*/browser_session.json")) if root.is_dir() else []:
        data = read_json(path, default={})
        if not isinstance(data, dict) or not data.get("browser_session_id"):
            continue
        if run_id and data.get("run_id") != run_id:
            continue
        if challenge_id and data.get("challenge_id") != challenge_id:
            continue
        if not include_closed and data.get("status") not in {"starting", "running"}:
            continue
        records.append(public_session_metadata(data))
    records.sort(key=lambda item: str(item.get("created_at") or ""))
    return records


def active_browser_session_count() -> int:
    return len(list_browser_session_metadata(include_closed=False))


def mark_orphaned_browser_sessions_for_run(run_id: str, *, reason: str) -> dict[str, object]:
    if not run_id:
        raise BrowserActionError("run_id is required")
    root = browser_root() / "sessions"
    count = 0
    for path in sorted(root.glob("*/browser_session.json")) if root.is_dir() else []:
        data = read_json(path, default={})
        if not isinstance(data, dict) or data.get("run_id") != run_id:
            continue
        if data.get("status") not in {"starting", "running"}:
            continue
        data["status"] = "failed"
        data["closed_at"] = data.get("closed_at") or iso_now()
        data["close_reason"] = reason
        data["updated_at"] = iso_now()
        data["last_error"] = reason
        write_private_json(path, data)
        count += 1
    return {
        "session_count": count,
        "closed_browser_session_count": 0,
        "browser_actions_count": 0,
        "browser_screenshot_count": 0,
        "browser_network_event_count": 0,
        "errors": [reason] if count else [],
    }


def repo_path_for_doctor() -> Path:
    return repo_root()
