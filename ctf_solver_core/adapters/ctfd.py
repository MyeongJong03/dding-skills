"""Generic CTFd platform adapter.

The adapter is fixture-first by default. Live CTFd discovery is read-only and
must be explicitly enabled by the caller; it only fetches bounded JSON from the
standard CTFd challenge API and never stores raw responses or auth material.
"""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import tempfile
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from ..browser_state import check_browser_profile
from ..paths import is_inside_repo, resolve_path
from ..platform_adapters import PlatformAdapter, PlatformAdapterError
from ..schemas import CATEGORIES, read_json, slugify

CTFD_LIVE_MAX_BYTES = 1024 * 1024
CTFD_LIVE_MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
CTFD_LIVE_TIMEOUT_SECONDS = 10
CTFD_LIVE_MAX_DESCRIPTION = 4096


def _is_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _live_requested(source: str | None, url: str | None = None) -> bool:
    return _is_url(source) or _is_url(url)


def _require_fixture_source(source: str | None) -> Path:
    if not source:
        raise PlatformAdapterError("source_required")
    if _is_url(source):
        raise PlatformAdapterError("ctfd_live_mode_requires_opt_in")
    path = resolve_path(source)
    if not path.is_file():
        raise PlatformAdapterError("source_not_found")
    return path


def _live_base_url(source: str | None, base_url: str | None = None) -> str:
    candidate = str(base_url or source or "").strip()
    if not candidate:
        raise PlatformAdapterError("base_url_missing")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PlatformAdapterError("base_url_missing")
    if parsed.username or parsed.password:
        raise PlatformAdapterError("base_url_must_not_include_userinfo")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _api_url(base_url: str, challenge_id: str | None = None) -> str:
    parsed = urlparse(_live_base_url(base_url))
    root_path = parsed.path.rstrip("/")
    if root_path.endswith("/api/v1/challenges"):
        api_path = root_path
    elif "/api/v1/challenges/" in root_path:
        api_path = root_path.split("/api/v1/challenges/", 1)[0] + "/api/v1/challenges"
    elif root_path.endswith("/api/v1"):
        api_path = root_path + "/challenges"
    else:
        api_path = root_path + "/api/v1/challenges"
    if challenge_id is not None:
        api_path = api_path.rstrip("/") + "/" + quote(str(challenge_id).strip(), safe="")
    return urlunparse((parsed.scheme, parsed.netloc, api_path, "", "", ""))


