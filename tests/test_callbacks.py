from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from conftest import parse_json_output
from ctf_solver_core.callbacks import CallbackError, is_inside_repo, validate_local_only_root


@pytest.fixture(autouse=True)
def _stop_callback_daemon(run_cli):
    yield
    run_cli(["scripts/callback_daemon.py", "stop"], check=False)


def _start_listener(run_cli, *, run_id: str = "RUN_CB") -> dict[str, object]:
    return parse_json_output(
        run_cli(
            [
                "scripts/callback_start.py",
                "--run-id",
                run_id,
                "--challenge-id",
                "CHAL_CB",
                "--json",
            ]
        )
    )


def _request(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None) -> int:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def test_callback_roots_are_local_only_in_tests(temp_ctf_env) -> None:
    assert not is_inside_repo(temp_ctf_env.callbacks)
    assert not is_inside_repo(temp_ctf_env.callbackd)
    with pytest.raises(CallbackError, match="callback_root_inside_repo"):
        validate_local_only_root(temp_ctf_env.solver_repo / "callbacks-test", label="callback_root")


def test_start_listener_and_get_url(run_cli) -> None:
    started = _start_listener(run_cli)
    assert started["ok"] is True
    listener_id = str(started["listener_id"])
    assert str(started["local_url"]).startswith("http://127.0.0.1:")

    url = parse_json_output(run_cli(["scripts/callback_url.py", "--listener-id", listener_id, "--json"]))
    assert url["url"] == started["local_url"]


def test_get_hit_redacts_query_and_headers(run_cli) -> None:
    started = _start_listener(run_cli)
    listener_id = str(started["listener_id"])
    marker = "callbackvalue"
    query = urllib.parse.urlencode({"to" + "ken": marker, "sec" + "ret": marker, "ok": "1"})
    url = f"{started['local_url']}?{query}"
    status = _request(
        url,
        headers={
            "Authorization": "Bearer " + marker,
            "Cookie": "sid=" + marker,
            "X-Api-Key": marker,
        },
    )
    assert status == 204

    hits = parse_json_output(run_cli(["scripts/callback_hits.py", "--listener-id", listener_id, "--json"]))
    rendered = json.dumps(hits, ensure_ascii=False, sort_keys=True)
    assert hits["count"] == 1
    assert marker not in rendered
    hit = hits["hits"][0]
    assert hit["headers"]["Authorization"] == "<REDACTED>"
    assert hit["headers"]["Cookie"] == "<REDACTED>"
    assert hit["headers"]["X-Api-Key"] == "<REDACTED>"
    query_values = {item["key"]: item["value"] for item in hit["query"]}
    assert query_values["to" + "ken"] == "<REDACTED>"
    assert query_values["sec" + "ret"] == "<REDACTED>"
    assert query_values["ok"] == "1"


def test_post_body_preview_redacts_sensitive_values(run_cli) -> None:
    started = _start_listener(run_cli)
    listener_id = str(started["listener_id"])
    marker = "formvalue"
    body = urllib.parse.urlencode({"to" + "ken": marker, "sec" + "ret": marker, "note": "hello"}).encode()
    status = _request(
        str(started["local_url"]),
        method="POST",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 204

    hits = parse_json_output(run_cli(["scripts/callback_hits.py", "--listener-id", listener_id, "--json"]))
    rendered = json.dumps(hits, ensure_ascii=False, sort_keys=True)
    assert marker not in rendered
    preview = str(hits["hits"][0]["body_preview"])
    assert "<REDACTED>" in preview
    assert "note=hello" in preview


def test_callback_wait_success_and_timeout(run_cli) -> None:
    started = _start_listener(run_cli)
    listener_id = str(started["listener_id"])
    url = str(started["local_url"]) + "/wait-ok"
    timer = threading.Timer(0.2, lambda: _request(url))
    timer.start()
    try:
        waited = parse_json_output(
            run_cli(
                [
                    "scripts/callback_wait.py",
                    "--listener-id",
                    listener_id,
                    "--timeout-sec",
                    "3",
                    "--pattern",
                    "wait-ok",
                    "--json",
                ]
            )
        )
    finally:
        timer.cancel()
    assert waited["ok"] is True
    assert waited["timed_out"] is False

    empty = _start_listener(run_cli, run_id="RUN_EMPTY")
    timed_out = parse_json_output(
        run_cli(
            [
                "scripts/callback_wait.py",
                "--listener-id",
                str(empty["listener_id"]),
                "--timeout-sec",
                "0.2",
                "--json",
            ],
            check=False,
        )
    )
    assert timed_out["ok"] is False
    assert timed_out["timed_out"] is True


def test_callback_list_filters_by_run_id(run_cli) -> None:
    first = _start_listener(run_cli, run_id="RUN_ONE")
    second = _start_listener(run_cli, run_id="RUN_TWO")
    listed = parse_json_output(run_cli(["scripts/callback_list.py", "--run-id", "RUN_ONE", "--json"]))
    ids = [item["listener_id"] for item in listed["listeners"]]
    assert ids == [first["listener_id"]]
    assert second["listener_id"] not in ids


def test_challenge_finalize_closes_run_listeners(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Callback Finalize",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    started = _start_listener(run_cli, run_id=run_id)
    assert _request(str(started["local_url"]) + "/finalize") == 204

    finalized = parse_json_output(
        run_cli(["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "manual_stop"])
    )
    assert finalized["callbacks"]["closed_callback_listener_count"] == 1
    final_record = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
    assert final_record["closed_callback_listener_count"] == 1
    assert final_record["callback_hit_count"] == 1

    listed = parse_json_output(run_cli(["scripts/callback_list.py", "--run-id", run_id, "--include-closed", "--json"]))
    assert listed["listeners"][0]["status"] == "closed"


def test_web_payload_helper_returns_snippets(run_cli) -> None:
    url = "http://127.0.0.1:9000/LISTENER"
    result = parse_json_output(run_cli(["scripts/web_payload_helper.py", "--callback-url", url, "--json"]))
    snippets = result["snippets"]
    assert url in snippets["img_src"]
    assert url in snippets["script_fetch"]
    assert url in snippets["fetch_post"]
    assert url in snippets["css_url"]
    assert url in snippets["markdown_image"]


def test_verify_run_can_use_callback_hit_summary(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Callback Verify",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    run_dir = Path(str(init["run_dir"]))
    started = _start_listener(run_cli, run_id=str(init["run_id"]))
    assert _request(str(started["local_url"]) + "/verified") == 204

    verified = parse_json_output(
        run_cli(
            [
                "scripts/verify_run.py",
                "--run-dir",
                str(run_dir),
                "--mode",
                "manual",
                "--callback-listener-id",
                str(started["listener_id"]),
                "--callback-pattern",
                "verified",
                "--callback-min-hits",
                "1",
                "--local",
            ]
        )
    )
    assert verified["success"] is True
    assert verified["mode"] == "manual"
    assert "matched_count" in verified["output_preview"]


def test_metrics_public_safe_with_callback_fields(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Callback Metrics",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    started = _start_listener(run_cli, run_id=run_id)
    assert _request(str(started["local_url"]) + "/metrics") == 204
    finalized = parse_json_output(
        run_cli(
            [
                "scripts/challenge_finalize.py",
                "--run-dir",
                str(run_dir),
                "--status",
                "manual_stop",
                "--update-metrics",
            ]
        )
    )
    assert finalized["metrics"]["record"]["callback_hit_count"] == 1
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK" in check.stdout


def test_secret_scan_strict_passes(run_cli) -> None:
    result = run_cli(["scripts/secret_scan.py", "--strict"])
    assert "OK" in result.stdout
