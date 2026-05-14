"""Dreamhack platform adapter scaffold.

The adapter is fixture-first for discovery/downloads. Live VM actions are
available only through explicit opt-in callers that provide local-only auth
material; raw Dreamhack responses and auth values are never returned or stored.
"""

from __future__ import annotations

from html.parser import HTMLParser
import json
from json import JSONDecodeError
import os
from pathlib import Path
from socket import timeout as SocketTimeout
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from ..paths import dreamhack_fixture_root, is_inside_repo, platform_automation_root, repo_root, resolve_path
from ..platform_adapters import PlatformAdapter, PlatformAdapterError, _copy_file
from ..schemas import CATEGORIES, atomic_write_json, iso_now, read_json, slugify, validate_public_record


DREAMHACK_BASE_URL = "https://dreamhack.io"
DREAMHACK_LIVE_TIMEOUT_SECONDS = 15
DREAMHACK_LIVE_MAX_BYTES = 1024 * 1024
DREAMHACK_VM_ACTIONS = {"start", "stop", "restart", "status"}
DREAMHACK_REPO_FIXTURE_ROOT = Path("tests") / "fixtures" / "dreamhack"
DREAMHACK_FIXTURE_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "csrf",
    "csrf_token",
    "csrfmiddlewaretoken",
    "raw_response",
    "response_body",
    "session",
    "session_id",
    "sessionid",
    "set-cookie",
    "set_cookie",
    "storage_state",
}


