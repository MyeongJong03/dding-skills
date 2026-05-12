"""Queue worker claim and action-selection helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import os
import time
import uuid

from .locks import DirectoryLock
from .paths import display_path, local_run_root, worker_root
from .platforms import PlatformPolicy
from .queue import (
    LOCAL_WORK_STATES,
    REMOTE_READY_STATES,
    TERMINAL_STATES,
    append_queue_event,
    list_queue_items,
)
from .resources import REMOTE_SERVER, active_primary_count, detect_stale_leases, list_leases
from .schemas import atomic_write_json, iso_now, parse_iso, read_json, slugify
from .verifier import load_verifier_result, verifier_summary


WORKER_SCHEMA_VERSION = 1
DEFAULT_CLAIM_STALE_AFTER_SEC = 180
WORKER_ACTIONS = (
    "do_local_work",
    "acquire_remote",
    "join_remote_as_helper",
    "verify_solution",
    "finalize_challenge",
    "wait",
    "no_work",
)


@dataclass
class WorkerClaim:
    worker_id: str
    challenge_id: str
    run_id: str
    claimed_at: str
    heartbeat_at: str
    stale_after_sec: int
    action: str
    schema_version: int = WORKER_SCHEMA_VERSION
    claim_id: str = ""
    queue_id: str = ""
    platform: str = ""
    event: str = ""
    shared: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def make_worker_id() -> str:
    configured = os.environ.get("CTF_WORKER_ID")
    if configured:
        return configured
    return f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def worker_id_hash(worker_id: str) -> str:
    return hashlib.sha256(worker_id.encode("utf-8")).hexdigest()[:16]


def default_claim_stale_after_sec() -> int:
    raw = os.environ.get("CTF_WORKER_STALE_AFTER_SEC") or os.environ.get("CTF_WORKER_STALE_SECONDS")
    if not raw:
        return DEFAULT_CLAIM_STALE_AFTER_SEC
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_CLAIM_STALE_AFTER_SEC


def _claim_id(challenge_id: str, worker_id: str, *, shared: bool = False) -> str:
    prefix = "helper" if shared else "primary"
    base = slugify(challenge_id, fallback="challenge", max_length=120)
    if shared:
        return f"{prefix}-{base}-{worker_id_hash(worker_id)}"
    return f"{prefix}-{base}"


def _claim_path(claim_id: str) -> Path:
    return worker_root() / f"{slugify(claim_id, fallback='claim', max_length=180)}.json"


def _claim_files() -> list[Path]:
    root = worker_root()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def _read_claim(path: Path) -> dict[str, object] | None:
    data = read_json(path, default={})
    if not isinstance(data, dict) or not data:
        return None
    return _normalize_claim(data)


def _seconds(value: object, default: int) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _normalize_claim(claim: dict[str, object]) -> dict[str, object]:
    normalized = dict(claim)
    normalized.setdefault("schema_version", WORKER_SCHEMA_VERSION)
    normalized.setdefault("claimed_at", normalized.get("heartbeat_at") or iso_now())
    normalized.setdefault("heartbeat_at", normalized.get("claimed_at") or iso_now())
    normalized.setdefault("stale_after_sec", default_claim_stale_after_sec())
    normalized.setdefault("shared", normalized.get("action") == "join_remote_as_helper")
    normalized["stale_after_sec"] = _seconds(normalized.get("stale_after_sec"), default_claim_stale_after_sec())
    if not normalized.get("claim_id") and normalized.get("challenge_id") and normalized.get("worker_id"):
        normalized["claim_id"] = _claim_id(
            str(normalized.get("challenge_id") or ""),
            str(normalized.get("worker_id") or ""),
            shared=bool(normalized.get("shared")),
        )
    return normalized


def _last_claim_activity(claim: dict[str, object]) -> float | None:
    for key in ("heartbeat_at", "claimed_at"):
        parsed = parse_iso(str(claim.get(key) or ""))
        if parsed:
            return parsed.timestamp()
    return None


def is_stale_claim(claim: dict[str, object], now: float | None = None) -> bool:
    stale_after = _seconds(claim.get("stale_after_sec"), default_claim_stale_after_sec())
    if stale_after <= 0:
        return False
    last_activity = _last_claim_activity(claim)
    if last_activity is None:
        return False
    now = time.time() if now is None else now
    return now - last_activity > stale_after


def public_claim_summary(claim: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_claim(claim)
    return {
        "claim_id": str(normalized.get("claim_id") or ""),
        "worker_id_hash": worker_id_hash(str(normalized.get("worker_id") or "")),
        "challenge_id": str(normalized.get("challenge_id") or ""),
        "run_id": str(normalized.get("run_id") or ""),
        "platform": str(normalized.get("platform") or ""),
        "event": str(normalized.get("event") or ""),
        "action": str(normalized.get("action") or ""),
        "claimed_at": str(normalized.get("claimed_at") or ""),
        "heartbeat_at": str(normalized.get("heartbeat_at") or ""),
        "stale_after_sec": _seconds(normalized.get("stale_after_sec"), default_claim_stale_after_sec()),
        "shared": bool(normalized.get("shared")),
        "stale": is_stale_claim(normalized),
    }


def _all_claims_locked() -> list[dict[str, object]]:
    claims: list[dict[str, object]] = []
    for path in _claim_files():
        claim = _read_claim(path)
        if claim:
            claims.append(claim)
    return claims


def _claim_matches(
    claim: dict[str, object],
    *,
    platform: str | None = None,
    event: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    worker_id: str | None = None,
) -> bool:
    if platform and claim.get("platform") != platform:
        return False
    if event and claim.get("event") != event:
        return False
    if challenge_id and claim.get("challenge_id") != challenge_id:
        return False
    if run_id and claim.get("run_id") != run_id:
        return False
    if worker_id and claim.get("worker_id") != worker_id:
        return False
    return True


def list_claims(
    *,
    platform: str | None = None,
    event: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    worker_id: str | None = None,
    include_stale: bool = True,
) -> list[dict[str, object]]:
    with DirectoryLock("worker-claims", "list worker claims", wait_seconds=10):
        claims = []
        for claim in _all_claims_locked():
            if not _claim_matches(
                claim,
                platform=platform,
                event=event,
                challenge_id=challenge_id,
                run_id=run_id,
                worker_id=worker_id,
            ):
                continue
            if not include_stale and is_stale_claim(claim):
                continue
            claims.append(claim)
        return claims


def _record_claim_event(
    event_type: str,
    claim: dict[str, object],
    *,
    worker_id: str | None = None,
    reason: str | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    metadata: dict[str, object] = {
        "claim_id": claim.get("claim_id"),
        "worker_id_hash": worker_id_hash(str(claim.get("worker_id") or "")),
        "action": claim.get("action"),
        "stale_after_sec": claim.get("stale_after_sec"),
        "shared": bool(claim.get("shared")),
    }
    if extra:
        metadata.update(extra)
    append_queue_event(
        event_type=event_type,
        queue_id=str(claim.get("queue_id") or ""),
        challenge_id=str(claim.get("challenge_id") or ""),
        run_id=str(claim.get("run_id") or ""),
        platform=str(claim.get("platform") or ""),
        event=str(claim.get("event") or ""),
        worker_id=worker_id or str(claim.get("worker_id") or ""),
        reason=reason,
        public_safe_metadata=metadata,
    )


def detect_stale_claims(
    *,
    platform: str | None = None,
    event: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    record_events: bool = False,
) -> list[dict[str, object]]:
    with DirectoryLock("worker-claims", "detect stale worker claims", wait_seconds=10):
        stale = [
            claim
            for claim in _all_claims_locked()
            if _claim_matches(claim, platform=platform, event=event, challenge_id=challenge_id, run_id=run_id)
            and is_stale_claim(claim)
        ]
    if record_events:
        for claim in stale:
            _record_claim_event("worker_claim_stale_detected", claim, reason="heartbeat_timeout")
    return stale


def reclaim_stale_claims(
    *,
    platform: str | None = None,
    event: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    worker_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    reclaimed: list[dict[str, object]] = []
    stale: list[dict[str, object]] = []
    with DirectoryLock("worker-claims", "reclaim stale worker claims", wait_seconds=30):
        for path in _claim_files():
            claim = _read_claim(path)
            if not claim:
                continue
            if not _claim_matches(claim, platform=platform, event=event, challenge_id=challenge_id, run_id=run_id):
                continue
            if not is_stale_claim(claim):
                continue
            stale.append(claim)
            if not dry_run:
                try:
                    path.unlink()
                    reclaimed.append(claim)
                except FileNotFoundError:
                    pass

    for claim in stale:
        _record_claim_event("worker_claim_stale_detected", claim, worker_id=worker_id, reason="heartbeat_timeout")
    if not dry_run:
        for claim in reclaimed:
            _record_claim_event("worker_claim_stale_reclaimed", claim, worker_id=worker_id, reason="stale_reclaimed")
    return {
        "ok": True,
        "dry_run": dry_run,
        "stale_count": len(stale),
        "reclaimed_count": len(reclaimed),
        "stale_claims": [public_claim_summary(claim) for claim in stale],
        "reclaimed": [public_claim_summary(claim) for claim in reclaimed],
    }


def claim_queue_item(
    item: dict[str, object],
    *,
    worker_id: str,
    action: str,
    stale_after_sec: int | None = None,
    shared: bool | None = None,
) -> dict[str, object]:
    if action not in WORKER_ACTIONS:
        raise ValueError(f"unsupported worker action: {action}")
    challenge_id = str(item.get("challenge_id") or "")
    if not challenge_id:
        return {"ok": False, "claimed": False, "reason": "challenge_id_required"}
    run_id = str(item.get("run_id") or "")
    shared_claim = bool(action == "join_remote_as_helper" if shared is None else shared)
    claim_id = _claim_id(challenge_id, worker_id, shared=shared_claim)
    path = _claim_path(claim_id)
    stale_after = stale_after_sec if stale_after_sec is not None else default_claim_stale_after_sec()
    now = iso_now()
    old_claim: dict[str, object] | None = None
    stale_reclaimed = False
    reused = False

    with DirectoryLock("worker-claims", "claim queue item", wait_seconds=30):
        if not shared_claim:
            for existing_path in _claim_files():
                existing = _read_claim(existing_path)
                if not existing or bool(existing.get("shared")):
                    continue
                if existing.get("challenge_id") != challenge_id:
                    continue
                if not is_stale_claim(existing):
                    if existing.get("worker_id") != worker_id:
                        return {
                            "ok": False,
                            "claimed": False,
                            "reason": "active_claim_exists",
                            "claim": public_claim_summary(existing),
                        }
                    path = existing_path
                    claim_id = str(existing.get("claim_id") or claim_id)
                    old_claim = existing
                    reused = True
                    break
                old_claim = existing
                stale_reclaimed = True
                try:
                    existing_path.unlink()
                except FileNotFoundError:
                    pass
                break
        else:
            existing = _read_claim(path)
            if existing and not is_stale_claim(existing):
                old_claim = existing
                reused = True
            elif existing and is_stale_claim(existing):
                old_claim = existing
                stale_reclaimed = True

        claimed_at = str(old_claim.get("claimed_at") or now) if reused and old_claim else now
        claim = WorkerClaim(
            schema_version=WORKER_SCHEMA_VERSION,
            claim_id=claim_id,
            worker_id=worker_id,
            challenge_id=challenge_id,
            run_id=run_id,
            platform=str(item.get("platform") or ""),
            event=str(item.get("event") or ""),
            queue_id=str(item.get("queue_id") or ""),
            claimed_at=claimed_at,
            heartbeat_at=now,
            stale_after_sec=max(0, int(stale_after)),
            action=action,
            shared=shared_claim,
        ).to_dict()
        atomic_write_json(path, claim)

    if stale_reclaimed and old_claim:
        _record_claim_event("worker_claim_stale_detected", old_claim, worker_id=worker_id, reason="heartbeat_timeout")
        _record_claim_event("worker_claim_stale_reclaimed", old_claim, worker_id=worker_id, reason="replaced_by_new_claim")
    _record_claim_event(
        "worker_claim_heartbeat" if reused else "worker_claimed",
        claim,
        reason="claim_reused" if reused else "claimed",
    )
    return {
        "ok": True,
        "claimed": True,
        "reason": "claim_reused" if reused else "claimed",
        "claim": public_claim_summary(claim),
        "reclaimed_stale": stale_reclaimed,
    }


def heartbeat_claim(
    *,
    worker_id: str,
    challenge_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    updated: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    heartbeat_at = iso_now()
    with DirectoryLock("worker-claims", "heartbeat worker claim", wait_seconds=30):
        for path in _claim_files():
            claim = _read_claim(path)
            if not claim:
                continue
            if not _claim_matches(claim, challenge_id=challenge_id, run_id=run_id, worker_id=worker_id):
                continue
            if is_stale_claim(claim):
                skipped.append({"claim_id": claim.get("claim_id"), "reason": "stale"})
                continue
            claim["heartbeat_at"] = heartbeat_at
            atomic_write_json(path, claim)
            updated.append(claim)
    for claim in updated:
        _record_claim_event("worker_claim_heartbeat", claim, reason="heartbeat")
    return {
        "ok": bool(updated),
        "reason": "heartbeat_recorded" if updated else "no_matching_active_claim",
        "heartbeat_at": heartbeat_at,
        "updated_count": len(updated),
        "updated": [public_claim_summary(claim) for claim in updated],
        "skipped": skipped,
    }


def release_claim(
    *,
    worker_id: str | None = None,
    challenge_id: str | None = None,
    run_id: str | None = None,
    reason: str = "manual_release",
) -> dict[str, object]:
    if not any([worker_id, challenge_id, run_id]):
        return {"ok": False, "released_count": 0, "released": [], "reason": "selector_required"}
    released: list[dict[str, object]] = []
    with DirectoryLock("worker-claims", "release worker claim", wait_seconds=30):
        for path in _claim_files():
            claim = _read_claim(path)
            if not claim:
                continue
            if not _claim_matches(claim, challenge_id=challenge_id, run_id=run_id, worker_id=worker_id):
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            released.append(claim)
    for claim in released:
        _record_claim_event("worker_claim_released", claim, reason=reason)
    return {
        "ok": True,
        "released_count": len(released),
        "released": [public_claim_summary(claim) for claim in released],
        "reason": reason,
    }


def resolve_run_dir_for_item(item: dict[str, object]) -> Path | None:
    challenge_id = str(item.get("challenge_id") or "")
    run_id = str(item.get("run_id") or "")
    if not challenge_id or not run_id:
        return None
    path = local_run_root() / challenge_id / run_id
    return path if path.exists() else None


def _finalization_record(item: dict[str, object]) -> dict[str, object]:
    run_dir = resolve_run_dir_for_item(item)
    if not run_dir:
        return {}
    for name in ("finalization.json", "finalize.json"):
        data = read_json(run_dir / name, default={})
        if isinstance(data, dict) and data:
            return data
    run = read_json(run_dir / "run.json", default={})
    if isinstance(run, dict) and isinstance(run.get("finalization"), dict):
        return run["finalization"]
    return {}


def _is_finalized(item: dict[str, object]) -> bool:
    if str(item.get("state") or "") == "finalized":
        return True
    final = _finalization_record(item)
    return bool(final.get("finalized") or final.get("finalized_at"))


def _verifier_success(item: dict[str, object]) -> bool:
    run_dir = resolve_run_dir_for_item(item)
    if not run_dir:
        return False
    verifier = load_verifier_result(run_dir)
    return bool(verifier_summary(verifier).get("success"))


def _remote_capacity_available(policy: PlatformPolicy) -> bool:
    remote = policy.resources.remote_server
    if not remote.provisioning or remote.max_active_leases <= 0:
        return False
    return active_primary_count(policy) < remote.max_active_leases


def _remote_candidate(item: dict[str, object]) -> bool:
    state = str(item.get("state") or "")
    return (
        state not in TERMINAL_STATES
        and not _is_finalized(item)
        and bool(item.get("local_exploit_ready") or item.get("remote_required") or state in REMOTE_READY_STATES)
    )


def _local_candidate(item: dict[str, object]) -> bool:
    state = str(item.get("state") or "")
    return (
        state not in TERMINAL_STATES
        and not _is_finalized(item)
        and bool(item.get("local_capable"))
        and not bool(item.get("local_exploit_ready"))
        and state in LOCAL_WORK_STATES
    )


def _active_exclusive_claims(
    *,
    platform: str,
    event: str,
    worker_id: str,
) -> dict[str, dict[str, object]]:
    claims = list_claims(platform=platform, event=event, include_stale=False)
    active: dict[str, dict[str, object]] = {}
    for claim in claims:
        if bool(claim.get("shared")):
            continue
        if claim.get("worker_id") == worker_id:
            continue
        challenge_id = str(claim.get("challenge_id") or "")
        if challenge_id:
            active[challenge_id] = claim
    return active


def _run_dir_text(item: dict[str, object]) -> str:
    run_dir = resolve_run_dir_for_item(item)
    return display_path(run_dir) if run_dir else "<run-dir>"


def _suggested_command(action: str, item: dict[str, object], policy: PlatformPolicy, worker_id: str, require_verifier: bool) -> str:
    challenge_id = str(item.get("challenge_id") or "")
    run_id = str(item.get("run_id") or "")
    if action == "acquire_remote":
        return (
            "python3 scripts/resource_acquire.py "
            f"--platform {policy.platform} --event {policy.event} "
            f"--challenge-id {challenge_id} --run-id {run_id} --worker-id {worker_id}"
        )
    if action == "join_remote_as_helper":
        return (
            "python3 scripts/resource_acquire.py "
            f"--platform {policy.platform} --event {policy.event} "
            f"--challenge-id {challenge_id} --run-id {run_id} --worker-id {worker_id} --mode helper"
        )
    if action == "verify_solution":
        return f"python3 scripts/verify_run.py --run-dir {_run_dir_text(item)} --mode command --command '<verify command>' --local"
    if action == "finalize_challenge":
        status = str(item.get("state") or "manual_stop")
        verifier = " --require-verifier" if require_verifier and status == "solved" else ""
        return f"python3 scripts/challenge_finalize.py --run-dir {_run_dir_text(item)} --status {status}{verifier}"
    return ""


def _decision(
    *,
    action: str,
    item: dict[str, object] | None,
    policy: PlatformPolicy,
    worker_id: str,
    reason: str,
    require_verifier: bool,
    primary_lease_id: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "action": action,
        "challenge_id": item.get("challenge_id") if item else None,
        "run_id": item.get("run_id") if item else None,
        "reason": reason,
        "worker_id": worker_id,
        "claimed": False,
        "priority_score": item.get("priority_score") if item else None,
    }
    if item:
        result["queue_id"] = item.get("queue_id")
        result["status"] = item.get("state")
        command = _suggested_command(action, item, policy, worker_id, require_verifier)
        if command:
            result["suggested_command"] = command
    if primary_lease_id:
        result["primary_lease_id"] = primary_lease_id
    return result


def _record_action_selected(policy: PlatformPolicy, decision: dict[str, object], *, worker_id: str) -> None:
    action = str(decision.get("action") or "wait")
    append_queue_event(
        event_type="worker_action_selected",
        queue_id=str(decision.get("queue_id") or ""),
        challenge_id=str(decision.get("challenge_id") or ""),
        run_id=str(decision.get("run_id") or ""),
        platform=policy.platform,
        event=policy.event,
        worker_id=worker_id,
        reason=str(decision.get("reason") or ""),
        public_safe_metadata={
            "action": action,
            "priority_score": decision.get("priority_score"),
            "claimed": bool(decision.get("claimed")),
        },
    )
    if action in {"wait", "no_work"}:
        append_queue_event(
            event_type="worker_wait",
            platform=policy.platform,
            event=policy.event,
            worker_id=worker_id,
            reason=str(decision.get("reason") or ""),
            public_safe_metadata={"action": action},
        )


def choose_worker_action(
    policy: PlatformPolicy,
    *,
    worker_id: str | None = None,
    allow_helper: bool = True,
    require_verifier: bool = False,
    claim: bool = True,
) -> dict[str, object]:
    worker = worker_id or make_worker_id()
    reclaim_stale_claims(platform=policy.platform, event=policy.event, worker_id=worker, dry_run=False)
    items = [item for item in list_queue_items(platform=policy.platform, event=policy.event) if not _is_finalized(item)]
    active_other = _active_exclusive_claims(platform=policy.platform, event=policy.event, worker_id=worker)

    ended = [
        item
        for item in items
        if str(item.get("state") or "") in {"solved", "abandoned"} and str(item.get("challenge_id") or "") not in active_other
    ]
    for item in ended:
        state = str(item.get("state") or "")
        if state == "solved" and require_verifier and not _verifier_success(item):
            decision = _decision(
                action="verify_solution",
                item=item,
                policy=policy,
                worker_id=worker,
                reason="require_verifier_missing",
                require_verifier=require_verifier,
            )
            break
        decision = _decision(
            action="finalize_challenge",
            item=item,
            policy=policy,
            worker_id=worker,
            reason="end_state_requires_finalization",
            require_verifier=require_verifier,
        )
        break
    else:
        decision = {}

    if not decision:
        remote_available = _remote_capacity_available(policy)
        remote_candidates = [
            item
            for item in items
            if _remote_candidate(item) and str(item.get("challenge_id") or "") not in active_other
        ]
        if remote_available and remote_candidates:
            local_ready = [item for item in remote_candidates if item.get("local_exploit_ready") or item.get("state") == "local_exploit_ready"]
            item = (local_ready or remote_candidates)[0]
            decision = _decision(
                action="acquire_remote",
                item=item,
                policy=policy,
                worker_id=worker,
                reason="remote_capacity_available",
                require_verifier=require_verifier,
            )
        else:
            local_candidates = [
                item
                for item in items
                if _local_candidate(item) and str(item.get("challenge_id") or "") not in active_other
            ]
            if local_candidates:
                decision = _decision(
                    action="do_local_work",
                    item=local_candidates[0],
                    policy=policy,
                    worker_id=worker,
                    reason="remote_unavailable_local_prework" if remote_candidates else "local_work_available",
                    require_verifier=require_verifier,
                )
            elif allow_helper and policy.resources.remote_server.sharing.allowed:
                active_primary = [
                    lease
                    for lease in list_leases(platform=policy.platform, event=policy.event, resource_type=REMOTE_SERVER)
                    if lease.get("role") == "primary"
                ]
                primary_by_challenge = {
                    str(lease.get("challenge_id") or ""): lease
                    for lease in active_primary
                    if lease.get("challenge_id")
                }
                helper_candidates = [
                    item
                    for item in items
                    if str(item.get("challenge_id") or "") in primary_by_challenge
                    and str(item.get("state") or "") not in TERMINAL_STATES
                ]
                if helper_candidates:
                    item = helper_candidates[0]
                    primary = primary_by_challenge[str(item.get("challenge_id") or "")]
                    decision = _decision(
                        action="join_remote_as_helper",
                        item=item,
                        policy=policy,
                        worker_id=worker,
                        reason="sharing_allowed_active_remote",
                        require_verifier=require_verifier,
                        primary_lease_id=str(primary.get("lease_id") or ""),
                    )
                else:
                    decision = _decision(
                        action="wait" if items else "no_work",
                        item=None,
                        policy=policy,
                        worker_id=worker,
                        reason="no_helper_candidate" if items else "queue_empty",
                        require_verifier=require_verifier,
                    )
            else:
                reason = "active_claim_exists" if items and active_other else "no_remote_capacity_no_local_work"
                decision = _decision(
                    action="wait" if items else "no_work",
                    item=None,
                    policy=policy,
                    worker_id=worker,
                    reason=reason if items else "queue_empty",
                    require_verifier=require_verifier,
                )

    if claim and decision.get("challenge_id") and decision.get("action") not in {"wait", "no_work"}:
        item = next(
            (
                candidate
                for candidate in items
                if candidate.get("challenge_id") == decision.get("challenge_id")
                and candidate.get("run_id") == decision.get("run_id")
            ),
            None,
        )
        if item:
            claim_result = claim_queue_item(
                item,
                worker_id=worker,
                action=str(decision.get("action") or ""),
                shared=str(decision.get("action") or "") == "join_remote_as_helper",
            )
            decision["claimed"] = bool(claim_result.get("claimed"))
            decision["claim"] = claim_result.get("claim")
            if not claim_result.get("ok"):
                decision = _decision(
                    action="wait",
                    item=None,
                    policy=policy,
                    worker_id=worker,
                    reason=str(claim_result.get("reason") or "claim_failed"),
                    require_verifier=require_verifier,
                )
                decision["claim_error"] = claim_result

    _record_action_selected(policy, decision, worker_id=worker)
    return decision


def worker_status(*, platform: str | None = None, event: str | None = None) -> dict[str, object]:
    claims = list_claims(platform=platform, event=event, include_stale=True)
    active_claims = [claim for claim in claims if not is_stale_claim(claim)]
    stale_claims = [claim for claim in claims if is_stale_claim(claim)]
    leases = list_leases(platform=platform, event=event, resource_type=REMOTE_SERVER, include_stale=True)
    active_leases = list_leases(platform=platform, event=event, resource_type=REMOTE_SERVER, include_stale=False)
    stale_leases = detect_stale_leases(platform=platform, event=event, resource_type=REMOTE_SERVER)
    queue_items = list_queue_items(platform=platform, event=event)
    queue_by_state = Counter(str(item.get("state") or "unknown") for item in queue_items)
    action_counts = Counter(str(claim.get("action") or "unknown") for claim in active_claims)
    return {
        "ok": True,
        "worker_root": display_path(worker_root()),
        "active_claims_count": len(active_claims),
        "stale_claims_count": len(stale_claims),
        "active_leases_count": len(active_leases),
        "stale_leases_count": len(stale_leases),
        "lease_records_count": len(leases),
        "queue_items_count": len(queue_items),
        "queue_by_state": dict(sorted(queue_by_state.items())),
        "worker_actions": dict(sorted(action_counts.items())),
        "claims": [public_claim_summary(claim) for claim in active_claims + stale_claims],
    }
