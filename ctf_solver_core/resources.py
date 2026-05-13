"""File-backed leases for remote CTF resources."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import os
import socket
import time
import uuid

from .locks import DirectoryLock
from .paths import lease_root
from .platforms import PlatformPolicy
from .schemas import atomic_write_json, iso_now, parse_iso, read_json, utc_now, validate_public_record


REMOTE_SERVER = "remote_server"
LEASE_SCHEMA_VERSION = 1
DEFAULT_HEARTBEAT_INTERVAL_SEC = 30
DEFAULT_STALE_AFTER_SEC = 180
STALE_RELEASE_REASON = "stale_reclaimed"


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def default_heartbeat_interval_sec() -> int:
    return _env_int("CTF_LEASE_HEARTBEAT_INTERVAL_SEC", DEFAULT_HEARTBEAT_INTERVAL_SEC)


def default_stale_after_sec() -> int:
    return _env_int(
        "CTF_LEASE_STALE_AFTER_SEC",
        _env_int("CTF_LEASE_STALE_SECONDS", DEFAULT_STALE_AFTER_SEC),
    )


def stale_lease_seconds() -> int:
    return default_stale_after_sec()


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


def _seconds_field(lease: dict[str, object], key: str, default: int) -> int:
    try:
        return max(0, int(lease.get(key) or default))
    except (TypeError, ValueError):
        return default


def _normalize_lease(lease: dict[str, object]) -> dict[str, object]:
    normalized = dict(lease)
    normalized.setdefault("schema_version", LEASE_SCHEMA_VERSION)
    normalized.setdefault("heartbeat_interval_sec", default_heartbeat_interval_sec())
    normalized.setdefault("stale_after_sec", default_stale_after_sec())
    normalized.setdefault("heartbeat_at", normalized.get("acquired_at") or iso_now())
    normalized.setdefault("renewed_at", None)
    try:
        renewal_count = int(normalized.get("renewal_count") or 0)
    except (TypeError, ValueError):
        renewal_count = 0
    normalized["renewal_count"] = max(0, renewal_count)
    return normalized


def _all_leases_locked() -> list[dict[str, object]]:
    leases: list[dict[str, object]] = []
    for path in _all_lease_paths():
        lease = _read_lease(path)
        if lease:
            leases.append(_normalize_lease(lease))
    return leases


def _is_released(lease: dict[str, object]) -> bool:
    return bool(lease.get("released_at"))


def _last_activity_ts(lease: dict[str, object]) -> float | None:
    for key in ("heartbeat_at", "renewed_at", "acquired_at"):
        value = lease.get(key)
        if not value:
            continue
        parsed = parse_iso(str(value))
        if parsed:
            return parsed.timestamp()
    return None


def _is_stale(lease: dict[str, object], now: float | None = None) -> bool:
    if _is_released(lease):
        return False
    now = time.time() if now is None else now
    expires_at = parse_iso(str(lease.get("expires_at") or ""))
    if expires_at and expires_at.timestamp() <= now:
        return True
    timeout = _seconds_field(lease, "stale_after_sec", default_stale_after_sec())
    if timeout <= 0:
        return False
    last_activity = _last_activity_ts(lease)
    if last_activity is None:
        return False
    return now - last_activity > timeout


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
    if scope in {"event", "platform_event", "challenge", "run"} and lease.get("event") != policy.event:
        return False
    if scope == "challenge" and lease.get("challenge_id") != challenge_id:
        return False
    if scope == "run" and lease.get("run_id") != run_id:
        return False
    return True


def _lease_matches(
    lease: dict[str, object],
    *,
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    role: str | None = None,
    run_id: str | None = None,
) -> bool:
    if platform and lease.get("platform") != platform:
        return False
    if event and lease.get("event") != event:
        return False
    if resource_type and lease.get("resource_type") != resource_type:
        return False
    if role and lease.get("role") != role:
        return False
    if run_id and lease.get("run_id") != run_id:
        return False
    return True


def _helper_invalid_reason(
    lease: dict[str, object],
    leases_by_id: dict[str, dict[str, object]],
    now: float,
) -> str | None:
    if lease.get("role") != "helper":
        return None
    primary_id = str(lease.get("primary_lease_id") or "")
    if not primary_id:
        return "missing_primary_lease"
    primary = leases_by_id.get(primary_id)
    if not primary:
        return "missing_primary_lease"
    if _is_released(primary):
        return "primary_released"
    if _is_stale(primary, now):
        return "primary_stale"
    return None


def _detect_stale_locked(
    *,
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    now = time.time()
    leases = _all_leases_locked()
    leases_by_id = {str(lease.get("lease_id") or ""): lease for lease in leases}
    stale: list[dict[str, object]] = []
    for lease in leases:
        if _is_released(lease):
            continue
        if not _lease_matches(lease, platform=platform, event=event, resource_type=resource_type, run_id=run_id):
            continue
        reason = ""
        if _is_stale(lease, now):
            reason = "heartbeat_timeout"
        else:
            reason = _helper_invalid_reason(lease, leases_by_id, now) or ""
        if reason:
            item = dict(lease)
            item["stale_reason"] = reason
            stale.append(item)
    return stale


def _held_seconds(lease: dict[str, object], released_at: str) -> int | None:
    acquired = parse_iso(str(lease.get("acquired_at") or ""))
    released = parse_iso(released_at)
    if not acquired or not released:
        return None
    return max(0, int((released - acquired).total_seconds()))


def public_lease_summary(lease: dict[str, object]) -> dict[str, object]:
    keys = (
        "lease_id",
        "platform",
        "event",
        "resource_type",
        "challenge_id",
        "run_id",
        "owner_worker_id",
        "role",
        "primary_lease_id",
        "acquired_at",
        "heartbeat_at",
        "heartbeat_interval_sec",
        "stale_after_sec",
        "renewed_at",
        "renewal_count",
        "expires_at",
        "released_at",
        "release_reason",
        "stale_reason",
        "held_sec",
    )
    return {key: lease[key] for key in keys if key in lease and lease[key] is not None}


def _mark_released_locked(lease_ids: set[str], release_reason: str) -> list[dict[str, object]]:
    released: list[dict[str, object]] = []
    released_at = iso_now()
    for lease_id in sorted(lease_ids):
        path = _lease_path(lease_id)
        lease = _read_lease(path)
        if not lease:
            continue
        lease = _normalize_lease(lease)
        if _is_released(lease):
            continue
        lease["released_at"] = released_at
        lease["release_reason"] = release_reason
        held_sec = _held_seconds(lease, released_at)
        if held_sec is not None:
            lease["held_sec"] = held_sec
        atomic_write_json(path, lease)
        released.append(public_lease_summary(lease))
    return released


def _reclaim_stale_locked(
    *,
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    run_id: str | None = None,
    dry_run: bool = True,
) -> dict[str, object]:
    stale = _detect_stale_locked(platform=platform, event=event, resource_type=resource_type, run_id=run_id)
    stale_ids = {str(lease.get("lease_id") or "") for lease in stale if lease.get("lease_id")}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "stale_count": len(stale),
            "stale_leases": [public_lease_summary(lease) for lease in stale],
            "reclaimed": [],
            "reclaimed_count": 0,
        }
    released = _mark_released_locked(stale_ids, STALE_RELEASE_REASON)
    return {
        "ok": True,
        "dry_run": False,
        "stale_count": len(stale),
        "stale_leases": [public_lease_summary(lease) for lease in stale],
        "reclaimed": released,
        "reclaimed_count": len(released),
    }


def _active_leases_locked(
    *,
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    role: str | None = None,
) -> list[dict[str, object]]:
    now = time.time()
    all_leases = _all_leases_locked()
    leases_by_id = {str(lease.get("lease_id") or ""): lease for lease in all_leases}
    leases: list[dict[str, object]] = []
    for lease in all_leases:
        if _is_released(lease) or _is_stale(lease, now):
            continue
        if _helper_invalid_reason(lease, leases_by_id, now):
            continue
        if _lease_matches(lease, platform=platform, event=event, resource_type=resource_type, role=role):
            leases.append(lease)
    return leases


def list_leases(
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    include_stale: bool = False,
) -> list[dict[str, object]]:
    with DirectoryLock("resource-leases", "list resource leases", wait_seconds=10):
        now = time.time()
        all_leases = _all_leases_locked()
        leases_by_id = {str(lease.get("lease_id") or ""): lease for lease in all_leases}
        leases: list[dict[str, object]] = []
        for lease in all_leases:
            if _is_released(lease):
                continue
            helper_invalid = _helper_invalid_reason(lease, leases_by_id, now)
            if not include_stale and (_is_stale(lease, now) or helper_invalid):
                continue
            if _lease_matches(lease, platform=platform, event=event, resource_type=resource_type):
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
    now = iso_now()
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
        "acquired_at": now,
        "heartbeat_at": now,
        "heartbeat_interval_sec": default_heartbeat_interval_sec(),
        "stale_after_sec": default_stale_after_sec(),
        "renewed_at": None,
        "renewal_count": 0,
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
            reclaimed = _reclaim_stale_locked(
                platform=policy.platform,
                event=policy.event,
                resource_type=REMOTE_SERVER,
                dry_run=False,
            )
            stale_reclaimed = reclaimed.get("reclaimed") or []
            stale_reclaimed_ids = [str(item.get("lease_id")) for item in stale_reclaimed if item.get("lease_id")]
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
                        "stale_reclaimed": stale_reclaimed,
                        "stale_released": stale_reclaimed_ids,
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
                        "stale_reclaimed": stale_reclaimed,
                        "stale_released": stale_reclaimed_ids,
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
                        "stale_reclaimed": stale_reclaimed,
                        "stale_released": stale_reclaimed_ids,
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
                    "stale_reclaimed": stale_reclaimed,
                    "stale_released": stale_reclaimed_ids,
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
                    "stale_reclaimed": stale_reclaimed,
                    "stale_released": stale_reclaimed_ids,
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
                    "stale_reclaimed": stale_reclaimed,
                    "stale_released": stale_reclaimed_ids,
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
                "stale_reclaimed": stale_reclaimed,
                "stale_released": stale_reclaimed_ids,
            }
    except TimeoutError as exc:
        return {"ok": False, "reason": "stale_lock", "error": str(exc)}


def release_lease(
    lease_id: str | None = None,
    run_id: str | None = None,
    platform: str | None = None,
    event: str | None = None,
    include_helpers: bool = True,
    release_reason: str = "manual_release",
) -> dict[str, object]:
    if not lease_id and not run_id:
        return {"ok": False, "reason": "lease_id_or_run_id_required", "released": []}
    try:
        with DirectoryLock("resource-leases", "release resource leases", wait_seconds=30):
            leases = [
                lease
                for lease in _all_leases_locked()
                if not _is_released(lease) and _lease_matches(lease, platform=platform, event=event)
            ]
            targets: set[str] = set()
            for lease in leases:
                current_id = str(lease.get("lease_id") or "")
                if lease_id and current_id == lease_id:
                    targets.add(current_id)
                    if include_helpers:
                        for candidate in leases:
                            if candidate.get("primary_lease_id") == lease_id:
                                targets.add(str(candidate.get("lease_id") or ""))
                if run_id and lease.get("run_id") == run_id:
                    targets.add(current_id)
                    if include_helpers and lease.get("role") == "primary":
                        primary_id = current_id
                        for candidate in leases:
                            if candidate.get("primary_lease_id") == primary_id:
                                targets.add(str(candidate.get("lease_id") or ""))
            released_records = _mark_released_locked(targets, release_reason)
            released = [str(record.get("lease_id")) for record in released_records if record.get("lease_id")]
            total_held = sum(int(record.get("held_sec") or 0) for record in released_records)
            return {
                "ok": True,
                "reason": "released",
                "release_reason": release_reason,
                "released": released,
                "released_records": released_records,
                "released_count": len(released),
                "total_lease_held_sec": total_held,
            }
    except TimeoutError as exc:
        return {"ok": False, "reason": "stale_lock", "error": str(exc), "released": []}


def active_primary_count(policy: PlatformPolicy, challenge_id: str = "", run_id: str = "") -> int:
    with DirectoryLock("resource-leases", "count remote server leases", wait_seconds=10):
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


def heartbeat_lease(
    lease_id: str | None = None,
    run_id: str | None = None,
    worker_id: str | None = None,
) -> dict[str, object]:
    if not lease_id and not run_id:
        return {"ok": False, "reason": "lease_id_or_run_id_required", "updated": []}
    try:
        with DirectoryLock("resource-leases", "heartbeat resource leases", wait_seconds=30):
            now = time.time()
            leases = _all_leases_locked()
            leases_by_id = {str(lease.get("lease_id") or ""): lease for lease in leases}
            targets = [
                lease
                for lease in leases
                if (lease_id and lease.get("lease_id") == lease_id) or (run_id and lease.get("run_id") == run_id)
            ]
            updated: list[dict[str, object]] = []
            skipped: list[dict[str, object]] = []
            heartbeat_at = iso_now()
            for lease in targets:
                current_id = str(lease.get("lease_id") or "")
                if _is_released(lease):
                    skipped.append({"lease_id": current_id, "reason": "released"})
                    continue
                if worker_id and lease.get("owner_worker_id") != worker_id:
                    skipped.append({"lease_id": current_id, "reason": "worker_mismatch"})
                    continue
                if _is_stale(lease, now):
                    skipped.append({"lease_id": current_id, "reason": "stale"})
                    continue
                helper_reason = _helper_invalid_reason(lease, leases_by_id, now)
                if helper_reason:
                    skipped.append({"lease_id": current_id, "reason": helper_reason})
                    continue
                lease["heartbeat_at"] = heartbeat_at
                atomic_write_json(_lease_path(current_id), lease)
                updated.append(public_lease_summary(lease))
            return {
                "ok": bool(updated),
                "reason": "heartbeat_recorded" if updated else "no_matching_active_lease",
                "heartbeat_at": heartbeat_at,
                "updated": updated,
                "updated_count": len(updated),
                "skipped": skipped,
            }
    except TimeoutError as exc:
        return {"ok": False, "reason": "stale_lock", "error": str(exc), "updated": []}


def renew_lease(lease_id: str, extend_sec: int | None = None) -> dict[str, object]:
    if not lease_id:
        return {"ok": False, "reason": "lease_id_required"}
    try:
        with DirectoryLock("resource-leases", "renew resource lease", wait_seconds=30):
            path = _lease_path(lease_id)
            lease = _read_lease(path)
            if not lease:
                return {"ok": False, "reason": "lease_not_found", "lease_id": lease_id}
            lease = _normalize_lease(lease)
            if _is_released(lease):
                return {"ok": False, "reason": "lease_released", "lease_id": lease_id}
            if _is_stale(lease):
                return {"ok": False, "reason": "lease_stale", "lease_id": lease_id}
            now = utc_now()
            lease["renewed_at"] = iso_now()
            lease["heartbeat_at"] = lease["renewed_at"]
            lease["renewal_count"] = int(lease.get("renewal_count") or 0) + 1
            if extend_sec is not None:
                current_expiry = parse_iso(str(lease.get("expires_at") or ""))
                base = current_expiry if current_expiry and current_expiry > now else now
                lease["expires_at"] = (base + timedelta(seconds=max(0, int(extend_sec)))).isoformat(
                    timespec="seconds"
                ).replace("+00:00", "Z")
            atomic_write_json(path, lease)
            return {"ok": True, "reason": "renewed", "lease": public_lease_summary(lease)}
    except TimeoutError as exc:
        return {"ok": False, "reason": "stale_lock", "error": str(exc)}


def detect_stale_leases(
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    with DirectoryLock("resource-leases", "detect stale resource leases", wait_seconds=10):
        return [
            public_lease_summary(lease)
            for lease in _detect_stale_locked(
                platform=platform,
                event=event,
                resource_type=resource_type,
                run_id=run_id,
            )
        ]


def reclaim_stale_leases(
    platform: str | None = None,
    event: str | None = None,
    resource_type: str | None = None,
    run_id: str | None = None,
    dry_run: bool = True,
) -> dict[str, object]:
    with DirectoryLock("resource-leases", "reclaim stale resource leases", wait_seconds=30):
        return _reclaim_stale_locked(
            platform=platform,
            event=event,
            resource_type=resource_type,
            run_id=run_id,
            dry_run=dry_run,
        )
