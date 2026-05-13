from __future__ import annotations

import json
from pathlib import Path

from conftest import parse_json_output
from ctf_solver_core.paths import is_inside_repo
from ctf_solver_core.platform_adapters import PlatformAdapterError, get_adapter
from ctf_solver_core.queue import list_queue_events, list_queue_items
from ctf_solver_core.schemas import read_json, read_jsonl


def _ctfd_fixtures(base: Path) -> tuple[Path, Path, Path]:
    attachments = base / "attachments"
    attachments.mkdir(parents=True, exist_ok=True)
    handout = attachments / "handout.txt"
    handout.write_text("ctfd local attachment\n", encoding="utf-8")

    discovery = base / "ctfd-challenges.json"
    discovery.write_text(
        json.dumps(
            {
                "success": True,
                "data": [
                    {
                        "id": 1,
                        "name": "web baby",
                        "category": "web",
                        "type": "standard",
                        "solves": 0,
                        "value": 100,
                        "tags": [{"name": "starter"}],
                        "files": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    detail = base / "ctfd-detail.json"
    detail.write_text(
        json.dumps(
            {
                "success": True,
                "data": {
                    "id": 1,
                    "name": "web baby",
                    "category": "web",
                    "description": "local-only problem statement",
                    "files": [{"name": "handout.txt", "path": "attachments/handout.txt"}],
                    "connection_info": "nc example.invalid 31337",
                    "hints": [{"content": "fixture hint"}],
                    "tags": [{"name": "starter"}],
                    "state": "visible",
                },
            }
        ),
        encoding="utf-8",
    )
    return discovery, detail, handout


def _ctfd_policy(temp_ctf_env, **kwargs) -> None:
    defaults = {
        "platform": "ctfd",
        "event": "LocalCTF",
        "adapter": "ctfd",
        "auth_mode": "none",
        "provisioning": False,
        "max_active": 0,
        "allow_problem_discovery": True,
        "allow_file_download": True,
        "allow_server_create": True,
        "allow_submission": "ask",
    }
    defaults.update(kwargs)
    temp_ctf_env.write_platform_config(**defaults)


def test_ctfd_discovery_parses_api_json_fixture(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    discovery, _, _ = _ctfd_fixtures(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--adapter",
                "ctfd",
                "--source",
                str(discovery),
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["challenge_count"] == 1
    challenge = result["challenges"][0]
    assert challenge["challenge_id"] == "ctfd/localctf/web/web-baby"
    assert challenge["external_id"] == "1"
    assert challenge["platform"] == "ctfd"
    assert challenge["event"] == "LocalCTF"
    assert challenge["tags"] == ["starter"]
    assert challenge["value"] == 100


def test_ctfd_discovery_parses_html_fixture(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    html = temp_ctf_env.base / "ctfd-challenges.html"
    html.write_text(
        '<button class="challenge-button" value="7" data-name="pwn intro" '
        'data-category="pwn" data-tags="starter,binary"></button>',
        encoding="utf-8",
    )
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--adapter",
                "ctfd",
                "--source",
                str(html),
                "--json",
            ]
        )
    )
    challenge = result["challenges"][0]
    assert challenge["challenge_id"] == "ctfd/localctf/pwn/pwn-intro"
    assert challenge["external_id"] == "7"
    assert challenge["tags"] == ["starter", "binary"]


def test_ctfd_challenge_id_is_stable_and_sanitized(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    discovery, _, _ = _ctfd_fixtures(temp_ctf_env.base)
    args = [
        "scripts/platform_discover.py",
        "--platform",
        "ctfd",
        "--event",
        "LocalCTF",
        "--adapter",
        "ctfd",
        "--source",
        str(discovery),
        "--json",
    ]
    first = parse_json_output(run_cli(args))
    second = parse_json_output(run_cli(args))
    assert first["challenges"][0]["challenge_id"] == second["challenges"][0]["challenge_id"]
    assert first["challenges"][0]["challenge_id"] == "ctfd/localctf/web/web-baby"


def test_ctfd_policy_adapter_is_used_when_cli_adapter_is_default(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    discovery, _, _ = _ctfd_fixtures(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--source",
                str(discovery),
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["adapter"] == "ctfd"
    assert result["challenges"][0]["challenge_id"] == "ctfd/localctf/web/web-baby"


def test_ctfd_platform_discover_queue_adds_items(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    discovery, _, _ = _ctfd_fixtures(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--adapter",
                "ctfd",
                "--source",
                str(discovery),
                "--queue",
                "--json",
            ]
        )
    )
    assert result["queued_count"] == 1
    items = list_queue_items(platform="ctfd", event="LocalCTF")
    assert len(items) == 1
    assert items[0]["challenge_id"] == "ctfd/localctf/web/web-baby"
    assert items[0]["state"] == "discovered"


def test_ctfd_detail_parsing_keeps_description_out_of_public_queue_events(temp_ctf_env) -> None:
    _ctfd_policy(temp_ctf_env)
    _, detail, _ = _ctfd_fixtures(temp_ctf_env.base)
    adapter = get_adapter("ctfd")
    parsed = adapter.get_challenge_detail(
        platform="ctfd",
        event="LocalCTF",
        challenge_id="ctfd/localctf/web/web-baby",
        source=str(detail),
    )
    assert parsed["category"] == "web"
    assert parsed["files"] == ["handout.txt"]
    assert parsed["tags"] == ["starter"]
    assert parsed["description"] == "local-only problem statement"
    events = list_queue_events(platform="ctfd", event="LocalCTF")
    assert "local-only problem statement" not in json.dumps(events)


def test_ctfd_download_copies_attachment_outside_repo_and_writes_metadata(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    discovery, detail, _ = _ctfd_fixtures(temp_ctf_env.base)
    run_cli(
        [
            "scripts/platform_discover.py",
            "--platform",
            "ctfd",
            "--event",
            "LocalCTF",
            "--adapter",
            "ctfd",
            "--source",
            str(discovery),
            "--queue",
            "--json",
        ]
    )
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_download.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--challenge-id",
                "ctfd/localctf/web/web-baby",
                "--adapter",
                "ctfd",
                "--source",
                str(detail),
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["metadata"]["files"][0]["name"] == "handout.txt"
    assert result["metadata"]["files"][0]["size"] > 0
    metadata_path = Path(str(result["metadata_path"]).replace("~", str(temp_ctf_env.home), 1))
    assert metadata_path.is_file()
    assert not is_inside_repo(metadata_path)
    metadata = read_json(metadata_path)
    assert metadata["files"][0]["relative_path"] == "handout.txt"
    assert list_queue_items(platform="ctfd", event="LocalCTF")[0]["state"] == "downloaded"


def test_ctfd_repo_internal_download_dest_is_rejected(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    _, detail, _ = _ctfd_fixtures(temp_ctf_env.base)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_download.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--challenge-id",
                "ctfd/localctf/web/web-baby",
                "--adapter",
                "ctfd",
                "--source",
                str(detail),
                "--dest",
                str(temp_ctf_env.solver_repo / "downloads"),
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["reason"] == "download_dest_inside_repo"


def test_ctfd_submit_default_ask_does_not_submit(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_submit.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--challenge-id",
                "ctfd/localctf/web/web-baby",
                "--flag",
                "PLACEHOLDER_FLAG",
                "--adapter",
                "ctfd",
                "--json",
            ],
            check=False,
        )
    )
    assert result["submitted"] is False
    assert result["reason"] == "allow_submission_requires_confirmation"
    assert "PLACEHOLDER_FLAG" not in json.dumps(result)


def test_ctfd_helper_role_submit_fails(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env, allow_submission=True)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_submit.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--challenge-id",
                "ctfd/localctf/web/web-baby",
                "--flag",
                "PLACEHOLDER_FLAG",
                "--role",
                "helper",
                "--adapter",
                "ctfd",
                "--json",
            ],
            check=False,
        )
    )
    assert result["submitted"] is False
    assert result["reason"] == "primary_role_required"
    assert "PLACEHOLDER_FLAG" not in json.dumps(result)


def test_ctfd_allow_submission_primary_simulates_without_raw_flag(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env, allow_submission=True)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_submit.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--challenge-id",
                "ctfd/localctf/web/web-baby",
                "--flag",
                "PLACEHOLDER_FLAG",
                "--adapter",
                "ctfd",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["submitted"] is True
    assert result["accepted"] is False
    assert result["reason"] == "ctfd_submit_scaffold_no_live_network"
    assert "PLACEHOLDER_FLAG" not in json.dumps(result)


def test_ctfd_server_acquire_returns_unsupported_when_policy_allows_create(temp_ctf_env, run_cli) -> None:
    _ctfd_policy(temp_ctf_env, provisioning=True, max_active=1, allow_server_create=True)
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_server_acquire.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--challenge-id",
                "ctfd/localctf/web/web-baby",
                "--run-id",
                "run-ctfd",
                "--adapter",
                "ctfd",
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["server_acquired"] is False
    assert result["reason"] == "ctfd_server_provisioning_unsupported"


def test_ctfd_live_fixture_boundary_blocks_url_without_opt_in(temp_ctf_env) -> None:
    _ctfd_policy(temp_ctf_env)
    adapter = get_adapter("ctfd")
    try:
        adapter.discover_challenges(
            platform="ctfd",
            event="LocalCTF",
            source="https://ctfd.example.invalid/api/v1/challenges",
        )
    except PlatformAdapterError as exc:
        assert str(exc) == "ctfd_live_mode_requires_opt_in"
    else:
        raise AssertionError("live URL should be blocked without explicit opt-in")


def test_platform_discover_ctfd_without_live_does_not_network(temp_ctf_env, run_cli, ctfd_mock_server) -> None:
    _ctfd_policy(temp_ctf_env)
    server = ctfd_mock_server()
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--adapter",
                "ctfd",
                "--base-url",
                server.base_url,
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["reason"] == "ctfd_live_mode_requires_opt_in"
    assert server.hits == []


def test_ctfd_live_discovery_parses_local_mock_api(temp_ctf_env, run_cli, ctfd_mock_server) -> None:
    _ctfd_policy(temp_ctf_env)
    server = ctfd_mock_server()
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--adapter",
                "ctfd",
                "--base-url",
                server.base_url,
                "--live",
                "--json",
            ]
        )
    )
    assert result["ok"] is True
    assert result["live"] is True
    assert result["challenge_count"] == 1
    challenge = result["challenges"][0]
    assert challenge["external_id"] == "1"
    assert challenge["name"] == "web baby"
    assert challenge["value"] == 100
    assert challenge["solves"] == 3
    assert challenge["tags"] == ["starter"]
    assert "/api/v1/challenges" in server.hits
    assert "description" not in json.dumps(result)


def test_ctfd_live_detail_parses_local_mock_api(temp_ctf_env, ctfd_mock_server) -> None:
    _ctfd_policy(temp_ctf_env)
    server = ctfd_mock_server()
    adapter = get_adapter("ctfd")
    detail = adapter.get_challenge_detail(
        platform="ctfd",
        event="LocalCTF",
        challenge_id="1",
        source=server.base_url,
        live=True,
    )
    assert detail["external_id"] == "1"
    assert detail["description"] == "local mock detail"
    assert detail["connection_info"] == "nc example.invalid 31337"
    assert "/api/v1/challenges/1" in server.hits


def test_ctfd_live_discovery_queue_adds_items(temp_ctf_env, run_cli, ctfd_mock_server) -> None:
    _ctfd_policy(temp_ctf_env)
    server = ctfd_mock_server()
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--adapter",
                "ctfd",
                "--base-url",
                server.base_url,
                "--live",
                "--queue",
                "--json",
            ]
        )
    )
    assert result["queued_count"] == 1
    items = list_queue_items(platform="ctfd", event="LocalCTF")
    assert len(items) == 1
    assert items[0]["challenge_id"] == "ctfd/localctf/web/web-baby"
    assert items[0]["state"] == "discovered"


