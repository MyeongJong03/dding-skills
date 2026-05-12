"""Browser/platform automation scaffold orchestration helpers."""

from __future__ import annotations

from pathlib import Path
import hashlib

from .locks import DirectoryLock
from .paths import (
    display_path,
    download_root,
    is_inside_repo,
    platform_automation_root,
    resolve_path,
)
from .platform_adapters import PlatformAdapterError, get_adapter
from .platforms import PlatformPolicy, get_platform_policy
from .queue import append_queue_event, find_queue_item, update_queue_item
from .resources import (
    REMOTE_SERVER,
    acquire_remote_server,
    list_leases,
    public_lease_summary,
    release_lease,
)
from .schemas import (
    atomic_write_json,
    iso_now,
    read_json,
    slugify,
    validate_public_record,
)


class PlatformAutomationError(RuntimeError):
    """Raised when automation policy or local-only storage policy blocks work."""


def _policy_value(value: bool | str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    lowered = str(value).strip().lower()
    if lowered in {"true", "yes", "on", "1", "enabled", "allow", "allowed"}:
        return "true"
    if lowered in {"ask", "confirm", "manual"}:
        return "ask"
    return "false"


def _select_adapter_name(policy: PlatformPolicy, requested: str) -> str:
    if requested in {"", "generic"} and policy.adapter:
        return policy.adapter
    return requested


def _policy_gate(
    policy: PlatformPolicy,
    field: str,
    *,
    confirmed: bool = False,
    allow_ask_confirmation: bool = False,
    suggested_command: str = "",
) -> dict[str, object] | None:
    automation = policy.automation
    raw = getattr(automation, field)
    mode = _policy_value(raw)
    if mode == "true":
        return None
    if mode == "ask" and confirmed and allow_ask_confirmation:
        return None
    if mode == "ask":
        return {
            "ok": False,
            "reason": f"{field}_requires_confirmation",
            "requires_confirmation": True,
            "suggested_command": suggested_command,
            "policy": mode,
        }
    return {
        "ok": False,
        "reason": f"{field}_disabled",
        "requires_confirmation": False,
        "policy": mode,
    }


def _queue_category(item: dict[str, object] | None, default: str = "unknown") -> str:
    if item and item.get("category"):
        return str(item.get("category"))
    return default


def _update_existing_queue(
    *,
    platform: str,
    event: str,
    challenge_id: str,
    state: str,
    category: str = "unknown",
    local_capable: bool = True,
    remote_required: bool = False,
    run_id: str | None = None,
    reason: str,
) -> dict[str, object] | None:
    existing = find_queue_item(challenge_id=challenge_id, run_id=run_id, platform=platform, event=event)
    if not existing:
        return None
    return update_queue_item(
        challenge_id=challenge_id,
        run_id=str(existing.get("run_id") or run_id or "") or None,
        platform=platform,
        event=event,
        category=_queue_category(existing, category),
        state=state,
        local_capable=bool(existing.get("local_capable", local_capable)),
        remote_required=bool(existing.get("remote_required", remote_required)),
        local_exploit_ready=bool(existing.get("local_exploit_ready", False)),
        confidence=float(existing.get("confidence") or 0.0),
        destructive_risk=float(existing.get("destructive_risk") or 0.0),
        deadline=str(existing.get("deadline") or "") or None,
        reason=reason,
    )


def discover_challenges(
    *,
    platform: str,
    event: str,
    adapter_name: str = "generic",
    source: str | None = None,
    policy_path: str | Path | None = None,
    queue: bool = False,
) -> dict[str, object]:
    policy = get_platform_policy(platform, event, policy_path)
    blocked = _policy_gate(policy, "allow_problem_discovery")
    if blocked:
        return blocked
    adapter = get_adapter(_select_adapter_name(policy, adapter_name))
    try:
        challenges = adapter.discover_challenges(platform=platform, event=event, source=source)
    except PlatformAdapterError as exc:
        return {"ok": False, "reason": str(exc), "adapter": adapter.name}

    queued: list[dict[str, object]] = []
    if queue:
        for item in challenges:
            queued.append(
                update_queue_item(
                    challenge_id=str(item.get("challenge_id") or ""),
                    platform=platform,
                    event=event,
                    category=str(item.get("category") or "unknown"),
                    state="discovered",
                    local_capable=bool(item.get("local_capable", True)),
                    remote_required=bool(item.get("remote_required", False)),
                    local_exploit_ready=False,
                    confidence=0.25,
                    destructive_risk=0.0,
                    reason="platform_discovery",
                )
            )
    metadata = {
        "adapter": adapter.name,
        "challenge_count": len(challenges),
        "queued_count": len(queued),
    }
    append_queue_event(
        event_type="platform_discovery",
        platform=platform,
        event=event,
        reason="discover_challenges",
        public_safe_metadata=metadata,
    )
    return {
        "ok": True,
        "platform": platform,
        "event": event,
        "adapter": adapter.name,
        "challenge_count": len(challenges),
        "challenges": challenges,
        "queued_count": len(queued),
        "queued": queued,
    }


def _default_download_dest(platform: str, event: str, challenge_id: str) -> Path:
    return (
        download_root()
        / slugify(platform, fallback="platform", max_length=64)
        / slugify(event, fallback="event", max_length=80)
        / slugify(challenge_id, fallback="challenge", max_length=96)
    )


def _combined_hash(files: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda entry: str(entry.get("relative_path") or "")):
        digest.update(str(item.get("relative_path") or "").encode("utf-8"))
        digest.update(str(item.get("sha256") or "").encode("ascii"))
    return digest.hexdigest()


def download_files(
    *,
    platform: str,
    event: str,
    challenge_id: str,
    adapter_name: str = "generic",
    url: str | None = None,
    source: str | None = None,
    dest: str | Path | None = None,
    policy_path: str | Path | None = None,
    allow_repo_dest: bool = False,
) -> dict[str, object]:
    policy = get_platform_policy(platform, event, policy_path)
    blocked = _policy_gate(policy, "allow_file_download")
    if blocked:
        return blocked
    destination = resolve_path(dest) if dest else _default_download_dest(platform, event, challenge_id)
    if is_inside_repo(destination) and not allow_repo_dest:
        return {
            "ok": False,
            "reason": "download_dest_inside_repo",
            "dest": display_path(destination),
        }
    adapter = get_adapter(_select_adapter_name(policy, adapter_name))
    try:
        files = adapter.download_files(
            platform=platform,
            event=event,
            challenge_id=challenge_id,
            dest=destination,
            source=source,
            url=url,
        )
    except PlatformAdapterError as exc:
        return {"ok": False, "reason": str(exc), "adapter": adapter.name}

    total_size = sum(int(item.get("size") or 0) for item in files)
    metadata = {
        "schema_version": 1,
        "platform": platform,
        "event": event,
        "challenge_id": challenge_id,
        "files": files,
        "size": total_size,
        "sha256": _combined_hash(files),
        "created_at": iso_now(),
    }
    atomic_write_json(destination / "download_metadata.json", metadata)
    queue_item = _update_existing_queue(
        platform=platform,
        event=event,
        challenge_id=challenge_id,
        state="downloaded",
        local_capable=True,
        remote_required=False,
        reason="platform_download",
    )
    append_queue_event(
        event_type="platform_download",
        challenge_id=challenge_id,
        platform=platform,
        event=event,
        reason="download_files",
        public_safe_metadata={
            "adapter": adapter.name,
            "file_count": len(files),
            "downloaded_bytes": total_size,
            "queue_updated": bool(queue_item),
        },
    )
    return {
        "ok": True,
        "platform": platform,
        "event": event,
        "challenge_id": challenge_id,
        "adapter": adapter.name,
        "dest": display_path(destination),
        "metadata": metadata,
        "metadata_path": display_path(destination / "download_metadata.json"),
        "queue_updated": bool(queue_item),
    }


def acquire_platform_server(
    *,
    platform: str,
    event: str,
    challenge_id: str,
    run_id: str,
    adapter_name: str = "generic",
    policy_path: str | Path | None = None,
    worker_id: str | None = None,
    confirmed: bool = False,
    role: str = "primary",
) -> dict[str, object]:
    policy = get_platform_policy(platform, event, policy_path)
    if not policy.resources.remote_server.provisioning:
        return {"ok": False, "server_acquired": False, "reason": "remote_server_provisioning_disabled"}
    if role != "primary":
        return {"ok": False, "server_acquired": False, "reason": "primary_role_required"}
    blocked = _policy_gate(
        policy,
        "allow_server_create",
        confirmed=confirmed,
        allow_ask_confirmation=True,
        suggested_command="rerun with --confirm after manual approval",
    )
    if blocked:
        return {**blocked, "server_acquired": False}

    adapter = get_adapter(_select_adapter_name(policy, adapter_name))
    lease_result = acquire_remote_server(
        policy,
        challenge_id=challenge_id,
        run_id=run_id,
        worker_id=worker_id,
        mode="primary",
        metadata={"adapter": adapter.name},
    )
    if not lease_result.get("ok"):
        append_queue_event(
            event_type="platform_server_acquire_blocked",
            challenge_id=challenge_id,
            run_id=run_id,
            platform=platform,
            event=event,
            worker_id=worker_id,
            reason=str(lease_result.get("reason") or ""),
            public_safe_metadata={
                "adapter": adapter.name,
                "max_active_leases": lease_result.get("max_active_leases"),
                "active_primary_count": lease_result.get("active_primary_count"),
            },
        )
        return {
            "ok": False,
            "server_acquired": False,
            "reason": lease_result.get("reason"),
            "challenge_id": challenge_id,
            "run_id": run_id,
            "adapter": adapter.name,
            "active_primary_count": lease_result.get("active_primary_count"),
            "max_active_leases": lease_result.get("max_active_leases"),
        }

    lease = lease_result.get("lease") if isinstance(lease_result.get("lease"), dict) else {}
    lease_id = str(lease.get("lease_id") or "")
    try:
        with DirectoryLock("platform-automation", "create platform server record", wait_seconds=30):
            server_info = adapter.create_server(
                platform=platform,
                event=event,
                challenge_id=challenge_id,
                run_id=run_id,
                lease_id=lease_id,
            )
    except PlatformAdapterError as exc:
        release = release_lease(lease_id=lease_id, release_reason="server_create_failed")
        return {
            "ok": False,
            "server_acquired": False,
            "reason": str(exc),
            "lease_released": release.get("released_count", 0),
            "adapter": adapter.name,
        }

    queue_item = _update_existing_queue(
        platform=platform,
        event=event,
        challenge_id=challenge_id,
        run_id=run_id,
        state="remote_lease_active",
        remote_required=True,
        reason="platform_server_acquire",
    )
    append_queue_event(
        event_type="platform_server_acquired",
        challenge_id=challenge_id,
        run_id=run_id,
        platform=platform,
        event=event,
        worker_id=worker_id,
        reason="server_acquired",
        public_safe_metadata={
            "adapter": adapter.name,
            "lease_id": lease_id,
            "queue_updated": bool(queue_item),
        },
    )
    result = {
        "ok": True,
        "server_acquired": True,
        "lease_id": lease_id,
        "challenge_id": challenge_id,
        "run_id": run_id,
        "adapter": adapter.name,
        "server_info": server_info,
        "queue_updated": bool(queue_item),
    }
    errors = validate_public_record(result)
    if errors:
        raise PlatformAutomationError("server acquire output not public-safe: " + "; ".join(errors))
    return result


def release_platform_server(
    *,
    platform: str,
    event: str,
    adapter_name: str = "generic",
    challenge_id: str | None = None,
    run_id: str | None = None,
    lease_id: str | None = None,
    server_id: str | None = None,
    reason: str = "manual_release",
    role: str = "primary",
) -> dict[str, object]:
    if role != "primary":
        return {"ok": False, "reason": "primary_role_required", "server_release_count": 0}
    policy = get_platform_policy(platform, event)
    adapter = get_adapter(_select_adapter_name(policy, adapter_name))
    server_result: dict[str, object]
    try:
        with DirectoryLock("platform-automation", "release platform server record", wait_seconds=30):
            server_result = adapter.release_server(
                platform=platform,
                event=event,
                challenge_id=challenge_id,
                run_id=run_id,
                lease_id=lease_id,
                server_id=server_id,
                reason=reason,
            )
    except PlatformAdapterError as exc:
        server_result = {"ok": False, "reason": str(exc), "released_count": 0, "released": []}
    lease_result = release_lease(
        lease_id=lease_id,
        run_id=run_id,
        platform=platform,
        event=event,
        release_reason=reason,
    )
    append_queue_event(
        event_type="platform_server_released",
        challenge_id=challenge_id or "",
        run_id=run_id or "",
        platform=platform,
        event=event,
        reason=reason,
        public_safe_metadata={
            "adapter": adapter.name,
            "server_release_count": server_result.get("released_count", 0),
            "lease_release_count": lease_result.get("released_count", 0),
        },
    )
    return {
        "ok": bool(server_result.get("ok", True)) and bool(lease_result.get("ok", True)),
        "platform": platform,
        "event": event,
        "adapter": adapter.name,
        "server_release": server_result,
        "resource_release": lease_result,
        "server_release_count": int(server_result.get("released_count") or 0),
        "lease_release_count": int(lease_result.get("released_count") or 0),
    }


def server_status(
    *,
    platform: str,
    event: str,
    adapter_name: str = "generic",
    challenge_id: str | None = None,
    run_id: str | None = None,
    lease_id: str | None = None,
) -> dict[str, object]:
    policy = get_platform_policy(platform, event)
    adapter = get_adapter(_select_adapter_name(policy, adapter_name))
    try:
        adapter_status = adapter.server_status(
            platform=platform,
            event=event,
            challenge_id=challenge_id,
            run_id=run_id,
            lease_id=lease_id,
        )
    except PlatformAdapterError as exc:
        adapter_status = {"ok": False, "reason": str(exc), "server_count": 0, "servers": []}
    leases = [
        public_lease_summary(item)
        for item in list_leases(platform=platform, event=event, resource_type=REMOTE_SERVER)
        if (not challenge_id or item.get("challenge_id") == challenge_id)
        and (not run_id or item.get("run_id") == run_id)
        and (not lease_id or item.get("lease_id") == lease_id)
    ]
    return {
        "ok": bool(adapter_status.get("ok", True)),
        "platform": platform,
        "event": event,
        "adapter": adapter.name,
        "server_count": int(adapter_status.get("server_count") or 0),
        "servers": adapter_status.get("servers") or [],
        "active_lease_count": len(leases),
        "active_leases": leases,
    }


def submit_flag(
    *,
    platform: str,
    event: str,
    challenge_id: str,
    flag: str,
    adapter_name: str = "generic",
    policy_path: str | Path | None = None,
    run_id: str | None = None,
    role: str = "primary",
) -> dict[str, object]:
    if role != "primary":
        return {
            "ok": False,
            "submitted": False,
            "reason": "primary_role_required",
            "flag_redacted": "<redacted>",
        }
    policy = get_platform_policy(platform, event, policy_path)
    blocked = _policy_gate(policy, "allow_submission")
    if blocked:
        append_queue_event(
            event_type="platform_submission_blocked",
            challenge_id=challenge_id,
            run_id=run_id or "",
            platform=platform,
            event=event,
            reason=str(blocked.get("reason") or ""),
            public_safe_metadata={"submission_policy": blocked.get("policy")},
        )
        return {**blocked, "submitted": False, "flag_redacted": "<redacted>"}
    adapter = get_adapter(_select_adapter_name(policy, adapter_name))
    try:
        result = adapter.submit_flag(
            platform=platform,
            event=event,
            challenge_id=challenge_id,
            flag=flag,
            run_id=run_id,
        )
    except PlatformAdapterError as exc:
        return {"ok": False, "submitted": False, "reason": str(exc), "adapter": adapter.name}
    append_queue_event(
        event_type="platform_submission",
        challenge_id=challenge_id,
        run_id=run_id or "",
        platform=platform,
        event=event,
        reason="submitted",
        public_safe_metadata={"adapter": adapter.name, "accepted": bool(result.get("accepted"))},
    )
    return {
        "ok": bool(result.get("ok")),
        "submitted": True,
        "adapter": adapter.name,
        "challenge_id": challenge_id,
        "run_id": run_id or "",
        "accepted": bool(result.get("accepted")),
        "reason": result.get("reason") or "",
        "flag_redacted": "<redacted>",
    }


def _server_record_files(platform: str | None = None, event: str | None = None) -> list[Path]:
    root = platform_automation_root()
    if not root.is_dir():
        return []
    if platform and event:
        server_root = (
            root
            / slugify(platform, fallback="platform", max_length=64)
            / slugify(event, fallback="event", max_length=80)
            / "servers"
        )
        return sorted(server_root.glob("*.json")) if server_root.is_dir() else []
    return sorted(root.rglob("servers/*.json"))


def release_local_server_records_for_run(
    *,
    platform: str,
    event: str,
    run_id: str,
    reason: str = "finalized",
) -> dict[str, object]:
    released: list[dict[str, object]] = []
    with DirectoryLock("platform-automation", "release local platform server records", wait_seconds=30):
        for path in _server_record_files(platform, event):
            record = read_json(path, default={})
            if not isinstance(record, dict) or record.get("run_id") != run_id:
                continue
            if record.get("status") != "released":
                record["status"] = "released"
                record["released_at"] = iso_now()
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


def platform_server_record_count() -> int:
    return len(_server_record_files())


def download_metadata_count() -> int:
    root = download_root()
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("download_metadata.json") if path.is_file())
