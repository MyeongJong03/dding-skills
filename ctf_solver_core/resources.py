"""File-backed leases for remote CTF resources."""

from __future__ import annotations

from pathlib import Path
import os
import socket
import time
import uuid

from .locks import DirectoryLock
from .paths import lease_root
from .platforms import PlatformPolicy
from .schemas import atomic_write_json, iso_now, parse_iso, read_json, validate_public_record


REMOTE_SERVER = "remote_server"
LEASE_SCHEMA_VERSION = 1


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def stale_lease_seconds() -> int:
    raw = os.environ.get("CTF_LEASE_STALE_SECONDS")
    if not raw:
        return 12 * 60 * 60
    try:
        return max(0, int(raw))
    except ValueError:
        return 12 * 60 * 60


def _lease_path(lease_id: str) -> Path:
    return lease_root() / f"{lease_id}.json"


def _read_lease(path: Path) -> dict[str, object] | None:
    data = read_json(path, default={})
    if not isinstance(data, dict) or not data:
        return None
    return data


def _all_lease_paths() -> list[Path]:
    root = lease_root()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def _is_stale(lease: dict[str, object], now: float | None = None) -> bool:
    now = time.time() if now is None else now
    expires_at = parse_iso(str(lease.get("expires_at") or ""))
    if expires_at and expires_at.timestamp() <= now:
        return True
    timeout = stale_lease_seconds()
    if timeout <= 0:
        return False
    acquired_at = parse_iso(str(lease.get("acquired_at") or ""))
    if not acquired_at:
        return False
    return now - acquired_at.timestamp() > timeout


def _public_safe_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    if not metadata:
        return {}
    safe = dict(metadata)
    errors = validate_public_record(safe)
    if errors:
        raise ValueError("lease metadata is not public-safe: " + "; ".join(errors))
    return safe


def _scope_matches(policy: PlatformPolicy, lease: dict[str, object], challenge_id: str, run_id: str) -> bool:
    scope = policy.resources.remote_server.lease_scope
    if lease.get("platform") != policy.platform:
        return False
    if scope in {"event", "challenge", "run"} and lease.get("event") != policy.event:
        return False
    if scope == "challenge" and lease.get("challenge_id") != challenge_id:
        return False
    if scope == "run" and lease.get("run_id") != run_id:
        return False
    return True


def _purge_stale_locked() -> list[str]:
    removed: list[str] = []
    for path in _all_lease_paths():
        lease = _read_lease(path)
        if lease and _is_stale(lease):
            removed.append(str(lease.get("lease_id") or path.stem))
            path.unlink(missing_ok=True)
    return removed


def _active_leases_locked(
    *,
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    role: str | None = None,
) -> list[dict[str, object]]:
    leases: list[dict[str, object]] = []
    for path in _all_lease_paths():
        lease = _read_lease(path)
        if not lease or _is_stale(lease):
            continue
        if platform and lease.get("platform") != platform:
            continue
        if event and lease.get("event") != event:
            continue
        if resource_type and lease.get("resource_type") != resource_type:
            continue
        if role and lease.get("role") != role:
            continue
        leases.append(lease)
    return leases


def list_leases(
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    include_stale: bool = False,
) -> list[dict[str, object]]:
    with DirectoryLock("resource-leases", "list resource leases", wait_seconds=10):
        if not include_stale:
            _purge_stale_locked()
        leases: list[dict[str, object]] = []
        for path in _all_lease_paths():
            lease = _read_lease(path)
            if not lease:
                continue
            if not include_stale and _is_stale(lease):
                continue
            if platform and lease.get("platform") != platform:
                continue
            if event and lease.get("event") != event:
                continue
            if resource_type and lease.get("resource_type") != resource_type:
                continue
            leases.append(lease)
        return leases


def _write_lease(
    *,
    policy: PlatformPolicy,
    challenge_id: str,
    run_id: str,
    worker_id: str,
    mode: str,
    resource_type: str,
    shared: bool,
    metadata: dict[str, object] | None = None,
    primary_lease_id: str | None = None,
    expires_at: str | None = None,
) -> dict[str, object]:
    lease_id = uuid.uuid4().hex
    lease: dict[str, object] = {
        "schema_version": LEASE_SCHEMA_VERSION,
        "lease_id": lease_id,
        "platform": policy.platform,
        "event": policy.event,
        "resource_type": resource_type,
        "challenge_id": challenge_id,
        "run_id": run_id,
        "owner_worker_id": worker_id,
        "role": mode,
        "acquired_at": iso_now(),
        "expires_at": expires_at,
        "shared": shared,
        "metadata": _public_safe_metadata(metadata),
    }
    if primary_lease_id:
        lease["primary_lease_id"] = primary_lease_id
    atomic_write_json(_lease_path(lease_id), lease)
    return lease