def _safe_url_without_query(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _url_origin(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    return parsed.scheme, parsed.netloc


def _host_is_local_or_private(host: str | None) -> bool:
    if not host:
        return True
    lowered = host.strip().lower().strip("[]")
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return bool(
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _safe_file_label(value: str, fallback: str = "attachment.bin") -> str:
    parsed = urlparse(value)
    source = parsed.path if (parsed.scheme or parsed.netloc or parsed.query) else value
    name = Path(unquote(source)).name.strip()
    if not name or name in {".", ".."}:
        return fallback
    return name


def _validate_output_name(name: str) -> str:
    decoded = unquote(str(name or "")).strip().replace("\\", "/")
    path = Path(decoded)
    if path.is_absolute() or ".." in path.parts:
        raise PlatformAdapterError("ctfd_download_suspicious_filename")
    safe = path.name
    if not safe or safe in {".", ".."}:
        raise PlatformAdapterError("ctfd_download_suspicious_filename")
    return safe


def _validate_url_path(raw: str) -> None:
    parsed = urlparse(raw)
    path = parsed.path if (parsed.scheme or parsed.netloc) else raw
    parts = [part for part in unquote(path).replace("\\", "/").split("/") if part]
    if any(part == ".." for part in parts):
        raise PlatformAdapterError("ctfd_download_suspicious_file_path")


def _resolve_live_file_url(base_url: str, raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise PlatformAdapterError("ctfd_download_file_url_missing")
    parsed = urlparse(value)
    if parsed.scheme == "file":
        raise PlatformAdapterError("ctfd_download_url_scheme_blocked")
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise PlatformAdapterError("ctfd_download_url_scheme_blocked")
    _validate_url_path(value)

    root = _live_base_url(base_url)
    if parsed.scheme:
        resolved = value
    elif value.startswith("/"):
        resolved = urljoin(root.rstrip("/") + "/", value)
    else:
        resolved = urljoin(root.rstrip("/") + "/", value)

    resolved_parsed = urlparse(resolved)
    if resolved_parsed.scheme not in {"http", "https"} or not resolved_parsed.netloc:
        raise PlatformAdapterError("ctfd_download_url_invalid")

    base_parsed = urlparse(root)
    target_private = _host_is_local_or_private(resolved_parsed.hostname)
    base_private = _host_is_local_or_private(base_parsed.hostname)
    same_origin = _url_origin(resolved) == _url_origin(root)
    if target_private and not (base_private and same_origin):
        raise PlatformAdapterError("ctfd_download_private_host_blocked")
    return resolved


def _read_cookie_file(path_value: str) -> str:
    path = resolve_path(path_value)
    if is_inside_repo(path):
        raise PlatformAdapterError("ctfd_cookie_file_inside_repo")
    if not path.is_file():
        raise PlatformAdapterError("ctfd_cookie_file_not_found")
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _cookie_header() -> str:
    header = os.environ.get("CTF_CTFD_COOKIE_HEADER", "").strip()
    if header:
        return header
    cookie_file = os.environ.get("CTF_CTFD_COOKIE_FILE", "").strip()
    if cookie_file:
        return _read_cookie_file(cookie_file)
    return ""


def _profile_configured(platform: str, event: str, profile: str | None) -> bool:
    if not profile:
        return False
    checked = check_browser_profile(platform, event, profile)
    return bool(checked.get("ok"))


def _auth_available(platform: str, event: str, profile: str | None) -> bool:
    return bool(_cookie_header() or _profile_configured(platform, event, profile))


def _live_headers(platform: str, event: str, profile: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "ctf-solver/ctfd-readonly-discovery",
    }
    cookie = _cookie_header()
    if cookie:
        headers["Cookie"] = cookie
    elif profile and not _profile_configured(platform, event, profile):
        raise PlatformAdapterError("auth_required_or_profile_missing")
    return headers


def _http_json(url: str, *, platform: str, event: str, profile: str | None = None) -> object:
    request = Request(_safe_url_without_query(url), headers=_live_headers(platform, event, profile), method="GET")
    try:
        with urlopen(request, timeout=CTFD_LIVE_TIMEOUT_SECONDS) as response:
            body = response.read(CTFD_LIVE_MAX_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            if _auth_available(platform, event, profile):
                raise PlatformAdapterError("ctfd_live_auth_failed") from exc
            raise PlatformAdapterError("auth_required_or_profile_missing") from exc
        raise PlatformAdapterError("ctfd_api_error") from exc
    except (TimeoutError, SocketTimeout) as exc:
        raise PlatformAdapterError("network_timeout") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", "")
        if isinstance(reason, (TimeoutError, SocketTimeout)) or "timed out" in str(reason).lower():
            raise PlatformAdapterError("network_timeout") from exc
        raise PlatformAdapterError("network_error") from exc
    if len(body) > CTFD_LIVE_MAX_BYTES:
        raise PlatformAdapterError("ctfd_live_response_too_large")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlatformAdapterError("ctfd_live_non_json_response") from exc


def _ensure_api_success(data: object) -> None:
    if isinstance(data, dict) and data.get("success") is False:
        raise PlatformAdapterError("ctfd_api_error")


def _normalize_category(value: object) -> str:
    category = str(value or "unknown").strip().lower()
    return category if category in CATEGORIES else "unknown"


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


def _tags(raw: object) -> list[str]:
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


def _file_name(raw: object) -> str | None:
    if isinstance(raw, str):
        return _safe_file_label(raw)
    if isinstance(raw, dict):
        value = raw.get("name") or raw.get("path") or raw.get("source") or raw.get("url")
        if value:
            return _safe_file_label(str(value))
    return None


def _files(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    files: list[str] = []
    for item in raw:
        value = _file_name(item)
        if value:
            files.append(value)
    return files


def _raw_file_lists(item: dict[str, object]) -> list[object]:
    entries: list[object] = []
    for key in ("files", "attachments"):
        raw = item.get(key)
        if isinstance(raw, list):
            entries.extend(raw)
    return entries


def _item_files(item: dict[str, object]) -> list[str]:
    files: list[str] = []
    for raw in _raw_file_lists(item):
        value = _file_name(raw)
        if value:
            files.append(value)
    return files


def _unwrap_discovery(data: object) -> list[dict[str, object]]:
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return [item for item in data["data"] if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("challenges"), list):
        return [item for item in data["challenges"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _unwrap_detail(data: object) -> dict[str, object] | None:
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]  # type: ignore[return-value]
    if isinstance(data, dict) and any(key in data for key in ("name", "category", "description", "files")):
        return data
    return None


def _bounded_text(value: object, limit: int = CTFD_LIVE_MAX_DESCRIPTION) -> str:
    text = str(value or "")
    text = "".join(char if char in "\n\r\t" or ord(char) >= 32 else " " for char in text)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _challenge_id(event: str, category: str, name: str, external_id: str) -> str:
    identifier = name or (f"id-{external_id}" if external_id else "challenge")
    return "/".join(
        [
            "ctfd",
            slugify(event, fallback="event", max_length=48),
            slugify(category, fallback="unknown", max_length=24),
            slugify(identifier, fallback="challenge", max_length=72),
        ]
    )


def _normalize_challenge(platform: str, event: str, item: dict[str, object], index: int) -> dict[str, object]:
    external_id = str(item.get("id") or item.get("external_id") or item.get("challenge_id") or "")
    name = str(
        item.get("name")
        or item.get("title")
        or (f"challenge-{external_id}" if external_id else f"challenge-{index}")
    )
    category = _normalize_category(item.get("category"))
    challenge_id = str(item.get("challenge_id") or "")
    if not challenge_id:
        challenge_id = _challenge_id(event, category, name, external_id)
    normalized: dict[str, object] = {
        "challenge_id": challenge_id,
        "external_id": external_id,
        "name": name,
        "category": category,
        "platform": platform,
        "event": event,
        "remote_required": _bool(item.get("remote_required"), bool(item.get("connection_info"))),
        "local_capable": _bool(item.get("local_capable"), True),
    }
    url = str(item.get("url") or "").strip()
    if url:
        normalized["url"] = url
    value = _int(item.get("value"))
    if value is not None:
        normalized["value"] = value
    solves = _int(item.get("solves"))
    if solves is not None:
        normalized["solves"] = solves
    tags = _tags(item.get("tags"))
    if tags:
        normalized["tags"] = tags
    files = _item_files(item)
    if files:
        normalized["files"] = files
    return normalized


def _normalize_live_challenges(
    platform: str,
    event: str,
    data: object,
    *,
    base_url: str,
) -> list[dict[str, object]]:
    _ensure_api_success(data)
    items = _unwrap_discovery(data)
    challenges: list[dict[str, object]] = []
    for index, item in enumerate(items, start=1):
        normalized = _normalize_challenge(platform, event, item, index)
        external_id = str(normalized.get("external_id") or "")
        if external_id and not normalized.get("url"):
            normalized["url"] = _api_url(base_url, external_id)
        challenges.append(normalized)
    return challenges


def _normalize_live_detail(
    platform: str,
    event: str,
    data: object,
    *,
    base_url: str,
    fallback_challenge_id: str,
) -> dict[str, object]:
    _ensure_api_success(data)
    item = _unwrap_detail(data)
    if item is None:
        raise PlatformAdapterError("challenge_detail_not_found")
    normalized = _normalize_challenge(platform, event, item, 1)
    if not normalized.get("external_id"):
        normalized["external_id"] = fallback_challenge_id
    if not normalized.get("url"):
        normalized["url"] = _api_url(base_url, str(normalized.get("external_id") or fallback_challenge_id))
    return {
        **normalized,
        "description": _bounded_text(item.get("description")),
        "connection_info": _bounded_text(item.get("connection_info"), 1024),
        "hints": item.get("hints") if isinstance(item.get("hints"), list) else [],
        "state": str(item.get("state") or ""),
    }


class _CTFdHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag not in {"a", "button", "div"}:
            return
        challenge_id = data.get("data-challenge-id") or data.get("data-id") or data.get("value")
        name = data.get("data-name") or data.get("aria-label") or data.get("title")
        if not challenge_id and not name:
            return
        item: dict[str, object] = {
            "id": challenge_id or "",
            "name": name or (challenge_id or "challenge"),
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


def _load_fixture_items(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".json":
        return _unwrap_discovery(read_json(path, default={}))
    parser = _CTFdHTMLParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.items


def _find_item(path: Path, platform: str, event: str, challenge_id: str) -> dict[str, object]:
    if path.suffix.lower() == ".json":
        data = read_json(path, default={})
        detail = _unwrap_detail(data)
        if detail is not None:
            normalized = _normalize_challenge(platform, event, detail, 1)
            if challenge_id in {
                str(normalized.get("challenge_id") or ""),
                str(normalized.get("external_id") or ""),
                str(detail.get("id") or ""),
                str(detail.get("name") or ""),
            }:
                return detail
            raise PlatformAdapterError("challenge_detail_not_found")
        items = _unwrap_discovery(data)
    else:
        items = _load_fixture_items(path)

    for index, item in enumerate(items, start=1):
        normalized = _normalize_challenge(platform, event, item, index)
        if challenge_id in {
            str(normalized.get("challenge_id") or ""),
            str(normalized.get("external_id") or ""),
            str(item.get("id") or ""),
            str(item.get("name") or ""),
        }:
            return item
    raise PlatformAdapterError("challenge_detail_not_found")


def _local_source_path(fixture: Path, raw: str) -> Path:
    if _is_url(raw):
        raise PlatformAdapterError("ctfd_fixture_file_requires_local_path")
    path = Path(raw).expanduser()
    if path.is_absolute() and path.is_file():
        return path.resolve()
    return (fixture.parent / raw.lstrip("/")).resolve()


def _download_entries(fixture: Path, item: dict[str, object]) -> list[tuple[Path, str]]:
    raw_files = item.get("files") if isinstance(item.get("files"), list) else []
    entries: list[tuple[Path, str]] = []
    for raw in raw_files:
        if isinstance(raw, str):
            name = Path(raw).name if raw.startswith("/") else raw
            entries.append((_local_source_path(fixture, raw), name))
        elif isinstance(raw, dict):
            value = raw.get("path") or raw.get("source") or raw.get("url")
            if not value:
                continue
            name = str(raw.get("name") or Path(str(value)).name)
            entries.append((_local_source_path(fixture, str(value)), name))
    return entries


def _live_download_entries(base_url: str, item: dict[str, object]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    used_names: set[str] = set()
    for raw in _raw_file_lists(item):
        if isinstance(raw, str):
            file_url = _resolve_live_file_url(base_url, raw)
            name = _validate_output_name(_safe_file_label(raw))
        elif isinstance(raw, dict):
            value = raw.get("url") or raw.get("path") or raw.get("source") or raw.get("href")
            if not value:
                continue
            file_url = _resolve_live_file_url(base_url, str(value))
            if raw.get("name"):
                name = _validate_output_name(str(raw.get("name") or ""))
            else:
                name = _validate_output_name(_safe_file_label(str(value)))
        else:
            continue
        stem = Path(name).stem or "attachment"
        suffix = Path(name).suffix
        candidate = name
        counter = 2
        while candidate in used_names:
            candidate = f"{stem}-{counter}{suffix}"
            counter += 1
        used_names.add(candidate)
        entries.append((file_url, candidate))
    return entries


def _download_live_file(
    url: str,
    dest_root: Path,
    relative_name: str,
    *,
    platform: str,
    event: str,
    profile: str | None,
) -> dict[str, object]:
    relative = Path(_validate_output_name(relative_name))
    destination = dest_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers=_live_headers(platform, event, profile), method="GET")
    digest = hashlib.sha256()
    total = 0
    tmp_path: Path | None = None
    completed = False
    try:
        with urlopen(request, timeout=CTFD_LIVE_TIMEOUT_SECONDS) as response:
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > CTFD_LIVE_MAX_DOWNLOAD_BYTES:
                        raise PlatformAdapterError("ctfd_download_too_large")
                except ValueError:
                    pass
            with tempfile.NamedTemporaryFile(
                "wb",
                dir=str(destination.parent),
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                tmp_path = Path(handle.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > CTFD_LIVE_MAX_DOWNLOAD_BYTES:
                        raise PlatformAdapterError("ctfd_download_too_large")
                    digest.update(chunk)
                    handle.write(chunk)
                completed = True
    except HTTPError as exc:
        if exc.code in {401, 403}:
            if _auth_available(platform, event, profile):
                raise PlatformAdapterError("ctfd_live_auth_failed") from exc
            raise PlatformAdapterError("auth_required_or_profile_missing") from exc
        raise PlatformAdapterError("ctfd_download_http_error") from exc
    except (TimeoutError, SocketTimeout) as exc:
        raise PlatformAdapterError("network_timeout") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", "")
        if isinstance(reason, (TimeoutError, SocketTimeout)) or "timed out" in str(reason).lower():
            raise PlatformAdapterError("network_timeout") from exc
        raise PlatformAdapterError("network_error") from exc
    finally:
        if tmp_path and tmp_path.exists() and not completed:
            tmp_path.unlink(missing_ok=True)
    if tmp_path is None:
        raise PlatformAdapterError("ctfd_download_failed")
    tmp_path.replace(destination)
    return {
        "name": destination.name,
        "relative_path": destination.relative_to(dest_root).as_posix(),
        "size": total,
        "sha256": digest.hexdigest(),
    }


def _copy_file(source: Path, dest_root: Path, relative_name: str) -> dict[str, object]:
    from ..platform_adapters import _copy_file as copy_file

    return copy_file(source, dest_root, relative_name)


class CTFdPlatformAdapter(PlatformAdapter):
    name = "ctfd"

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
            root = _live_base_url(source, base_url)
            data = _http_json(_api_url(root), platform=platform, event=event, profile=profile)
            return _normalize_live_challenges(platform, event, data, base_url=root)
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
        if live:
            root = _live_base_url(source or url, base_url)
            data = _http_json(_api_url(root, challenge_id), platform=platform, event=event, profile=profile)
            return _normalize_live_detail(
                platform,
                event,
                data,
                base_url=root,
                fallback_challenge_id=challenge_id,
            )
        if _live_requested(source, url):
            raise PlatformAdapterError("ctfd_live_mode_requires_opt_in")
        path = _require_fixture_source(source)
        item = _find_item(path, platform, event, challenge_id)
        normalized = _normalize_challenge(platform, event, item, 1)
        detail: dict[str, object] = {
            **normalized,
            "description": str(item.get("description") or ""),
            "connection_info": str(item.get("connection_info") or ""),
            "hints": item.get("hints") if isinstance(item.get("hints"), list) else [],
            "state": str(item.get("state") or ""),
        }
        return detail

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
        if live:
            root = _live_base_url(source or url, base_url)
            if not challenge_id:
                raise PlatformAdapterError("challenge_id_required_for_download")
            data = _http_json(_api_url(root, challenge_id), platform=platform, event=event, profile=profile)
            _ensure_api_success(data)
            item = _unwrap_detail(data)
            if item is None:
                raise PlatformAdapterError("challenge_detail_not_found")
            entries = _live_download_entries(root, item)
            if not entries:
                raise PlatformAdapterError("challenge_files_not_found")
            dest.mkdir(parents=True, exist_ok=True)
            return [
                _download_live_file(
                    file_url,
                    dest,
                    relative_name,
                    platform=platform,
                    event=event,
                    profile=profile,
                )
                for file_url, relative_name in entries
            ]
        if _live_requested(source, url):
            raise PlatformAdapterError("ctfd_live_mode_requires_opt_in")
        path = _require_fixture_source(source or url)
        item = _find_item(path, platform, event, challenge_id)
        entries = _download_entries(path, item)
        if not entries:
            raise PlatformAdapterError("challenge_files_not_found")
        dest.mkdir(parents=True, exist_ok=True)
        return [_copy_file(source_path, dest, relative_name) for source_path, relative_name in entries]

    def create_server(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        run_id: str,
        lease_id: str,
    ) -> dict[str, object]:
        raise PlatformAdapterError("ctfd_server_provisioning_unsupported")

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
        return {"ok": True, "released_count": 0, "released": [], "reason": "ctfd_server_provisioning_unsupported"}

    def server_status(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str | None = None,
        run_id: str | None = None,
        lease_id: str | None = None,
    ) -> dict[str, object]:
        return {"ok": True, "server_count": 0, "servers": [], "reason": "ctfd_server_provisioning_unsupported"}

    def submit_flag(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        flag: str,
        run_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "ok": True,
            "adapter": self.name,
            "challenge_id": challenge_id,
            "run_id": run_id or "",
            "accepted": False,
            "reason": "ctfd_submit_scaffold_no_live_network",
            "flag_redacted": "<redacted>",
            "flag_length": len(flag),
        }
