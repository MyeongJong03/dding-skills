from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from conftest import REPO_ROOT, parse_json_output
from ctf_solver_core.paths import is_inside_repo


@pytest.fixture(autouse=True)
def _stop_daemons(run_cli):
    yield
    run_cli(["scripts/browser_daemon.py", "stop"], check=False)
    run_cli(["scripts/callback_daemon.py", "stop"], check=False)


def _request(url: str, *, method: str = "GET", body: bytes | None = None) -> int:
    request = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _init_workflow(run_cli, run_id: str = "RUN_WEBWF") -> dict[str, object]:
    return parse_json_output(
        run_cli(
            [
                "scripts/web_workflow_init.py",
                "--run-id",
                run_id,
                "--challenge-id",
                "CHAL_WEBWF",
                "--start-callback",
                "--json",
            ]
        )
    )


def test_web_workflow_init_with_callback_creates_listener(run_cli) -> None:
    result = _init_workflow(run_cli)
    workflow = result["workflow"]
    assert result["ok"] is True
    assert workflow["workflow_id"]
    assert workflow["callback_listener_id"]
    assert str(workflow["local_callback_url"]).startswith("http://127.0.0.1:")


def test_web_payload_generate_uses_workflow_callback_url(run_cli) -> None:
    workflow = _init_workflow(run_cli)["workflow"]
    result = parse_json_output(
        run_cli(
            [
                "scripts/web_payload_generate.py",
                "--workflow-id",
                str(workflow["workflow_id"]),
                "--types",
                "img,script-fetch,css-url",
                "--json",
            ]
        )
    )
    rendered = json.dumps(result, ensure_ascii=False)
    assert result["count"] == 3
    assert str(workflow["local_callback_url"]) in rendered
    assert {item["type"] for item in result["payloads"]} == {"img", "script-fetch", "css-url"}


def test_callback_probe_waits_for_local_hit_and_records_evidence(run_cli) -> None:
    workflow = _init_workflow(run_cli)["workflow"]
    workflow_id = str(workflow["workflow_id"])
    url = str(workflow["local_callback_url"]) + "/probe-ok"
    timer = threading.Timer(0.2, lambda: _request(url))
    timer.start()
    try:
        result = parse_json_output(
            run_cli(
                [
                    "scripts/web_callback_probe.py",
                    "--workflow-id",
                    workflow_id,
                    "--wait-timeout-sec",
                    "3",
                    "--pattern",
                    "probe-ok",
                    "--json",
                ]
            )
        )
    finally:
        timer.cancel()
    assert result["ok"] is True
    assert result["evidence"]["matched_count"] == 1


def test_evidence_collect_writes_outside_repo(run_cli, temp_ctf_env) -> None:
    workflow = _init_workflow(run_cli)["workflow"]
    workflow_id = str(workflow["workflow_id"])
    assert _request(str(workflow["local_callback_url"]) + "/evidence") == 204
    parse_json_output(
        run_cli(
            [
                "scripts/web_callback_probe.py",
                "--workflow-id",
                workflow_id,
                "--wait-timeout-sec",
                "1",
                "--pattern",
                "evidence",
                "--json",
            ]
        )
    )
    result = parse_json_output(
        run_cli(
            [
                "scripts/web_evidence_collect.py",
                "--workflow-id",
                workflow_id,
                "--include-callback-summary",
                "--json",
            ]
        )
    )
    evidence_path = temp_ctf_env.web_workflows / workflow_id / "evidence.json"
    summary_path = temp_ctf_env.web_workflows / workflow_id / "summary.md"
    assert result["ok"] is True
    assert evidence_path.is_file()
    assert summary_path.is_file()
    assert REPO_ROOT not in evidence_path.parents
    assert temp_ctf_env.solver_repo not in evidence_path.parents
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["callback_hit_count"] == 1
    assert not is_inside_repo(evidence_path)


def test_workflow_close_closes_callback_listener(run_cli) -> None:
    workflow = _init_workflow(run_cli)["workflow"]
    workflow_id = str(workflow["workflow_id"])
    listener_id = str(workflow["callback_listener_id"])
    closed = parse_json_output(run_cli(["scripts/web_workflow_close.py", "--workflow-id", workflow_id, "--json"]))
    assert closed["status"] == "closed"
    listeners = parse_json_output(
        run_cli(["scripts/callback_list.py", "--include-closed", "--run-id", "RUN_WEBWF", "--json"])
    )
    matching = [item for item in listeners["listeners"] if item["listener_id"] == listener_id]
    assert matching and matching[0]["status"] == "closed"