def acquire_remote_server(
    policy: PlatformPolicy,
    challenge_id: str,
    run_id: str,
    worker_id: str | None = None,
    mode: str = "primary",
    metadata: dict[str, object] | None = None,
    expires_at: str | None = None,
) -> dict[str, object]:
    worker = worker_id or default_worker_id()
    if mode not in {"primary", "helper"}:
        return {"ok": False, "reason": "invalid_mode", "mode": mode}
    try:
        with DirectoryLock("resource-leases", "acquire remote server lease", wait_seconds=30):
            stale_released = _purge_stale_locked()
            active = _active_leases_locked(
                platform=policy.platform,
                event=policy.event,
                resource_type=REMOTE_SERVER,
            )
            if mode == "helper":
                sharing = policy.resources.remote_server.sharing
                if not sharing.allowed:
                    return {
                        "ok": False,
                        "reason": "sharing_not_allowed",
                        "stale_released": stale_released,
                    }
                primary = [
                    lease
                    for lease in active
                    if lease.get("role") == "primary" and lease.get("challenge_id") == challenge_id
                ]
                if not primary:
                    return {
                        "ok": False,
                        "reason": "no_primary_lease_for_helper",
                        "stale_released": stale_released,
                    }
                primary_lease = primary[0]
                participants = [
                    lease
                    for lease in active
                    if lease.get("challenge_id") == challenge_id
                    and (
                        lease.get("lease_id") == primary_lease.get("lease_id")
                        or lease.get("primary_lease_id") == primary_lease.get("lease_id")
                    )
                ]
                if len(participants) >= sharing.max_workers:
                    return {
                        "ok": False,
                        "reason": "max_workers_reached",
                        "stale_released": stale_released,
                    }
                lease = _write_lease(
                    policy=policy,
                    challenge_id=challenge_id,
                    run_id=run_id,
                    worker_id=worker,
                    mode="helper",
                    resource_type=REMOTE_SERVER,
                    shared=True,
                    metadata=metadata,
                    primary_lease_id=str(primary_lease.get("lease_id")),
                    expires_at=expires_at,
                )
                return {
                    "ok": True,
                    "reason": "acquired",
                    "lease": lease,
                    "stale_released": stale_released,
                }

            existing_same_run = [
                lease
                for lease in active
                if lease.get("role") == "primary"
                and lease.get("run_id") == run_id
                and lease.get("challenge_id") == challenge_id
            ]
            if existing_same_run:
                return {
                    "ok": True,
                    "reason": "already_acquired",
                    "lease": existing_same_run[0],
                    "stale_released": stale_released,
                }

            scoped_primary = [
                lease
                for lease in active
                if lease.get("role") == "primary" and _scope_matches(policy, lease, challenge_id, run_id)
            ]
            max_active = policy.resources.remote_server.max_active_leases
            if max_active >= 0 and len(scoped_primary) >= max_active:
                return {
                    "ok": False,
                    "reason": "max_active_leases_reached",
                    "active_primary_count": len(scoped_primary),
                    "max_active_leases": max_active,
                    "stale_released": stale_released,
                }
            lease = _write_lease(
                policy=policy,
                challenge_id=challenge_id,
                run_id=run_id,
                worker_id=worker,
                mode="primary",
                resource_type=REMOTE_SERVER,
                shared=policy.resources.remote_server.sharing.allowed,
                metadata=metadata,
                expires_at=expires_at,
            )
            return {
                "ok": True,
                "reason": "acquired",
                "lease": lease,
                "stale_released": stale_released,
            }
    except TimeoutError as exc:
        return {"ok": False, "reason": "stale_lock", "error": str(exc)}


def release_lease(
    lease_id: str | None = None,
    run_id: str | None = None,
    platform: str | None = None,
    event: str | None = None,
    include_helpers: bool = True,
) -> dict[str, object]:
    if not lease_id and not run_id:
        return {"ok": False, "reason": "lease_id_or_run_id_required", "released": []}
    try:
        with DirectoryLock("resource-leases", "release resource leases", wait_seconds=30):
            _purge_stale_locked()
            active = _active_leases_locked(platform=platform, event=event)
            targets: set[str] = set()
            for lease in active:
                current_id = str(lease.get("lease_id") or "")
                if lease_id and current_id == lease_id:
                    targets.add(current_id)
                    if include_helpers:
                        for candidate in active:
                            if candidate.get("primary_lease_id") == lease_id:
                                targets.add(str(candidate.get("lease_id") or ""))
                if run_id and lease.get("run_id") == run_id:
                    targets.add(current_id)
                    if include_helpers and lease.get("role") == "primary":
                        primary_id = current_id
                        for candidate in active:
                            if candidate.get("primary_lease_id") == primary_id:
                                targets.add(str(candidate.get("lease_id") or ""))
            released: list[str] = []
            for target in sorted(targets):
                path = _lease_path(target)
                if path.exists():
                    path.unlink()
                    released.append(target)
            return {"ok": True, "reason": "released", "released": released, "released_count": len(released)}
    except TimeoutError as exc:
        return {"ok": False, "reason": "stale_lock", "error": str(exc), "released": []}


def active_primary_count(policy: PlatformPolicy, challenge_id: str = "", run_id: str = "") -> int:
    with DirectoryLock("resource-leases", "count remote server leases", wait_seconds=10):
        _purge_stale_locked()
        return sum(
            1
            for lease in _active_leases_locked(
                platform=policy.platform,
                event=policy.event,
                resource_type=REMOTE_SERVER,
                role="primary",
            )
            if _scope_matches(policy, lease, challenge_id, run_id)
        )
