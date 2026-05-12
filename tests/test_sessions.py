from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import parse_json_output


@pytest.fixture(autouse=True)
def _stop_session_daemon(run_cli):
    yield
    run_cli(["scripts/session_daemon.py", "stop"], check=False)


def _start(run_cli, kind: str, *extra: str) -> dict[str, object]:
    return parse_json_output(run_cli(["scripts/session_start.py", kind, "--json", *extra]))


def test_shell_session_write_expect_close(run_cli) -> None:
    started = _start(run_cli, "shell", "--run-id", "RUN_A")
    session_id = str(started["session"]["session_id"])

    run_cli(["scripts/session_write.py", session_id, "echo hello", "--json"])
    expected = parse_json_output(
        run_cli(["scripts/session_expect.py", session_id, "hello", "--timeout-ms", "1500", "--json"])
    )
    assert expected["matched"] == "hello"
    assert "hello" in str(expected["output"])

    closed = parse_json_output(run_cli(["scripts/session_close.py", session_id, "--json"]))
    assert closed["status"] == "closed"


def test_python_session_repl(run_cli) -> None:
    started = _start(run_cli, "python", "--run-id", "RUN_PY")
    session_id = str(started["session"]["session_id"])

    run_cli(["scripts/session_write.py", session_id, "print(1+1)", "--json"])
    expected = parse_json_output(
        run_cli(["scripts/session_expect.py", session_id, "2", "--timeout-ms", "1500", "--json"])
    )
    assert expected["matched"] == "2"
    run_cli(["scripts/session_close.py", session_id, "--json"])


def test_expect_timeout_is_clean_and_bounded(run_cli) -> None:
    started = _start(run_cli, "shell")
    session_id = str(started["session"]["session_id"])

    result = parse_json_output(
        run_cli(
            [
                "scripts/session_expect.py",
                session_id,
                "pattern-that-will-not-appear",
                "--timeout-ms",
                "150",
                "--max-bytes",
                "128",
                "--json",
            ],
            check=False,
        )
    )
    assert result["matched"] is None
    assert result["timed_out"] is True
    assert len(str(result["output"]).encode("utf-8")) <= 128
    run_cli(["scripts/session_close.py", session_id, "--json"])


def test_session_list_filters_and_closed_visibility(run_cli) -> None:
    a = _start(run_cli, "shell", "--run-id", "RUN_A")
    b = _start(run_cli, "shell", "--run-id", "RUN_B")
    session_a = str(a["session"]["session_id"])
    session_b = str(b["session"]["session_id"])

    listed = parse_json_output(run_cli(["scripts/session_list.py", "--run-id", "RUN_A", "--json"]))
    ids = {str(item["session_id"]) for item in listed["sessions"]}
    assert session_a in ids
    assert session_b not in ids

    run_cli(["scripts/session_close.py", session_a, "--json"])
    open_only = parse_json_output(run_cli(["scripts/session_list.py", "--run-id", "RUN_A", "--json"]))
    assert open_only["sessions"] == []

    with_closed = parse_json_output(
        run_cli(["scripts/session_list.py", "--run-id", "RUN_A", "--include-closed", "--json"])
    )
    assert {str(item["session_id"]) for item in with_closed["sessions"]} == {session_a}
    run_cli(["scripts/session_close.py", session_b, "--json"])


def test_finalize_closes_run_sessions(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Session Finalize",
                "--category",
                "misc",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    started = _start(run_cli, "shell", "--run-id", run_id)
    session_id = str(started["session"]["session_id"])

    finalized = parse_json_output(
        run_cli(["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "manual_stop"])
    )
    assert finalized["sessions"]["closed_session_count"] == 1
    final_record = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
    assert final_record["closed_session_count"] == 1

    listed = parse_json_output(
        run_cli(["scripts/session_list.py", "--run-id", run_id, "--include-closed", "--json"])
    )
    statuses = {str(item["session_id"]): item["status"] for item in listed["sessions"]}
    assert statuses[session_id] == "closed"


def test_daemon_recovery_from_dead_status_file(run_cli, temp_ctf_env) -> None:
    status_file = temp_ctf_env.sessiond / "sessiond.json"
    status_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "host": "127.0.0.1",
                "port": 9,
                "token": "dummy-token",
                "pid": 999999,
                "created_at": "2000-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    started = _start(run_cli, "shell")
    session_id = str(started["session"]["session_id"])
    assert session_id
    run_cli(["scripts/session_close.py", session_id, "--json"])