def test_ctfd_live_auth_missing_returns_clear_error(temp_ctf_env, run_cli, ctfd_mock_server) -> None:
    _ctfd_policy(temp_ctf_env)
    server = ctfd_mock_server(required_cookie=("sess" + "ion=required"))
    result = parse_json_output(
        run_cli(
            [
                "scripts/platform_discover.py",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--adapter",
                "ctfd",
                "--base-url",
                server.base_url,
                "--live",
                "--json",
            ],
            check=False,
        )
    )
    assert result["ok"] is False
    assert result["reason"] == "auth_required_or_profile_missing"


def test_ctfd_live_cookie_header_is_not_printed(temp_ctf_env, run_cli, ctfd_mock_server) -> None:
    _ctfd_policy(temp_ctf_env)
    cookie = ("sess" + "ion=SECRET_COOKIE_SHOULD_NOT_PRINT")
    temp_ctf_env.env["CTF_CTFD_COOKIE_HEADER"] = cookie
    server = ctfd_mock_server(required_cookie=cookie)
    output = run_cli(
        [
            "scripts/platform_discover.py",
            "--platform",
            "ctfd",
            "--event",
            "LocalCTF",
            "--adapter",
            "ctfd",
            "--base-url",
            server.base_url,
            "--live",
            "--json",
        ]
    )
    assert cookie not in output.stdout
    result = parse_json_output(output)
    assert result["ok"] is True


