"""Generic CTFd platform adapter.

The adapter is intentionally fixture-first. Live CTFd access is reserved for an
explicit manual phase and is blocked unless the caller opts in through an
environment variable; even then this module returns a clear scaffold error
instead of making network requests.
"""

from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
from urllib.parse import urlparse

from ..paths import resolve_path
from ..platform_adapters import PlatformAdapter, PlatformAdapterError
from ..schemas import CATEGORIES, read_json, slugify


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
        if os.environ.get("CTF_CTFD_LIVE") == "1":
            raise PlatformAdapterError("ctfd_live_network_not_implemented")
        raise PlatformAdapterError("ctfd_live_mode_requires_opt_in")
    path = resolve_path(source)
    if not path.is_file():
        raise PlatformAdapterError("source_not_found")
    return path


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
        return raw
    if isinstance(raw, dict):
        value = raw.get("name") or raw.get("path") or raw.get("source") or raw.get("url")
        if value:
            return str(value)
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
    value = item.get("value")
    if isinstance(value, int):
        normalized["value"] = value
    tags = _tags(item.get("tags"))
    if tags:
        normalized["tags"] = tags
    files = _files(item.get("files"))
    if files:
        normalized["files"] = files
    return normalized


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


def _copy_file(source: Path, dest_root: Path, relative_name: str) -> dict[str, object]:
    from ..platform_adapters import _copy_file as copy_file

    return copy_file(source, dest_root, relative_name)


class CTFdPlatformAdapter(PlatformAdapter):
    name = "ctfd"

    def discover_challenges(self, *, platform: str, event: str, source: str | None = None) -> list[dict[str, object]]:
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
    ) -> dict[str, object]:
        if _live_requested(source, url):
            if os.environ.get("CTF_CTFD_LIVE") == "1":
                raise PlatformAdapterError("ctfd_live_network_not_implemented")
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
    ) -> list[dict[str, object]]:
        if _live_requested(source, url):
            if os.environ.get("CTF_CTFD_LIVE") == "1":
                raise PlatformAdapterError("ctfd_live_network_not_implemented")
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
