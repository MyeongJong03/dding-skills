from __future__ import annotations

import json
from pathlib import Path

from conftest import parse_json_output
from ctf_solver_core.gdb_parsers import parse_registers, parse_vmmap, summarize_backtrace
from ctf_solver_core.paths import gdb_artifact_root, gdb_root, is_inside_repo


def _toy_binary(tmp_path: Path) -> Path:
    binary = tmp_path / "toy"
    binary.write_bytes(b"mock binary")
    binary.chmod(0o755)
    return binary


def _start_mock(run_cli, binary: Path, *, run_id: str = "RUN-GDB-1") -> dict[str, object]:
    return parse_json_output(
        run_cli(
            [
                "scripts/gdb_start.py",
                "--binary",
                str(binary),
                "--mode",
                "mock",
                "--run-id",
                run_id,
                "--challenge-id",
                "chal-gdb",
                "--json",
            ]
        )
    )


def test_gdb_root_path_validation(temp_ctf_env) -> None:
    assert gdb_root() == temp_ctf_env.gdb.resolve()
    assert gdb_artifact_root() == temp_ctf_env.gdb_artifacts.resolve()
    assert not is_inside_repo(gdb_root())
    assert not is_inside_repo(gdb_artifact_root())


def test_mock_gdb_start_creates_session_metadata(temp_ctf_env, run_cli, tmp_path: Path) -> None:
    result = _start_mock(run_cli, _toy_binary(tmp_path))
    session = result["gdb_session"]
    gdb_session_id = str(session["gdb_session_id"])
    metadata = temp_ctf_env.gdb / gdb_session_id / "gdb_session.json"
    log = temp_ctf_env.gdb / gdb_session_id / "gdb.log"
    artifact_dir = temp_ctf_env.gdb_artifacts / gdb_session_id
    assert metadata.is_file()
    assert artifact_dir.is_dir()
    assert not log.exists()
    assert session["mode"] == "mock"
    assert session["run_id"] == "RUN-GDB-1"


def test_gdb_cmd_mock_returns_bounded_output(temp_ctf_env, run_cli, tmp_path: Path) -> None:
    started = _start_mock(run_cli, _toy_binary(tmp_path))
    sid = str(started["gdb_session"]["gdb_session_id"])
    result = parse_json_output(
        run_cli(
            [
                "scripts/gdb_cmd.py",
                "--gdb-session-id",
                sid,
                "--cmd",
                "show version",
                "--max-bytes",
                "12",
                "--json",
            ]
        )
    )
    assert len(result["output"].encode()) <= 12
    assert (temp_ctf_env.gdb / sid / "gdb.log").is_file()


def test_gdb_wait_crash_mock_parses_signal_and_pc(run_cli, tmp_path: Path) -> None:
    started = _start_mock(run_cli, _toy_binary(tmp_path))
    sid = str(started["gdb_session"]["gdb_session_id"])
    result = parse_json_output(
        run_cli(["scripts/gdb_wait_crash.py", "--gdb-session-id", sid, "--json"])
    )
    assert result["crashed"] is True
    assert result["crash_info"]["signal"] == "SIGSEGV"
    assert result["crash_info"]["pc"] == "0x401234"


def test_gdb_registers_parser_extracts_registers() -> None:
    output = "rax            0x0  0\nrip            0x401234  0x401234 <main+1>\n"
    assert parse_registers(output) == {"rax": "0x0", "rip": "0x401234"}


def test_gdb_backtrace_parser_keeps_bounded_public_summary() -> None:
    output = "#0  0x401234 in vuln () at /Users/alice/private/chall.c:7\n#1  0x401299 in main ()\n"
    summary = summarize_backtrace(output, max_bytes=200)
    rendered = json.dumps(summary, sort_keys=True)
    assert summary["frame_count"] == 2
    assert "/Users/alice" not in rendered
    assert "<path>/chall.c" in rendered


def test_gdb_vmmap_parser_extracts_mappings() -> None:
    output = (
        "0x0000000000400000 0x0000000000410000 r-xp 00000000 /workspace/chall\n"
        "0x00007ffffffde000 0x00007ffffffff000 rw-p 00000000 [stack]\n"
    )
    mappings = parse_vmmap(output)
    assert mappings[0]["start"] == "0x0000000000400000"
    assert mappings[0]["perms"] == "r-xp"
    assert mappings[0]["path"] == "chall"
    assert mappings[1]["path"] == "[stack]"


def test_gdb_telescope_output_bounded(run_cli, tmp_path: Path) -> None:
    started = _start_mock(run_cli, _toy_binary(tmp_path))
    sid = str(started["gdb_session"]["gdb_session_id"])
    result = parse_json_output(
        run_cli(
            [
                "scripts/gdb_telescope.py",
                "--gdb-session-id",
                sid,
                "--address",
                "$rsp",
                "--count",
                "4",
                "--max-bytes",
                "60",
                "--json",
            ]
        )
    )
    assert len(result["telescope"]["output_preview"].encode()) <= 60


def test_challenge_finalize_closes_run_id_mock_gdb_sessions(temp_ctf_env, run_cli, tmp_path: Path) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "ctf",
                "--event",
                "GDB",
                "--challenge-name",
                "GDB Regression",
                "--category",
                "pwn",
                "--json",
            ]
        )
    )
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    started = _start_mock(run_cli, _toy_binary(tmp_path), run_id=run_id)
    sid = str(started["gdb_session"]["gdb_session_id"])
    run_cli(["scripts/gdb_wait_crash.py", "--gdb-session-id", sid, "--json"])

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
    assert finalized["gdb_sessions"]["closed_gdb_session_count"] == 1
    metadata = json.loads((temp_ctf_env.gdb / sid / "gdb_session.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "closed"
    summary = temp_ctf_env.solver_repo / "metrics" / "summary.jsonl"
    records = [json.loads(line) for line in summary.read_text(encoding="utf-8").splitlines()]
    assert records[0]["gdb_used"] is True
    assert records[0]["gdb_session_count"] == 1
    assert records[0]["gdb_crash_count"] == 1


def test_gdb_metrics_public_safe_check_passes(temp_ctf_env, run_cli) -> None:
    run_cli(
        [
            "scripts/update_metrics.py",
            "--run-id",
            "RUN-GDB-METRICS",
            "--status",
            "manual_stop",
            "--platform",
            "ctf",
            "--event",
            "GDB",
            "--category",
            "pwn",
            "--gdb-session-count",
            "2",
            "--closed-gdb-session-count",
            "2",
            "--gdb-crash-count",
            "1",
            "--gdb-command-count",
            "5",
            "--gdb-used",
        ]
    )
    check = run_cli(["scripts/update_metrics.py", "--check"])
    assert "OK: public metrics are safe" in check.stdout


def test_secret_scan_passes(run_cli) -> None:
    result = run_cli(["scripts/secret_scan.py", "--strict"])
    assert "OK: secret scan clean" in result.stdout
