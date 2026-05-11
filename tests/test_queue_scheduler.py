from __future__ import annotations

from conftest import parse_json_output
from ctf_solver_core.platforms import get_platform_policy
from ctf_solver_core.queue import list_queue_items
from ctf_solver_core.resources import acquire_remote_server, release_lease


def _queue_update(run_cli, challenge_id: str, run_id: str, state: str, *, ready: bool = False) -> None:
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
            "true",
            "--remote-required",
            "true",
            "--local-exploit-ready",
            "true" if ready else "false",
            "--confidence",
            "0.7",
            "--destructive-risk",
            "0.1",
            "--worker-id",
            "queue-worker",
        ]
    )


def test_local_first_priority_and_queue_history(temp_ctf_env, run_cli) -> None:
    policy = get_platform_policy("thcon", "THCON")
    blocker = acquire_remote_server(policy, "challenge-blocker", "run-blocker", worker_id="blocker")
    assert blocker["ok"] is True

    _queue_update(run_cli, "challenge-A", "run-A", "downloaded")
    _queue_update(run_cli, "challenge-A", "run-A", "local_analysis")
    _queue_update(run_cli, "challenge-B", "run-B", "local_exploit_ready", ready=True)

    items = list_queue_items(platform="thcon", event="THCON")
    by_challenge = {item["challenge_id"]: item for item in items}
    assert by_challenge["challenge-B"]["priority_score"] > by_challenge["challenge-A"]["priority_score"]

    blocked_decision = parse_json_output(
        run_cli(["scripts/queue_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "queue-worker"])
    )
    assert blocked_decision["action"] == "do_local_work"
    assert blocked_decision["challenge_id"] == "challenge-A"

    release_lease(lease_id=str(blocker["lease"]["lease_id"]), release_reason="queue_test_release")
    ready_decision = parse_json_output(
        run_cli(["scripts/queue_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "queue-worker"])
    )
    assert ready_decision["action"] == "acquire_remote"
    assert ready_decision["challenge_id"] == "challenge-B"

    history = parse_json_output(run_cli(["scripts/queue_history.py", "--tail", "50", "--json"]))
    event_types = {event["event_type"] for event in history["events"]}
    assert {"queue_item_created", "state_changed", "scheduler_decision", "remote_blocked"} <= event_types


def test_helper_scheduler_respects_sharing_policy(temp_ctf_env, run_cli) -> None:
    temp_ctf_env.write_platform_config(sharing=True)
    shared_policy = get_platform_policy("thcon", "THCON")
    primary = acquire_remote_server(shared_policy, "challenge-C", "run-C", worker_id="primary-C")
    assert primary["ok"] is True

    run_cli(
        [
            "scripts/queue_update.py",
            "--platform",
            "thcon",
            "--event",
            "THCON",
            "--challenge-id",
            "challenge-C",
            "--run-id",
            "run-C",
            "--category",
            "web",
            "--state",
            "remote_testing",
            "--local-capable",
            "false",
            "--remote-required",
            "false",
            "--local-exploit-ready",
            "false",
            "--confidence",
            "0.5",
            "--destructive-risk",
            "0.1",
        ]
    )

    helper_decision = parse_json_output(
        run_cli(["scripts/queue_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "helper-worker"])
    )
    assert helper_decision["action"] == "join_remote_as_helper"
    assert helper_decision["primary_lease_id"] == primary["lease"]["lease_id"]

    temp_ctf_env.write_platform_config(sharing=False)
    exclusive_decision = parse_json_output(
        run_cli(["scripts/queue_next.py", "--platform", "thcon", "--event", "THCON", "--worker-id", "exclusive-worker"])
    )
    assert exclusive_decision["action"] == "wait"