def test_ctfd_metrics_public_safe_fields(temp_ctf_env, run_cli) -> None:
    result = parse_json_output(
        run_cli(
            [
                "scripts/update_metrics.py",
                "--run-id",
                "ctfd-metric-run",
                "--status",
                "manual_stop",
                "--platform",
                "ctfd",
                "--event",
                "LocalCTF",
                "--category",
                "web",
                "--platform-adapter",
                "ctfd",
                "--ctfd-challenge-count",
                "1",
                "--ctfd-download-count",
                "1",
                "--ctfd-submit-attempted",
                "--ctfd-live-discovery-attempted",
                "--ctfd-live-discovery-success",
                "--ctfd-live-discovered-count",
                "1",
            ]
        )
    )
    assert result["public_summary_updated"] is True
    records = read_jsonl(temp_ctf_env.solver_repo / "metrics" / "summary.jsonl")
    assert records[0]["platform_adapter"] == "ctfd"
    assert records[0]["ctfd_challenge_count"] == 1
    assert records[0]["ctfd_download_count"] == 1
    assert records[0]["ctfd_submit_attempted"] is True
    assert records[0]["ctfd_live_discovery_attempted"] is True
    assert records[0]["ctfd_live_discovery_success"] is True
    assert records[0]["ctfd_live_discovered_count"] == 1
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout
