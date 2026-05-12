from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from conftest import parse_json_output
from ctf_solver_core.paths import worker_root
from ctf_solver_core.platforms import get_platform_policy
from ctf_solver_core.queue import list_queue_events
from ctf_solver_core.resources import acquire_remote_server
from ctf_solver_core.schemas import read_json
from ctf_solver_core.worker import list_claims


def _old_timestamp() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _queue_update(
    run_cli,
    challenge_id: str,
    run_id: str,
    state: str,
    *,
    local_capable: bool = True,
    remote_required: bool = True,
    ready: bool = False,
) -> None:
    run_cli(
        [
            "scripts/queue_update.py",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--challenge-id",
            challenge_id,
            "--run-id",
            run_id,
            "--category",
            "web",
            "--state",
            state,
            "--local-capable",
            "true" if local_capable else "false",
            "--remote-required",
            "true" if remote_required else "false",
            "--local-exploit-ready",
            "true" if ready else "false",
            "--confidence",
            "0.8",
            "--destructive-risk",
            "0.1",
        ]
    )


def _make_run(run_cli, name: str) -> dict[str, object]:
    return parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                name,
                "--category",
                "web",
                "--json",
            ]
        )
    )


def test_worker_claim_prevents_duplicate_and_stale_reclaims(temp_ctf_env, run_cli) -> None:
    _queue_update(run_cli, "challenge-A", "run-A", "downloaded", remote_required=False)

    first = parse_json_output(
        run_cli(["scripts/worker_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "worker-1"])
    )
    assert first["action"] == "do_local_work"
    assert first["claimed"] is True
    assert first["challenge_id"] == "challenge-A"

    blocked = parse_json_output(
        run_cli(["scripts/worker_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "worker-2"])
    )
    assert blocked["action"] == "wait"
    assert blocked["reason"] == "active_claim_exists"

    claim_path = next(worker_root().glob("*.json"))
    claim = read_json(claim_path)
    claim["heartbeat_at"] = _old_timestamp()
    claim["stale_after_sec"] = 1
    claim_path.write_text(json.dumps(claim, indent=2, sort_keys=True), encoding="utf-8")

    reclaimed = parse_json_output(
        run_cli(["scripts/worker_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "worker-2"])
    )
    assert reclaimed["action"] == "do_local_work"
    assert reclaimed["claimed"] is True
    claims = list_claims(platform="thcon", event="THCON", include_stale=True)
    assert len(claims) == 1
    assert claims[0]["worker_id"] == "worker-2"
    events = {event["event_type"] for event in list_queue_events(platform="thcon", event="THCON")}
    assert {"worker_claim_stale_detected", "worker_claim_stale_reclaimed"} <= events


def test_finalize_releases_worker_claim_and_records_events(temp_ctf_env, run_cli) -> None:
    init = _make_run(run_cli, "Worker Finalize")
    challenge_id = str(init["challenge_id"])
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    _queue_update(run_cli, challenge_id, run_id, "downloaded", remote_required=False)

    claimed = parse_json_output(
        run_cli(["scripts/worker_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "worker-final"])
    )
    assert claimed["claimed"] is True
    assert list_claims(platform="thcon", event="THCON")

    finalized = parse_json_output(
        run_cli(["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "manual_stop"])
    )
    assert finalized["status"] == "manual_stop"
    assert finalized["worker_claim_release"]["released_count"] == 1
    assert not list_claims(platform="thcon", event="THCON", include_stale=True)

    events = {event["event_type"] for event in list_queue_events(platform="thcon", event="THCON")}
    assert {"worker_claimed", "worker_action_selected", "worker_claim_released"} <= events


def test_worker_action_policy_local_first_remote_ready_and_verifier(temp_ctf_env, run_cli) -> None:
    policy = get_platform_policy("thcon", "THCON")
    blocker = acquire_remote_server(policy, "blocker", "run-blocker", worker_id="blocker")
    assert blocker["ok"] is True
    _queue_update(run_cli, "challenge-local", "run-local", "downloaded", remote_required=True)

    local = parse_json_output(
        run_cli(["scripts/worker_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "worker-local"])
    )
    assert local["action"] == "do_local_work"
    assert local["challenge_id"] == "challenge-local"

    temp_ctf_env.write_platform_config(max_active=2)
    _queue_update(run_cli, "challenge-ready", "run-ready", "local_exploit_ready", ready=True)
    ready = parse_json_output(
        run_cli(["scripts/worker_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "worker-ready"])
    )
    assert ready["action"] == "acquire_remote"
    assert ready["challenge_id"] == "challenge-ready"

    _queue_update(run_cli, "challenge-solved", "run-solved", "solved", remote_required=False)
    solved = parse_json_output(
        run_cli(
            [
                "scripts/worker_next.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--worker-id",
                "worker-verify",
                "--require-verifier",
                "true",
            ]
        )
    )
    assert solved["action"] == "verify_solution"
    assert solved["challenge_id"] == "challenge-solved"


def test_finalized_item_not_selected_and_status_counts(temp_ctf_env, run_cli) -> None:
    _queue_update(run_cli, "challenge-finalized", "run-finalized", "finalized", remote_required=False)
    _queue_update(run_cli, "challenge-active", "run-active", "downloaded", remote_required=False)
    selected = parse_json_output(
        run_cli(["scripts/worker_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "worker-status"])
    )
    assert selected["action"] == "do_local_work"
    assert selected["challenge_id"] == "challenge-active"

    status = parse_json_output(
        run_cli(["scripts/worker_status.py", "--platform", "thcon", "--event", "THCON", "--show-claims", "--json"])
    )
    assert status["active_claims_count"] == 1
    assert status["stale_claims_count"] == 0
    assert status["queue_by_state"]["finalized"] == 1
    assert status["worker_actions"]["do_local_work"] == 1
