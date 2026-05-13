"""Adapter interfaces for future CTF platform automation."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import shutil
import uuid
from urllib.parse import urlparse

from .paths import platform_automation_root, resolve_path
from .schemas import CATEGORIES, atomic_write_json, iso_now, read_json, slugify


class PlatformAdapterError(RuntimeError):
    """Raised when a platform adapter cannot perform an action safely."""


@dataclass(frozen=True)
class Challenge:
    challenge_id: str
    name: str
    category: str
    url: str = ""
    files: tuple[str, ...] = ()
    remote_required: bool = False
    local_capable: bool = True

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "challenge_id": self.challenge_id,
            "name": self.name,
            "category": self.category,
            "remote_required": self.remote_required,
            "local_capable": self.local_capable,
        }
        if self.url:
            data["url"] = self.url
        if self.files:
            data["files"] = list(self.files)
        return data


class PlatformAdapter:
    name = "generic"

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
        raise PlatformAdapterError("adapter_not_implemented")

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
        raise PlatformAdapterError("adapter_not_implemented")

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
        raise PlatformAdapterError("adapter_not_implemented")

    def create_server(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        run_id: str,
        lease_id: str,
    ) -> dict[str, object]:
        raise PlatformAdapterError("adapter_not_implemented")

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
        raise PlatformAdapterError("adapter_not_implemented")

    def server_status(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str | None = None,
        run_id: str | None = None,
        lease_id: str | None = None,
    ) -> dict[str, object]:
        raise PlatformAdapterError("adapter_not_implemented")

    def submit_flag(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        flag: str,
        run_id: str | None = None,
    ) -> dict[str, object]:
        raise PlatformAdapterError("adapter_not_implemented")


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


def _normalize_category(value: object) -> str:
    category = str(value or "unknown").strip().lower()
    return category if category in CATEGORIES else "unknown"


def _challenge_from_dict(platform: str, event: str, item: dict[str, object], index: int) -> dict[str, object]:
    name = str(item.get("name") or item.get("title") or item.get("challenge_name") or f"challenge-{index}")
    challenge_id = str(item.get("challenge_id") or item.get("id") or "")
    if not challenge_id:
        challenge_id = "-".join(
            [
                slugify(platform, fallback="platform", max_length=24),
                slugify(event, fallback="event", max_length=32),
                slugify(name, fallback="challenge", max_length=48),
            ]
        )
    raw_files = item.get("files") if isinstance(item.get("files"), list) else []
    files: list[str] = []
    for entry in raw_files:
        if isinstance(entry, str):
            files.append(entry)
        elif isinstance(entry, dict):
            value = entry.get("path") or entry.get("source") or entry.get("name")
            if value:
                files.append(str(value))
    return Challenge(
        challenge_id=challenge_id,
        name=name,
        category=_normalize_category(item.get("category")),
        url=str(item.get("url") or ""),
        files=tuple(files),
        remote_required=_bool(item.get("remote_required"), False),
        local_capable=_bool(item.get("local_capable"), True),
    ).to_dict()


class _ChallengeHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        challenge_id = data.get("data-challenge-id") or data.get("data-id")
        name = data.get("data-name") or data.get("title")
        if not challenge_id and not name:
            return
        item: dict[str, object] = {
            "challenge_id": challenge_id or "",
            "name": name or challenge_id or "challenge",
            "category": data.get("data-category") or "unknown",
            "url": data.get("href") if tag == "a" else data.get("data-url", ""),
            "remote_required": data.get("data-remote-required", "false"),
            "local_capable": data.get("data-local-capable", "true"),
        }
        files = data.get("data-files")
        if files:
            item["files"] = [part.strip() for part in files.split(",") if part.strip()]
        self.items.append(item)


def _load_discovery_source(platform: str, event: str, source: str | None) -> list[dict[str, object]]:
    if not source:
        raise PlatformAdapterError("source_required")
    if _is_url(source):
        raise PlatformAdapterError("mock_adapter_requires_local_source")
    path = resolve_path(source)
    if not path.is_file():
        raise PlatformAdapterError("source_not_found")
    if path.suffix.lower() == ".json":
        data = read_json(path, default={})
        raw_items: list[object]
        if isinstance(data, dict) and isinstance(data.get("challenges"), list):
            raw_items = list(data["challenges"])
        elif isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            raw_items = [value for value in data.values() if isinstance(value, dict)]
        else:
            raw_items = []
        return [
            _challenge_from_dict(platform, event, item, index)
            for index, item in enumerate(raw_items, start=1)
            if isinstance(item, dict)
        ]

    parser = _ChallengeHTMLParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return [
        _challenge_from_dict(platform, event, item, index)
        for index, item in enumerate(parser.items, start=1)
    ]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_file(source: Path, dest_root: Path, relative_name: str | None = None) -> dict[str, object]:
    if not source.is_file():
        raise PlatformAdapterError("download_source_file_not_found")
    relative = Path(relative_name or source.name)
    if relative.is_absolute() or ".." in relative.parts:
        relative = Path(source.name)
    destination = dest_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    size = destination.stat().st_size
    return {
        "name": destination.name,
        "relative_path": destination.relative_to(dest_root).as_posix(),
        "size": size,
        "sha256": _hash_file(destination),
    }


def _download_sources_from_json(source: Path, challenge_id: str) -> list[tuple[Path, str | None]]:
    data = read_json(source, default={})
    if not isinstance(data, dict):
        return []
    raw_items = data.get("challenges") if isinstance(data.get("challenges"), list) else []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("challenge_id") or item.get("id") or "") != challenge_id:
            continue
        files = item.get("files") if isinstance(item.get("files"), list) else []
        results: list[tuple[Path, str | None]] = []
        for entry in files:
            if isinstance(entry, str):
                results.append(((source.parent / entry).resolve(), entry))
            elif isinstance(entry, dict):
                raw = entry.get("path") or entry.get("source")
                if not raw:
                    continue
                name = str(entry.get("name") or raw)
                results.append(((source.parent / str(raw)).resolve(), name))
        return results
    return []


def _download_source_files(source: str | None, challenge_id: str) -> list[tuple[Path, str | None]]:
    if not source:
        raise PlatformAdapterError("source_required")
    if _is_url(source):
        raise PlatformAdapterError("mock_adapter_requires_local_source")
    path = resolve_path(source)
    if path.is_file() and path.suffix.lower() == ".json":
        files = _download_sources_from_json(path, challenge_id)
        if files:
            return files
        raise PlatformAdapterError("challenge_files_not_found")
    if path.is_file():
        return [(path, path.name)]
    if path.is_dir():
        challenge_dir = path / challenge_id
        root = challenge_dir if challenge_dir.is_dir() else path
        return [(item, item.relative_to(root).as_posix()) for item in sorted(root.rglob("*")) if item.is_file()]
    raise PlatformAdapterError("source_not_found")


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
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


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


class MockPlatformAdapter(PlatformAdapter):
    name = "mock"

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
        return _load_discovery_source(platform, event, source)

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
        if url and _is_url(url):
            raise PlatformAdapterError("mock_adapter_does_not_fetch_network")
        files = _download_source_files(source or url, challenge_id)
        dest.mkdir(parents=True, exist_ok=True)
        return [_copy_file(source_path, dest, relative_name) for source_path, relative_name in files]

    def create_server(
        self,
        *,
        platform: str,
        event: str,
        challenge_id: str,
        run_id: str,
        lease_id: str,
    ) -> dict[str, object]:
        server_id = uuid.uuid4().hex
        record = {
            "schema_version": 1,
            "adapter": self.name,
            "server_id": server_id,
            "platform": platform,
            "event": event,
            "challenge_id": challenge_id,
            "run_id": run_id,
            "lease_id": lease_id,
            "status": "active",
            "created_at": iso_now(),
            "released_at": "",
            "release_reason": "",
        }
        atomic_write_json(_server_path(platform, event, server_id), record)
        return {
            "server_id": server_id,
            "adapter": self.name,
            "status": "active",
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
        return {
            "ok": True,
            "adapter": self.name,
            "challenge_id": challenge_id,
            "run_id": run_id or "",
            "accepted": True,
            "flag_redacted": "<redacted>",
            "flag_length": len(flag),
        }


def get_adapter(name: str | None) -> PlatformAdapter:
    adapter_name = (name or "generic").strip().lower()
    if adapter_name in {"mock", "local"}:
        return MockPlatformAdapter()
    if adapter_name == "ctfd":
        from .adapters.ctfd import CTFdPlatformAdapter

        return CTFdPlatformAdapter()
    if adapter_name == "generic":
        return PlatformAdapter()
    raise PlatformAdapterError(f"unsupported_adapter:{adapter_name}")


def mock_server_record_count() -> int:
    root = platform_automation_root()
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("servers/*.json") if path.is_file())
