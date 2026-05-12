"""File-backed challenge queue and local-first scheduler helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import uuid

from .locks import DirectoryLock
from .paths import queue_root
from .platforms import PlatformPolicy
from .resources import REMOTE_SERVER, active_primary_count, list_leases
from .schemas import (
    atomic_write_json,
    atomic_write_jsonl,
    iso_now,
    parse_iso,
    read_json,
    read_jsonl,
    slugify,
    validate_public_record,
)


QUEUE_SCHEMA_VERSION = 1
QUEUE_STATES = (
    "discovered",
    "downloaded",
    "local_triage",
    "local_analysis",
    "exploit_planning",
    "local_exploit_ready",
    "needs_remote",
    "waiting_for_remote",
    "remote_lease_active",
    "remote_testing",
    "remote_shared_helping",
    "solved",
    "abandoned",
    "finalized",
)
TERMINAL_STATES = {"solved", "abandoned", "finalized"}
LOCAL_WORK_STATES = {
    "discovered",
    "downloaded",
    "local_triage",
    "local_analysis",
    "exploit_planning",
    "waiting_for_remote",
}
REMOTE_READY_STATES = {
    "local_exploit_ready",
    "needs_remote",
    "waiting_for_remote",
}
QUEUE_EVENT_TYPES = {
    "queue_item_created",
    "queue_item_updated",
    "state_changed",
    "priority_updated",
    "scheduler_decision",
    "remote_blocked",
    "local_work_selected",
    "remote_acquire_selected",
    "helper_join_selected",
    "wait_selected",
    "lease_acquired",
    "lease_released",
    "lease_stale_detected",
    "lease_stale_reclaimed",
    "finalized",
    "keep_lease",
    "worker_claimed",
    "worker_claim_heartbeat",
    "worker_claim_released",
    "worker_claim_stale_detected",
    "worker_claim_stale_reclaimed",
    "worker_action_selected",
    "worker_wait",
    "worker_auto_finalize",
    "worker_auto_acquire_remote",
}


@dataclass
class QueueItem:
    queue_id: str
    challenge_id: str
    run_id: str | None
    platform: str
    event: str
    category: str
    state: str
    local_capable: bool
    remote_required: bool
    local_exploit_ready: bool
    confidence: float
    destructive_risk: float
    deadline: str | None
    created_at: str
    updated_at: str
    priority_score: float

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["schema_version"] = QUEUE_SCHEMA_VERSION
        return data


def _queue_path(queue_id: str) -> Path:
    return queue_root() / f"{slugify(queue_id, fallback='queue', max_length=160)}.json"


def _events_path() -> Path:
    return queue_root() / "events.jsonl"


def _load_queue_file(path: Path) -> dict[str, object] | None:
    data = read_json(path, default={})
    if not isinstance(data, dict) or not data:
        return None
    return data


def _queue_files() -> list[Path]:
    root = queue_root()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def _public_safe_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    if not metadata:
        return {}
    safe = dict(metadata)
    errors = validate_public_record(safe)
    if errors:
        raise ValueError("queue event metadata is not public-safe: " + "; ".join(errors))
    return safe


def _append_queue_event_locked(
    *,
    event_type: str,
    queue_id: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    platform: str | None = None,
    event: str | None = None,
    old_state: str | None = None,
    new_state: str | None = None,
    worker_id: str | None = None,
    reason: str | None = None,
    public_safe_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    metadata = _public_safe_metadata(public_safe_metadata)
    record: dict[str, object] = {
        "event_id": uuid.uuid4().hex,
        "timestamp": iso_now(),
        "queue_id": queue_id or "",
        "challenge_id": challenge_id or "",
        "run_id": run_id,
        "platform": platform,
        "event": event,
        "event_type": event_type,
        "old_state": old_state,
        "new_state": new_state,
        "worker_id": worker_id,
        "reason": reason,
        "public_safe_metadata": metadata,
    }
    record = {key: value for key, value in record.items() if value is not None}
    errors = validate_public_record(record)
    if errors:
        raise ValueError("queue event is not public-safe: " + "; ".join(errors))
    records = read_jsonl(_events_path())
    records.append(record)
    atomic_write_jsonl(_events_path(), records)
    return record


def append_queue_event(
    *,
    event_type: str,
    queue_id: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    platform: str | None = None,
    event: str | None = None,
    old_state: str | None = None,
    new_state: str | None = None,
    worker_id: str | None = None,
    reason: str | None = None,
    public_safe_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    with DirectoryLock("challenge-queue", "append challenge queue event", wait_seconds=30):
        return _append_queue_event_locked(
            event_type=event_type,
            queue_id=queue_id,
            challenge_id=challenge_id,
            run_id=run_id,
            platform=platform,
            event=event,
            old_state=old_state,
            new_state=new_state,
            worker_id=worker_id,
            reason=reason,
            public_safe_metadata=public_safe_metadata,
        )


def list_queue_events(
    *,
    platform: str | None = None,
    event: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    tail: int | None = None,
) -> list[dict[str, object]]:
    with DirectoryLock("challenge-queue", "list challenge queue events", wait_seconds=10):
        records = read_jsonl(_events_path())
    filtered: list[dict[str, object]] = []
    for record in records:
        if platform and record.get("platform") != platform:
            continue
        if event and record.get("event") != event:
            continue
        if challenge_id and record.get("challenge_id") != challenge_id:
            continue
        if run_id and record.get("run_id") != run_id:
            continue
        filtered.append(record)
    if tail is not None and tail >= 0:
        filtered = filtered[-tail:]
    return filtered


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_priority_score(item: dict[str, object]) -> float:
    state = str(item.get("state") or "discovered")
    confidence = _clamp(float(item.get("confidence") or 0.0))
    destructive_risk = _clamp(float(item.get("destructive_risk") or 0.0))
    score = confidence * 100.0 - destructive_risk * 20.0
    if item.get("local_exploit_ready") or state == "local_exploit_ready":
        score += 120.0
    if state in {"needs_remote", "waiting_for_remote"} or item.get("remote_required"):
        score += 35.0
    if state in {"downloaded", "local_triage", "local_analysis", "exploit_planning"}:
        score += 10.0
    deadline = parse_iso(str(item.get("deadline") or ""))
    if deadline:
        score += 15.0
    if state in TERMINAL_STATES:
        score -= 1000.0
    return round(score, 3)


def _new_queue_id(platform: str, event: str, challenge_id: str, run_id: str | None) -> str:
    suffix = run_id or uuid.uuid4().hex[:8]
    return "-".join(
        [
            slugify(platform, fallback="platform", max_length=32),
            slugify(event, fallback="event", max_length=40),
            slugify(challenge_id, fallback="challenge", max_length=72),
            slugify(suffix, fallback="run", max_length=32),
        ]
    )


def _find_existing_locked(
    *,
    challenge_id: str,
    run_id: str | None = None,
    platform: str | None = None,
    event: str | None = None,
) -> dict[str, object] | None:
    for path in _queue_files():
        item = _load_queue_file(path)
        if not item:
            continue
        if run_id and item.get("run_id") == run_id:
            return item
        if item.get("challenge_id") != challenge_id:
            continue
        if platform and item.get("platform") != platform:
            continue
        if event and item.get("event") != event:
            continue
        return item
    return None


def find_queue_item(
    *,
    challenge_id: str,
    run_id: str | None = None,
    platform: str | None = None,
    event: str | None = None,
) -> dict[str, object] | None:
    with DirectoryLock("challenge-queue", "find challenge queue item", wait_seconds=10):
        item = _find_existing_locked(
            challenge_id=challenge_id,
            run_id=run_id,
            platform=platform,
            event=event,
        )
        return dict(item) if item else None


def update_queue_item(
    *,
    challenge_id: str,
    platform: str,
    event: str,
    category: str,
    state: str,
    run_id: str | None = None,
    local_capable: bool = True,
    remote_required: bool = False,
    local_exploit_ready: bool = False,
    confidence: float = 0.0,
    destructive_risk: float = 0.0,
    deadline: str | None = None,
    worker_id: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    if state not in QUEUE_STATES:
        raise ValueError(f"unsupported queue state: {state}")
    with DirectoryLock("challenge-queue", "update challenge queue", wait_seconds=30):
        now = iso_now()
        existing = _find_existing_locked(
            challenge_id=challenge_id,
            run_id=run_id,
            platform=platform,
            event=event,
        )
        queue_id = str(existing.get("queue_id")) if existing else _new_queue_id(platform, event, challenge_id, run_id)
        created_at = str(existing.get("created_at") or now) if existing else now
        old_state = str(existing.get("state") or "") if existing else None
        old_priority = float(existing.get("priority_score") or 0.0) if existing else None
        item: dict[str, object] = {
            "schema_version": QUEUE_SCHEMA_VERSION,
            "queue_id": queue_id,
            "challenge_id": challenge_id,
            "run_id": run_id,
            "platform": platform,
            "event": event,
            "category": category,
            "state": state,
            "local_capable": bool(local_capable),
            "remote_required": bool(remote_required),
            "local_exploit_ready": bool(local_exploit_ready or state == "local_exploit_ready"),
            "confidence": _clamp(float(confidence)),
            "destructive_risk": _clamp(float(destructive_risk)),
            "deadline": deadline,
            "created_at": created_at,
            "updated_at": now,
        }
        item["priority_score"] = compute_priority_score(item)
        atomic_write_json(_queue_path(queue_id), item)
        _append_queue_event_locked(
            event_type="queue_item_updated" if existing else "queue_item_created",
            queue_id=queue_id,
            challenge_id=challenge_id,
            run_id=run_id,
            platform=platform,
            event=event,
            old_state=old_state,
            new_state=state,
            worker_id=worker_id,
            reason=reason or ("updated" if existing else "created"),
            public_safe_metadata={"priority_score": item["priority_score"]},
        )
        if existing and old_state != state:
            _append_queue_event_locked(
                event_type="state_changed",
                queue_id=queue_id,
                challenge_id=challenge_id,
                run_id=run_id,
                platform=platform,
                event=event,
                old_state=old_state,
                new_state=state,
                worker_id=worker_id,
                reason=reason,
            )
        if existing and old_priority is not None and old_priority != float(item["priority_score"]):
            _append_queue_event_locked(
                event_type="priority_updated",
                queue_id=queue_id,
                challenge_id=challenge_id,
                run_id=run_id,
                platform=platform,
                event=event,
                worker_id=worker_id,
                reason=reason,
                public_safe_metadata={
                    "old_priority_score": old_priority,
                    "new_priority_score": item["priority_score"],
                },
            )
        return item


def list_queue_items(*, platform: str | None = None, event: str | None = None) -> list[dict[str, object]]:
    with DirectoryLock("challenge-queue", "list challenge queue", wait_seconds=10):
        items: list[dict[str, object]] = []
        for path in _queue_files():
            item = _load_queue_file(path)
            if not item:
                continue
            if platform and item.get("platform") != platform:
                continue
            if event and item.get("event") != event:
                continue
            item["priority_score"] = compute_priority_score(item)
            items.append(item)
        return sorted(items, key=lambda item: float(item.get("priority_score") or 0), reverse=True)


def mark_finalized(
    *,
    challenge_id: str,
    run_id: str | None = None,
    worker_id: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    with DirectoryLock("challenge-queue", "finalize challenge queue item", wait_seconds=10):
        item = _find_existing_locked(challenge_id=challenge_id, run_id=run_id)
        if not item:
            return {"updated": False, "reason": "queue_item_not_found"}
        old_state = str(item.get("state") or "")
        item["state"] = "finalized"
        item["updated_at"] = iso_now()
        item["priority_score"] = compute_priority_score(item)
        atomic_write_json(_queue_path(str(item["queue_id"])), item)
        if old_state != "finalized":
            _append_queue_event_locked(
                event_type="state_changed",
                queue_id=str(item.get("queue_id") or ""),
                challenge_id=str(item.get("challenge_id") or challenge_id),
                run_id=str(item.get("run_id") or run_id or ""),
                platform=str(item.get("platform") or ""),
                event=str(item.get("event") or ""),
                old_state=old_state,
                new_state="finalized",
                worker_id=worker_id,
                reason=reason,
            )
        _append_queue_event_locked(
            event_type="finalized",
            queue_id=str(item.get("queue_id") or ""),
            challenge_id=str(item.get("challenge_id") or challenge_id),
            run_id=str(item.get("run_id") or run_id or ""),
            platform=str(item.get("platform") or ""),
            event=str(item.get("event") or ""),
            old_state=old_state,
            new_state="finalized",
            worker_id=worker_id,
            reason=reason,
        )
        return {"updated": True, "queue_id": item.get("queue_id"), "state": "finalized"}


def _remote_capacity_available(policy: PlatformPolicy) -> bool:
    max_active = policy.resources.remote_server.max_active_leases
    if max_active <= 0:
        return False
    return active_primary_count(policy) < max_active


def _eligible_remote(item: dict[str, object]) -> bool:
    state = str(item.get("state") or "")
    return (
        state not in TERMINAL_STATES
        and bool(item.get("remote_required") or item.get("local_exploit_ready") or state in REMOTE_READY_STATES)
    )


def _eligible_local(item: dict[str, object]) -> bool:
    state = str(item.get("state") or "")
    return (
        state not in TERMINAL_STATES
        and bool(item.get("local_capable"))
        and not bool(item.get("local_exploit_ready"))
        and state in LOCAL_WORK_STATES
    )


def _record_scheduler_decision(
    policy: PlatformPolicy,
    decision: dict[str, object],
    *,
    worker_id: str | None,
    remote_blocked: dict[str, object] | None = None,
) -> None:
    if remote_blocked:
        _append = append_queue_event
        _append(
            event_type="remote_blocked",
            queue_id=str(remote_blocked.get("queue_id") or ""),
            challenge_id=str(remote_blocked.get("challenge_id") or ""),
            run_id=str(remote_blocked.get("run_id") or ""),
            platform=policy.platform,
            event=policy.event,
            worker_id=worker_id,
            reason="max_active_leases_reached",
            public_safe_metadata={
                "priority_score": remote_blocked.get("priority_score"),
                "max_active_leases": policy.resources.remote_server.max_active_leases,
            },
        )

    action = str(decision.get("action") or "wait")
    action_event = {
        "acquire_remote": "remote_acquire_selected",
        "do_local_work": "local_work_selected",
        "join_remote_as_helper": "helper_join_selected",
        "wait": "wait_selected",
    }.get(action, "scheduler_decision")
    metadata = {
        "action": action,
        "priority_score": decision.get("priority_score"),
    }
    if decision.get("primary_lease_id"):
        metadata["primary_lease_id"] = decision.get("primary_lease_id")
    for event_type in ("scheduler_decision", action_event):
        append_queue_event(
            event_type=event_type,
            queue_id=str(decision.get("queue_id") or ""),
            challenge_id=str(decision.get("challenge_id") or ""),
            run_id=str(decision.get("run_id") or ""),
            platform=policy.platform,
            event=policy.event,
            worker_id=worker_id,
            reason=str(decision.get("reason") or ""),
            public_safe_metadata=metadata,
        )


def select_next(policy: PlatformPolicy, *, worker_id: str | None = None) -> dict[str, object]:
    items = list_queue_items(platform=policy.platform, event=policy.event)
    remote_candidates = [item for item in items if _eligible_remote(item)]
    if _remote_capacity_available(policy) and remote_candidates:
        item = remote_candidates[0]
        decision = {
            "action": "acquire_remote",
            "challenge_id": item.get("challenge_id"),
            "run_id": item.get("run_id"),
            "reason": "remote_capacity_available",
            "priority_score": item.get("priority_score"),
            "queue_id": item.get("queue_id"),
        }
        _record_scheduler_decision(policy, decision, worker_id=worker_id)
        return decision

    remote_blocked = remote_candidates[0] if remote_candidates else None

    local_candidates = [item for item in items if _eligible_local(item)]
    if local_candidates:
        item = local_candidates[0]
        decision = {
            "action": "do_local_work",
            "challenge_id": item.get("challenge_id"),
            "run_id": item.get("run_id"),
            "reason": "remote_unavailable_local_prework",
            "priority_score": item.get("priority_score"),
            "queue_id": item.get("queue_id"),
        }
        _record_scheduler_decision(policy, decision, worker_id=worker_id, remote_blocked=remote_blocked)
        return decision

    sharing = policy.resources.remote_server.sharing
    if sharing.allowed:
        active_primary = list_leases(
            platform=policy.platform,
            event=policy.event,
            resource_type=REMOTE_SERVER,
        )
        primary_by_challenge = {
            str(lease.get("challenge_id")): lease
            for lease in active_primary
            if lease.get("role") == "primary"
        }
        helper_candidates = [
            item
            for item in items
            if str(item.get("challenge_id")) in primary_by_challenge
            and str(item.get("state") or "") not in TERMINAL_STATES
        ]
        if helper_candidates:
            item = helper_candidates[0]
            primary = primary_by_challenge[str(item.get("challenge_id"))]
            decision = {
                "action": "join_remote_as_helper",
                "challenge_id": item.get("challenge_id"),
                "run_id": item.get("run_id"),
                "reason": "sharing_allowed_active_remote",
                "priority_score": item.get("priority_score"),
                "queue_id": item.get("queue_id"),
                "primary_lease_id": primary.get("lease_id"),
            }
            _record_scheduler_decision(policy, decision, worker_id=worker_id, remote_blocked=remote_blocked)
            return decision

    decision = {
        "action": "wait",
        "challenge_id": None,
        "run_id": None,
        "reason": "no_remote_capacity_no_local_work",
        "priority_score": None,
    }
    _record_scheduler_decision(policy, decision, worker_id=worker_id, remote_blocked=remote_blocked)
    return decision