def _is_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
            return True
        if lowered in {"false", "no", "off", "0"}:
            return False
    return default


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _normalize_category(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or value.get("slug") or value.get("category")
    category = str(value or "unknown").strip().lower()
    return category if category in CATEGORIES else "unknown"


def _repo_dummy_fixture_allowed(path: Path) -> bool:
    if not is_inside_repo(path):
        return True
    try:
        path.resolve().relative_to((repo_root() / DREAMHACK_REPO_FIXTURE_ROOT).resolve())
        return True
    except ValueError:
        return False


def _resolve_fixture_path(source: str) -> Path:
    path = Path(source).expanduser()
    candidates = [path.resolve()]
    if not path.is_absolute():
        candidates.append((dreamhack_fixture_root() / source).resolve())
    for candidate in candidates:
        if candidate.is_file():
            if not _repo_dummy_fixture_allowed(candidate):
                raise PlatformAdapterError("dreamhack_repo_fixture_not_allowed")
            return candidate
    return candidates[0]


def _require_fixture_source(source: str | None) -> Path:
    if not source:
        raise PlatformAdapterError("source_required")
    if _is_url(source):
        raise PlatformAdapterError("dreamhack_live_mode_requires_opt_in")
    path = _resolve_fixture_path(source)
    if not path.is_file():
        raise PlatformAdapterError("source_not_found")
    return path


def _live_base_url(base_url: str | None = None) -> str:
    candidate = str(base_url or DREAMHACK_BASE_URL).strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PlatformAdapterError("dreamhack_base_url_invalid")
    if parsed.username or parsed.password:
        raise PlatformAdapterError("dreamhack_base_url_must_not_include_userinfo")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _vm_url(challenge_id: str, base_url: str | None = None) -> str:
    root = _live_base_url(base_url)
    path = f"api/v1/wargame/challenges/{quote(str(challenge_id).strip(), safe='')}/live/"
    return urljoin(root.rstrip("/") + "/", path)


def _read_auth_file(path_value: str, label: str) -> str:
    path = resolve_path(path_value)
    if is_inside_repo(path):
        raise PlatformAdapterError(f"dreamhack_{label}_file_inside_repo")
    if not path.is_file():
        raise PlatformAdapterError(f"dreamhack_{label}_file_not_found")
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _auth_summary(session_id: str, csrf_value: str) -> dict[str, object]:
    return {
        "session_configured": bool(session_id),
        "csrf_configured": bool(csrf_value),
    }


def _safe_state(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 80:
        return "present"
    if any(marker in text for marker in ("{", "}", "\n", "\r", "://", "=")):
        return "present"
    return text


def _walk_first(node: object, keys: set[str]) -> object | None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in keys and value not in {None, ""}:
                return value
        for value in node.values():
            found = _walk_first(value, keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _walk_first(value, keys)
            if found is not None:
                return found
    return None


def _first_value(item: dict[str, object], *keys: str) -> object | None:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for key in keys:
        if key in item and item[key] is not None and item[key] != "":
            return item[key]
        lowered_value = lowered.get(key.lower())
        if lowered_value is not None and lowered_value != "":
            return lowered_value
    return None


def _has_sensitive_fixture_key(node: object) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in DREAMHACK_FIXTURE_SENSITIVE_KEYS:
                return True
            if _has_sensitive_fixture_key(value):
                return True
    elif isinstance(node, list):
        return any(_has_sensitive_fixture_key(value) for value in node)
    return False


def _read_json_fixture(path: Path) -> object:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise PlatformAdapterError("dreamhack_fixture_invalid_json") from exc
    if _has_sensitive_fixture_key(data):
        raise PlatformAdapterError("dreamhack_fixture_contains_sensitive_fields")
    return data


def _extract_port(data: object) -> int | None:
    found = _walk_first(data, {"port", "server_port"})
    value = _int(found)
    if value is None or not (0 < value < 65536):
        return None
    return value


def _host_present(data: object) -> bool:
    found = _walk_first(data, {"host", "hostname", "server_host", "domain", "ip", "url"})
    return bool(str(found or "").strip())


def _vm_state(data: object, status_code: int | None) -> str:
    found = _walk_first(data, {"vm_state", "state", "status", "server_status"})
    state = _safe_state(found)
    if state:
        return state
    if status_code is None:
        return "unknown"
    return "http_success" if 200 <= status_code < 300 else "http_error"


def _read_response_body(response) -> object:
    body = response.read(DREAMHACK_LIVE_MAX_BYTES + 1)
    if len(body) > DREAMHACK_LIVE_MAX_BYTES:
        raise PlatformAdapterError("dreamhack_live_response_too_large")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"text_present": bool(body)}


def _request_once(
    *,
    action: str,
    challenge_id: str,
    session_id: str,
    csrf_value: str,
    base_url: str | None = None,
) -> tuple[int, object]:
    method = {"status": "GET", "start": "POST", "stop": "DELETE"}[action]
    url = _vm_url(challenge_id, base_url)
    csrf_cookie_name = "csrf_" + "token"
    headers = {
        "Accept": "application/json",
        "Origin": _live_base_url(base_url),
        "Referer": urljoin(_live_base_url(base_url).rstrip("/") + "/", f"wargame/challenges/{challenge_id}"),
        "User-Agent": "ctf-solver/dreamhack-vm-control",
        "X-CSRFToken": csrf_value,
        "Cookie": f"sessionid={session_id}; {csrf_cookie_name}={csrf_value}",
    }
    request = Request(url, data=b"" if method == "POST" else None, headers=headers, method=method)
    try:
        with urlopen(request, timeout=DREAMHACK_LIVE_TIMEOUT_SECONDS) as response:
            return int(response.status), _read_response_body(response)
    except HTTPError as exc:
        try:
            data = _read_response_body(exc)
        except PlatformAdapterError:
            data = {"http_error": exc.code}
        return int(exc.code), data
    except (TimeoutError, SocketTimeout) as exc:
        raise PlatformAdapterError("network_timeout") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", "")
        if isinstance(reason, (TimeoutError, SocketTimeout)) or "timed out" in str(reason).lower():
            raise PlatformAdapterError("network_timeout") from exc
        raise PlatformAdapterError("network_error") from exc


def _vm_action_live(
    *,
    action: str,
    challenge_id: str,
    session_id: str,
    csrf_value: str,
    base_url: str | None = None,
) -> tuple[int, object]:
    if action == "restart":
        _request_once(
            action="stop",
            challenge_id=challenge_id,
            session_id=session_id,
            csrf_value=csrf_value,
            base_url=base_url,
        )
        return _request_once(
            action="start",
            challenge_id=challenge_id,
            session_id=session_id,
            csrf_value=csrf_value,
            base_url=base_url,
        )
    return _request_once(
        action=action,
        challenge_id=challenge_id,
        session_id=session_id,
        csrf_value=csrf_value,
        base_url=base_url,
    )


def _vm_summary(
    *,
    action: str,
    challenge_id: str,
    live: bool,
    session_id: str,
    csrf_value: str,
    status_code: int | None = None,
    data: object | None = None,
    ok: bool | None = None,
    reason: str = "",
) -> dict[str, object]:
    success = bool(ok) if ok is not None else bool(status_code is not None and 200 <= status_code < 300)
    summary: dict[str, object] = {
        "ok": success,
        "adapter": "dreamhack",
        "action": action,
        "challenge_id": str(challenge_id),
        "live": bool(live),
        "status": "success" if success else "error",
        "vm_state": _vm_state(data, status_code),
        "auth": _auth_summary(session_id, csrf_value),
    }
    if status_code is not None:
        summary["status_code"] = int(status_code)
    if reason:
        summary["reason"] = reason
    if data is not None and _host_present(data):
        summary["host"] = "<redacted>"
    port = _extract_port(data)
    if port is not None:
        summary["port"] = port
    errors = validate_public_record(summary)
    if errors:
        raise PlatformAdapterError("dreamhack_vm_summary_not_public_safe")
    return summary


class _DreamhackHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        challenge_id = data.get("data-challenge-id") or data.get("data-id") or data.get("value")
        name = data.get("data-name") or data.get("aria-label") or data.get("title")
        if not challenge_id and not name:
            return
        item: dict[str, object] = {
            "id": challenge_id or "",
            "name": name or challenge_id or "challenge",
            "category": data.get("data-category") or "unknown",
        }
        href = data.get("href")
        if tag == "a" and href:
            item["url"] = href
        files = data.get("data-files")
        if files:
            item["files"] = [part.strip() for part in files.split(",") if part.strip()]
        tags = data.get("data-tags")
        if tags:
            item["tags"] = [part.strip() for part in tags.split(",") if part.strip()]
        self.items.append(item)


def _unwrap_items(data: object) -> list[dict[str, object]]:
    if isinstance(data, dict):
        for key in ("challenges", "wargames", "problems", "results", "items"):
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]  # type: ignore[index]
        if isinstance(data.get("data"), list):
            return [item for item in data["data"] if isinstance(item, dict)]  # type: ignore[index]
        if isinstance(data.get("data"), dict):
            nested = data["data"]  # type: ignore[index]
            nested_items = _unwrap_items(nested)
            if nested_items:
                return nested_items
        if isinstance(data.get("response"), dict):
            nested_items = _unwrap_items(data["response"])  # type: ignore[index]
            if nested_items:
                return nested_items
        if any(key in data for key in ("name", "title", "category", "files", "attachments", "wargame_id")):
            return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _unwrap_detail(data: object) -> dict[str, object] | None:
    if isinstance(data, dict):
        for key in ("challenge", "wargame", "problem", "detail"):
            value = data.get(key)
            if isinstance(value, dict):
                return value
        data_value = data.get("data")
        if isinstance(data_value, dict):
            nested = _unwrap_detail(data_value)
            return nested if nested is not None else data_value
        response = data.get("response")
        if isinstance(response, dict):
            nested = _unwrap_detail(response)
            return nested if nested is not None else response
        if any(key in data for key in ("name", "title", "category", "files", "attachments", "wargame_id")):
            return data
    return None


def _file_name(raw: object) -> str | None:
    if isinstance(raw, str):
        path = urlparse(raw).path if _is_url(raw) else raw
        name = Path(path).name.strip()
        return name or None
    if isinstance(raw, dict):
        value = raw.get("name") or raw.get("filename") or raw.get("path") or raw.get("source") or raw.get("url")
        if value:
            return _file_name(str(value))
    return None


def _item_files(item: dict[str, object]) -> list[str]:
    files: list[str] = []
    for key in ("files", "attachments", "handouts", "downloads"):
        raw = item.get(key)
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        for entry in raw:
            name = _file_name(entry)
            if name:
                files.append(name)
    return files


def _tags(raw: object) -> list[str]:
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    for item in raw:
        if isinstance(item, str):
            tags.append(item)
        elif isinstance(item, dict):
            value = item.get("name") or item.get("value") or item.get("tag")
            if value:
                tags.append(str(value))
    return tags


def _normalize_challenge(platform: str, event: str, item: dict[str, object], index: int) -> dict[str, object]:
    external_id = str(_first_value(item, "external_id", "id", "wargame_id", "problem_id") or "").strip()
    name = str(
        _first_value(item, "name", "title", "challenge_name", "problem_title")
        or (f"challenge-{external_id}" if external_id else f"challenge-{index}")
    )
    category = _normalize_category(_first_value(item, "category", "type"))
    challenge_id = str(_first_value(item, "challenge_id") or "").strip()
    if not external_id and challenge_id and "/" not in challenge_id:
        external_id = challenge_id
    if challenge_id == external_id:
        challenge_id = ""
    if not challenge_id:
        challenge_id = "/".join(
            [
                "dreamhack",
                slugify(event, fallback="event", max_length=48),
                slugify(category, fallback="unknown", max_length=24),
                slugify(name or external_id, fallback="challenge", max_length=72),
            ]
        )
    normalized: dict[str, object] = {
        "challenge_id": challenge_id,
        "external_id": external_id,
        "name": name,
        "title": name,
        "category": category,
        "platform": platform,
        "event": event,
        "remote_required": _bool(
            _first_value(item, "remote_required"),
            bool(_first_value(item, "has_vm", "server", "connection_info")),
        ),
        "local_capable": _bool(_first_value(item, "local_capable"), True),
    }
    url = str(_first_value(item, "url", "link", "href") or "").strip()
    if url:
        normalized["url"] = url
    value = _int(_first_value(item, "value", "points", "point"))
    if value is not None:
        normalized["value"] = value
    solves = _int(_first_value(item, "solves", "solved_count", "solve_count"))
    if solves is not None:
        normalized["solves"] = solves
    files = _item_files(item)
    if files:
        normalized["files"] = files
    tags = _tags(item.get("tags"))
    if tags:
        normalized["tags"] = tags
    return normalized


def _load_fixture_items(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".json":
        return _unwrap_items(_read_json_fixture(path))
    parser = _DreamhackHTMLParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.items


def _find_item(path: Path, platform: str, event: str, challenge_id: str) -> dict[str, object]:
    if path.suffix.lower() == ".json":
        detail = _unwrap_detail(_read_json_fixture(path))
        if detail is not None:
            normalized = _normalize_challenge(platform, event, detail, 1)
            candidates = {
                str(normalized.get("challenge_id") or ""),
                str(normalized.get("external_id") or ""),
                str(_first_value(detail, "id", "wargame_id", "challenge_id", "problem_id") or ""),
                str(_first_value(detail, "name", "title") or ""),
            }
            if challenge_id in candidates:
                return detail
    for index, item in enumerate(_load_fixture_items(path), start=1):
        normalized = _normalize_challenge(platform, event, item, index)
        candidates = {
            str(normalized.get("challenge_id") or ""),
            str(normalized.get("external_id") or ""),
            str(_first_value(item, "id", "wargame_id", "challenge_id", "problem_id") or ""),
            str(_first_value(item, "name", "title") or ""),
        }
        if challenge_id in candidates:
            return item
    raise PlatformAdapterError("challenge_detail_not_found")


def _local_source_path(fixture: Path, raw: str) -> Path:
    if _is_url(raw):
        raise PlatformAdapterError("dreamhack_fixture_file_requires_local_path")
    path = Path(raw).expanduser()
    if path.is_absolute() and path.is_file():
        return path.resolve()
    return (fixture.parent / raw.lstrip("/")).resolve()


def _download_entries(fixture: Path, item: dict[str, object]) -> list[tuple[Path, str]]:
    entries: list[tuple[Path, str]] = []
    for key in ("files", "attachments", "handouts", "downloads"):
        raw_files = item.get(key)
        if isinstance(raw_files, dict):
            raw_files = [raw_files]
        if not isinstance(raw_files, list):
            continue
        for raw in raw_files:
            if isinstance(raw, str):
                name = Path(urlparse(raw).path if _is_url(raw) else raw).name
                entries.append((_local_source_path(fixture, raw), name))
            elif isinstance(raw, dict):
                value = raw.get("path") or raw.get("source") or raw.get("url")
                if not value:
                    continue
                name = str(raw.get("name") or raw.get("filename") or Path(str(value)).name)
                entries.append((_local_source_path(fixture, str(value)), name))
    return entries


def _server_dir(platform: str, event: str) -> Path:
    return (
        platform_automation_root()
        / slugify(platform, fallback="platform", max_length=64)
        / slugify(event, fallback="event", max_length=80)
        / "servers"
    )


def _server_path(platform: str, event: str, server_id: str) -> Path:
    return _server_dir(platform, event) / f"{slugify(server_id, fallback='server', max_length=160)}.json"


def _server_files(platform: str, event: str) -> list[Path]:
    root = _server_dir(platform, event)
    return sorted(root.glob("*.json")) if root.is_dir() else []


def _read_server(path: Path) -> dict[str, object]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def _server_matches(
    record: dict[str, object],
    *,
    challenge_id: str | None = None,
    run_id: str | None = None,
    lease_id: str | None = None,
    server_id: str | None = None,
) -> bool:
    if challenge_id and record.get("challenge_id") != challenge_id:
        return False
    if run_id and record.get("run_id") != run_id:
        return False
    if lease_id and record.get("lease_id") != lease_id:
        return False
    if server_id and record.get("server_id") != server_id:
        return False
    return True


class DreamhackPlatformAdapter(PlatformAdapter):
    name = "dreamhack"

    def discover_challenges(
        self,
        *,
        platform: str,
        event: str,
        source: str | None = None,
        live: bool = False,
        base_url: str | None = None,
        profile: str | None = None,
    ) -> list[dict[str, object]]:
        if live:
            raise PlatformAdapterError("dreamhack_live_discovery_unsupported")
        path = _require_fixture_source(source)
        items = _load_fixture_items(path)
        return [_normalize_challenge(platform, event, item, index) for index, item in enumerate(items, start=1)]

    def get_challenge_detail(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        source: str | None = None,
        url: str | None = None,
        live: bool = False,
        base_url: str | None = None,
        profile: str | None = None,
    ) -> dict[str, object]:
        if live or _is_url(source) or _is_url(url):
            raise PlatformAdapterError("dreamhack_live_detail_unsupported")
        path = _require_fixture_source(source or url)
        item = _find_item(path, platform, event, challenge_id)
        return {
            **_normalize_challenge(platform, event, item, 1),
            "description": str(_first_value(item, "description", "content") or ""),
            "connection_info": str(_first_value(item, "connection_info", "server", "connection") or ""),
            "hints": item.get("hints") if isinstance(item.get("hints"), list) else [],
            "state": str(_first_value(item, "state", "status") or ""),
        }

    def download_files(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        dest: Path,
        source: str | None = None,
        url: str | None = None,
        live: bool = False,
        base_url: str | None = None,
        profile: str | None = None,
    ) -> list[dict[str, object]]:
        if live or _is_url(source) or _is_url(url):
            raise PlatformAdapterError("dreamhack_live_download_unsupported")
        fixture = _require_fixture_source(source or url)
        item = _find_item(fixture, platform, event, challenge_id)
        entries = _download_entries(fixture, item)
        if not entries:
            raise PlatformAdapterError("challenge_files_not_found")
        dest.mkdir(parents=True, exist_ok=True)
        return [_copy_file(source_path, dest, relative_name) for source_path, relative_name in entries]

    def resolve_vm_auth(
        self,
        *,
        session_id: str | None = None,
        csrf_value: str | None = None,
        session_id_file: str | None = None,
        csrf_value_file: str | None = None,
    ) -> tuple[str, str]:
        resolved_session = str(session_id or "").strip()
        resolved_csrf = str(csrf_value or "").strip()
        if not resolved_session:
            resolved_session = _env_value("CTF_DREAMHACK_SESSION_ID", "DREAMHACK_SESSION_ID")
        if not resolved_csrf:
            resolved_csrf = _env_value("CTF_DREAMHACK_CSRF_TOKEN", "CTF_DREAMHACK_CSRF", "DREAMHACK_CSRF_TOKEN")
        if not resolved_session and session_id_file:
            resolved_session = _read_auth_file(session_id_file, "session")
        if not resolved_csrf and csrf_value_file:
            resolved_csrf = _read_auth_file(csrf_value_file, "csrf")
        if not resolved_session or not resolved_csrf:
            raise PlatformAdapterError("dreamhack_auth_required")
        return resolved_session, resolved_csrf

    def control_vm(
        self,
        *,
        action: str,
        challenge_id: str,
        live: bool = False,
        session_id: str | None = None,
        csrf_value: str | None = None,
        session_id_file: str | None = None,
        csrf_value_file: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, object]:
        normalized_action = action.strip().lower()
        if normalized_action not in DREAMHACK_VM_ACTIONS:
            raise PlatformAdapterError("dreamhack_invalid_vm_action")
        if not live:
            raise PlatformAdapterError("dreamhack_live_required")
        resolved_session, resolved_csrf = self.resolve_vm_auth(
            session_id=session_id,
            csrf_value=csrf_value,
            session_id_file=session_id_file,
            csrf_value_file=csrf_value_file,
        )
        status_code, data = _vm_action_live(
            action=normalized_action,
            challenge_id=challenge_id,
            session_id=resolved_session,
            csrf_value=resolved_csrf,
            base_url=base_url,
        )
        return _vm_summary(
            action=normalized_action,
            challenge_id=challenge_id,
            live=True,
            session_id=resolved_session,
            csrf_value=resolved_csrf,
            status_code=status_code,
            data=data,
        )

    def summarize_vm_response(
        self,
        *,
        action: str,
        challenge_id: str,
        status_code: int,
        response: object,
        session_configured: bool = True,
        csrf_configured: bool = True,
    ) -> dict[str, object]:
        return _vm_summary(
            action=action,
            challenge_id=challenge_id,
            live=True,
            session_id="configured" if session_configured else "",
            csrf_value="configured" if csrf_configured else "",
            status_code=status_code,
            data=response,
        )

    def create_server(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        run_id: str,
        lease_id: str,
    ) -> dict[str, object]:
        server_id = f"dreamhack-{uuid.uuid4().hex}"
        record = {
            "schema_version": 1,
            "adapter": self.name,
            "server_id": server_id,
            "platform": platform,
            "event": event,
            "challenge_id": challenge_id,
            "run_id": run_id,
            "lease_id": lease_id,
            "status": "lease_active",
            "vm_state": "live_action_required",
            "created_at": iso_now(),
            "released_at": "",
            "release_reason": "",
        }
        atomic_write_json(_server_path(platform, event, server_id), record)
        return {
            "server_id": server_id,
            "adapter": self.name,
            "status": "lease_active",
            "vm_state": "live_action_required",
            "challenge_id": challenge_id,
            "run_id": run_id,
        }

    def record_vm_action(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        run_id: str,
        lease_id: str,
        summary: dict[str, object],
    ) -> dict[str, object]:
        server_id = f"dreamhack-{uuid.uuid4().hex}"
        record = {
            "schema_version": 1,
            "adapter": self.name,
            "server_id": server_id,
            "platform": platform,
            "event": event,
            "challenge_id": challenge_id,
            "run_id": run_id,
            "lease_id": lease_id,
            "status": "active" if summary.get("ok") else "error",
            "action": summary.get("action"),
            "vm_state": summary.get("vm_state") or "unknown",
            "host": summary.get("host") or "",
            "port": summary.get("port") or None,
            "created_at": iso_now(),
            "released_at": "",
            "release_reason": "",
        }
        errors = validate_public_record(record)
        if errors:
            raise PlatformAdapterError("dreamhack_vm_record_not_public_safe")
        atomic_write_json(_server_path(platform, event, server_id), record)
        return {
            "server_id": server_id,
            "adapter": self.name,
            "status": record["status"],
            "vm_state": record["vm_state"],
            "challenge_id": challenge_id,
            "run_id": run_id,
        }

    def release_server(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str | None = None,
        run_id: str | None = None,
        lease_id: str | None = None,
        server_id: str | None = None,
        reason: str = "manual_release",
    ) -> dict[str, object]:
        released: list[dict[str, object]] = []
        released_at = iso_now()
        for path in _server_files(platform, event):
            record = _read_server(path)
            if not record or not _server_matches(
                record,
                challenge_id=challenge_id,
                run_id=run_id,
                lease_id=lease_id,
                server_id=server_id,
            ):
                continue
            if record.get("status") != "released":
                record["status"] = "released"
                record["released_at"] = released_at
                record["release_reason"] = reason
                atomic_write_json(path, record)
            released.append(
                {
                    "server_id": record.get("server_id"),
                    "challenge_id": record.get("challenge_id"),
                    "run_id": record.get("run_id"),
                    "lease_id": record.get("lease_id"),
                    "status": record.get("status"),
                    "release_reason": record.get("release_reason"),
                }
            )
        return {"ok": True, "released_count": len(released), "released": released}

    def server_status(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str | None = None,
        run_id: str | None = None,
        lease_id: str | None = None,
    ) -> dict[str, object]:
        records: list[dict[str, object]] = []
        for path in _server_files(platform, event):
            record = _read_server(path)
            if not record or not _server_matches(record, challenge_id=challenge_id, run_id=run_id, lease_id=lease_id):
                continue
            records.append(
                {
                    "server_id": record.get("server_id"),
                    "challenge_id": record.get("challenge_id"),
                    "run_id": record.get("run_id"),
                    "lease_id": record.get("lease_id"),
                    "status": record.get("status"),
                    "adapter": record.get("adapter"),
                    "vm_state": record.get("vm_state"),
                    "host": record.get("host") or "",
                    "port": record.get("port") or None,
                    "created_at": record.get("created_at"),
                    "released_at": record.get("released_at"),
                    "release_reason": record.get("release_reason"),
                }
            )
        return {"ok": True, "server_count": len(records), "servers": records}

    def submit_flag(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        flag: str,
        run_id: str | None = None,
    ) -> dict[str, object]:
        raise PlatformAdapterError("dreamhack_submission_not_implemented")
