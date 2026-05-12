"""Local-only browser/session profile metadata helpers."""

from __future__ import annotations

from pathlib import Path

from .locks import DirectoryLock
from .paths import browser_state_root, display_path, is_inside_repo, resolve_path
from .schemas import atomic_write_json, iso_now, read_json, slugify


BROWSER_STATE_SCHEMA_VERSION = 1


class BrowserStateError(ValueError):
    """Raised when browser profile metadata would violate local-only policy."""


def _profile_path(platform: str, event: str, profile_name: str) -> Path:
    platform_slug = slugify(platform, fallback="platform", max_length=64)
    event_slug = slugify(event, fallback="event", max_length=80)
    profile_slug = slugify(profile_name, fallback="profile", max_length=96)
    return browser_state_root() / platform_slug / event_slug / f"{profile_slug}.json"


def profile_metadata_path(platform: str, event: str, profile_name: str) -> Path:
    return _profile_path(platform, event, profile_name)


def _storage_state_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = resolve_path(value)
    if is_inside_repo(path):
        raise BrowserStateError("storage_state_path_inside_repo")
    if not path.is_file():
        raise BrowserStateError("storage_state_path_not_found")
    return path


def register_browser_profile(
    *,
    platform: str,
    event: str,
    profile_name: str,
    storage_state_path: str | Path | None = None,
    notes: str = "",
) -> dict[str, object]:
    """Create or replace local-only browser profile metadata.

    This helper never reads the storage state contents. It only validates that
    an optional path exists and is outside the repository.
    """

    storage_path = _storage_state_path(storage_state_path)
    metadata = {
        "schema_version": BROWSER_STATE_SCHEMA_VERSION,
        "platform": platform,
        "event": event,
        "profile_name": profile_name,
        "storage_state_path": str(storage_path) if storage_path else "",
        "created_at": iso_now(),
        "notes": notes,
    }
    path = _profile_path(platform, event, profile_name)
    with DirectoryLock("browser-state", "register browser state profile", wait_seconds=30):
        atomic_write_json(path, metadata)
    return {
        "ok": True,
        "profile": metadata,
        "profile_path": str(path),
    }


def load_browser_profile(platform: str, event: str, profile_name: str) -> dict[str, object] | None:
    path = _profile_path(platform, event, profile_name)
    data = read_json(path, default={})
    if not isinstance(data, dict) or not data:
        return None
    return data


def check_browser_profile(platform: str, event: str, profile_name: str) -> dict[str, object]:
    path = _profile_path(platform, event, profile_name)
    data = load_browser_profile(platform, event, profile_name)
    exists = bool(data)
    storage_value = str((data or {}).get("storage_state_path") or "")
    storage_exists = False
    storage_configured = bool(storage_value)
    if storage_configured:
        # Do not open or parse the file. Existence is the only check.
        storage_exists = Path(storage_value).expanduser().is_file()
    return {
        "ok": exists and (not storage_configured or storage_exists),
        "exists": exists,
        "platform": platform,
        "event": event,
        "profile_name": profile_name,
        "profile_path": str(path),
        "storage_state_configured": storage_configured,
        "storage_state_exists": storage_exists,
    }


def profile_summary(result: dict[str, object]) -> dict[str, object]:
    """Return a display-safe summary without storage state contents."""

    profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
    raw_path = str(result.get("profile_path") or "")
    storage_configured = bool(profile.get("storage_state_path")) if isinstance(profile, dict) else False
    return {
        "ok": bool(result.get("ok")),
        "platform": str(profile.get("platform") or result.get("platform") or ""),
        "event": str(profile.get("event") or result.get("event") or ""),
        "profile_name": str(profile.get("profile_name") or result.get("profile_name") or ""),
        "created_at": str(profile.get("created_at") or ""),
        "storage_state_configured": storage_configured,
        "profile_path": display_path(Path(raw_path)) if raw_path else "",
    }


def browser_profile_count() -> int:
    root = browser_state_root()
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("*.json") if path.is_file())
