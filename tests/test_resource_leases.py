from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from conftest import parse_json_output
from ctf_solver_core.paths import lease_root
from ctf_solver_core.platforms import get_platform_policy
from ctf_solver_core.resources import (
    REMOTE_SERVER,
    acquire_remote_server,
    detect_stale_leases,
    reclaim_stale_leases,
    release_lease,
)
from ctf_solver_core.schemas import read_json


def _old_timestamp() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_stale_primary(lease_id: str, challenge_id: str, run_id: str) -> None:
    old = _old_timestamp()
    lease_root().mkdir(parents=True, exist_ok=True)
    (lease_root() / f"{lease_id}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "lease_id": lease_id,
                "platform": "thcon",
                "event": "THCON",
                "resource_type": REMOTE_SERVER,
                "challenge_id": challenge_id,
                "run_id": run_id,
                "owner_worker_id": "dead-worker",
                "role": "primary",
                "acquired_at": old,
                "heartbeat_at": old,
                "heartbeat_interval_sec": 1,
                "stale_after_sec": 1,
                "renewed_at": None,
                "renewal_count": 0,
                "expires_at": None,
                "shared": False,
                "metadata": {},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_remote_lease_heartbeat_reclaim_release_and_helper_policy(temp_ctf_env, run_cli) -> None:
    policy = get_platform_policy("thcon", "THCON")
    acquired_a = parse_json_output(
        run_cli(
            [
                "scripts/resource_acquire.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-id",
                "challenge-A",
                "--run-id",
                "run-A",
                "--worker-id",
                "worker-A",
            ]
        )
    )
    assert acquired_a["ok"] is True
    lease_a = acquired_a["lease"]
    lease_a_id = str(lease_a["lease_id"])

    acquired_b = acquire_remote_server(policy, "challenge-B", "run-B", worker_id="worker-B")
    assert acquired_b["ok"] is False
    assert acquired_b["reason"] == "max_active_leases_reached"

    heartbeat = parse_json_output(
        run_cli(
            [
                "scripts/resource_heartbeat.py",
                "--lease-id",
                lease_a_id,
                "--worker-id",
                "worker-A",
                "--once",
                "--json",
            ]
        )
    )
    assert heartbeat["ok"] is True
    assert heartbeat["updated_count"] == 1

    _write_stale_primary("stale-primary", "challenge-stale", "run-stale")
    stale = detect_stale_leases(platform="thcon", event="THCON", resource_type=REMOTE_SERVER)
    assert [item["lease_id"] for item in stale] == ["stale-primary"]

    dry = parse_json_output(run_cli(["scripts/resource_reclaim_stale.py", "--dry-run", "--json"]))
    assert dry["stale_count"] == 1
    assert "released_at" not in read_json(lease_root() / "stale-primary.json")

    applied = parse_json_output(run_cli(["scripts/resource_reclaim_stale.py", "--apply", "--json"]))
    assert applied["reclaimed_count"] == 1
    stale_record = read_json(lease_root() / "stale-primary.json")
    assert stale_record["release_reason"] == "stale_reclaimed"
    assert "released_at" not in read_json(lease_root() / f"{lease_a_id}.json")

    helper_denied = acquire_remote_server(
        policy,
        "challenge-A",
        "run-helper-denied",
        worker_id="helper-denied",
        mode="helper",
    )
    assert helper_denied["ok"] is False
    assert helper_denied["reason"] == "sharing_not_allowed"

    released_a = release_lease(lease_id=lease_a_id, release_reason="test_release")
    assert released_a["released_count"] == 1
    assert read_json(lease_root() / f"{lease_a_id}.json")["release_reason"] == "test_release"

    temp_ctf_env.write_platform_config(sharing=True)
    shared_policy = get_platform_policy("thcon", "THCON")
    primary = acquire_remote_server(shared_policy, "challenge-C", "run-C", worker_id="primary-C")
    assert primary["ok"] is True
    helper = acquire_remote_server(shared_policy, "challenge-C", "run-helper", worker_id="helper-C", mode="helper")
    assert helper["ok"] is True
    assert helper["lease"]["primary_lease_id"] == primary["lease"]["lease_id"]

    release_lease(lease_id=str(primary["lease"]["lease_id"]), release_reason="primary_done")
    helper_after_release = acquire_remote_server(
        shared_policy,
        "challenge-C",
        "run-helper-after-release",
        worker_id="helper-after",
        mode="helper",
    )
    assert helper_after_release["ok"] is False
    assert helper_after_release["reason"] == "no_primary_lease_for_helper"

    _write_stale_primary("stale-shared-primary", "challenge-S", "run-S")
    helper_after_stale = acquire_remote_server(
        shared_policy,
        "challenge-S",
        "run-helper-stale",
        worker_id="helper-stale",
        mode="helper",
    )
    assert helper_after_stale["ok"] is False
    assert helper_after_stale["reason"] == "no_primary_lease_for_helper"
    assert read_json(lease_root() / "stale-shared-primary.json")["release_reason"] == "stale_reclaimed"