def test_workflow_list_filters_by_run_id(run_cli) -> None:
    first = _init_workflow(run_cli, run_id="RUN_WF_ONE")["workflow"]
    second = _init_workflow(run_cli, run_id="RUN_WF_TWO")["workflow"]
    listed = parse_json_output(run_cli(["scripts/web_workflow_list.py", "--run-id", "RUN_WF_ONE", "--json"]))
    ids = [item["workflow_id"] for item in listed["workflows"]]
    assert ids == [first["workflow_id"]]
    assert second["workflow_id"] not in ids


def test_browser_integration_is_skip_safe_without_playwright(run_cli) -> None:
    started = parse_json_output(
        run_cli(["scripts/web_workflow_init.py", "--run-id", "RUN_WF_BROWSER", "--start-browser", "--json"])
    )
    workflow = started["workflow"]
    workflow_id = str(workflow["workflow_id"])
    if workflow.get("browser_session_id"):
        html = urllib.parse.quote("<html><head><title>WF</title></head><body>ok</body></html>", safe="")
        goto = parse_json_output(
            run_cli(
                [
                    "scripts/web_browser_probe.py",
                    "--workflow-id",
                    workflow_id,
                    "--action",
                    "goto",
                    "--url",
                    f"data:text/html,{html}",
                    "--json",
                ]
            )
        )
        assert goto["ok"] is True
        evaluated = parse_json_output(
            run_cli(
                [
                    "scripts/web_browser_probe.py",
                    "--workflow-id",
                    workflow_id,
                    "--action",
                    "eval",
                    "--expression",
                    "document.title",
                    "--json",
                ]
            )
        )
        assert evaluated["ok"] is True
    else:
        probe = parse_json_output(
            run_cli(
                [
                    "scripts/web_browser_probe.py",
                    "--workflow-id",
                    workflow_id,
                    "--action",
                    "eval",
                    "--expression",
                    "document.title",
                    "--json",
                ],
                check=False,
            )
        )
        assert probe["reason"] == "no_browser_session_id"


def test_finalize_closes_run_workflows_and_records_counts(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Web Workflow Finalize",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    workflow = _init_workflow(run_cli, run_id=run_id)["workflow"]
    assert _request(str(workflow["local_callback_url"]) + "/finalize") == 204
    finalized = parse_json_output(
        run_cli(["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "manual_stop"])
    )
    assert finalized["web_workflows"]["closed_web_workflow_count"] == 1
    assert finalized["web_workflows"]["web_evidence_count"] == 1
    final_record = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
    assert final_record["closed_web_workflow_count"] == 1
    assert final_record["web_evidence_count"] == 1


def test_verify_run_can_use_web_workflow_evidence(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Web Workflow Verify",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    workflow = _init_workflow(run_cli, run_id=run_id)["workflow"]
    workflow_id = str(workflow["workflow_id"])
    assert _request(str(workflow["local_callback_url"]) + "/verified") == 204
    parse_json_output(
        run_cli(
            [
                "scripts/web_evidence_collect.py",
                "--workflow-id",
                workflow_id,
                "--include-callback-summary",
                "--json",
            ]
        )
    )
    verified = parse_json_output(
        run_cli(
            [
                "scripts/verify_run.py",
                "--run-dir",
                str(run_dir),
                "--mode",
                "manual",
                "--web-workflow-id",
                workflow_id,
                "--callback-pattern",
                "verified",
                "--callback-min-hits",
                "1",
                "--local",
            ]
        )
    )
    assert verified["success"] is True
    listed = parse_json_output(run_cli(["scripts/web_workflow_list.py", "--run-id", run_id, "--json"]))
    assert listed["workflows"][0]["status"] == "verified"


def test_metrics_public_safe_with_web_workflow_fields(run_cli) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Web Workflow Metrics",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    workflow = _init_workflow(run_cli, run_id=run_id)["workflow"]
    parse_json_output(
        run_cli(
            [
                "scripts/web_payload_generate.py",
                "--workflow-id",
                str(workflow["workflow_id"]),
                "--types",
                "img,script-fetch",
                "--json",
            ]
        )
    )
    assert _request(str(workflow["local_callback_url"]) + "/metrics") == 204
    parse_json_output(
        run_cli(
            [
                "scripts/web_callback_probe.py",
                "--workflow-id",
                str(workflow["workflow_id"]),
                "--wait-timeout-sec",
                "1",
                "--pattern",
                "metrics",
                "--json",
            ]
        )
    )
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
    record = finalized["metrics"]["record"]
    assert record["web_workflow_count"] == 1
    assert record["web_payload_count"] == 2
    assert record["web_callback_probe_success"] is True
    assert record["web_evidence_collected"] is True
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK" in check.stdout


def test_secret_scan_strict_include_untracked_passes(run_cli) -> None:
    result = run_cli(["scripts/secret_scan.py", "--strict", "--include-untracked"])
    assert "OK" in result.stdout
