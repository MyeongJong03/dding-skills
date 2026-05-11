"""File-backed challenge queue and local-first scheduler helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import uuid

from .locks import DirectoryLock
from .paths import queue_root
from .platforms import PlatformPolicy
from .resources import REMOTE_SERVER, active_primary_count, list_leases
from .schemas import atomic_write_json, iso_now, parse_iso, read_json, slugify


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


def mark_finalized(*, challenge_id: str, run_id: str | None = None) -> dict[str, object]:
    with DirectoryLock("challenge-queue", "finalize challenge queue item", wait_seconds=10):
        item = _find_existing_locked(challenge_id=challenge_id, run_id=run_id)
        if not item:
            return {"updated": False, "reason": "queue_item_not_found"}
        item["state"] = "finalized"
        item["updated_at"] = iso_now()
        item["priority_score"] = compute_priority_score(item)
        atomic_write_json(_queue_path(str(item["queue_id"])), item)
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


def select_next(policy: PlatformPolicy, *, worker_id: str | None = None) -> dict[str, object]:
    items = list_queue_items(platform=policy.platform, event=policy.event)
    remote_candidates = [item for item in items if _eligible_remote(item)]
    if _remote_capacity_available(policy) and remote_candidates:
        item = remote_candidates[0]
        return {
            "action": "acquire_remote",
            "challenge_id": item.get("challenge_id"),
            "run_id": item.get("run_id"),
            "reason": "remote_capacity_available",
            "priority_score": item.get("priority_score"),
            "queue_id": item.get("queue_id"),
        }

    local_candidates = [item for item in items if _eligible_local(item)]
    if local_candidates:
        item = local_candidates[0]
        return {
            "action": "do_local_work",
            "challenge_id": item.get("challenge_id"),
            "run_id": item.get("run_id"),
            "reason": "remote_unavailable_local_prework",
            "priority_score": item.get("priority_score"),
            "queue_id": item.get("queue_id"),
        }

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
            return {
                "action": "join_remote_as_helper",
                "challenge_id": item.get("challenge_id"),
                "run_id": item.get("run_id"),
                "reason": "sharing_allowed_active_remote",
                "priority_score": item.get("priority_score"),
                "queue_id": item.get("queue_id"),
                "primary_lease_id": primary.get("lease_id"),
            }

    return {
        "action": "wait",
        "challenge_id": None,
        "run_id": None,
        "reason": "no_remote_capacity_no_local_work",
        "priority_score": None,
    }
