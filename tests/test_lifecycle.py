from __future__ import annotations

import json
from pathlib import Path

from conftest import parse_json_output


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def test_challenge_init_finalize_writeup_cleanup_metrics(temp_ctf_env, run_cli, tmp_path: Path) -> None:
    init = parse_json_output(
        run_cli(
            [
                "scripts/challenge_init.py",
                "--platform",
                "thcon",
                "--event",
                "THCON",
                "--challenge-name",
                "Lifecycle Regression",
                "--category",
                "web",
                "--json",
            ]
        )
    )
    challenge_id = str(init["challenge_id"])
    run_id = str(init["run_id"])
    run_dir = Path(str(init["run_dir"]))
    workspace = Path(str(init["workspace"]))

    assert challenge_id
    assert run_id
    assert (run_dir / "challenge.json").is_file()
    assert (run_dir / "notes.md").is_file()
    for name in ("artifacts", "exploit", "logs", "scratch"):
        assert (run_dir / name).is_dir()

    exploit = tmp_path / "dummy_exploit.py"
    exploit_code = "def exploit():\n    return 'regression-ok'\n\nprint(exploit())\n"
    exploit.write_text(exploit_code, encoding="utf-8")
    protected_workspace_file = workspace / "final_payload.py"
    protected_workspace_file.write_text("print('keep me')\n", encoding="utf-8")
    cache_dir = workspace / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "junk.pyc").write_bytes(b"cache")

    finalized = parse_json_output(
        run_cli(
            [
                "scripts/challenge_finalize.py",
                "--run-dir",
                str(run_dir),
                "--status",
                "solved",
                "--reason",
                "regression",
                "--flag",
                "DH{dummy_local_only_flag}",
                "--exploit",
                str(exploit),
                "--generate-writeup",
                "--cleanup",
                "--update-metrics",
            ]
        )
    )

    writeup_path = Path(str(finalized["writeup"]["writeup_path"]))
    assert writeup_path.is_file()
    assert _is_relative_to(writeup_path, temp_ctf_env.writeups)
    assert not _is_relative_to(writeup_path, temp_ctf_env.solver_repo)
    assert exploit_code.strip() in writeup_path.read_text(encoding="utf-8")
    assert protected_workspace_file.exists()
    assert not cache_dir.exists()

    summary = temp_ctf_env.solver_repo / "metrics" / "summary.jsonl"
    records = [json.loads(line) for line in summary.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["run_id"] == run_id

    duplicate = parse_json_output(
        run_cli(["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "solved"])
    )
    assert duplicate["already_finalized"] is True
    records_after = [json.loads(line) for line in summary.read_text(encoding="utf-8").splitlines()]
    assert len(records_after) == 1

    changed_status = run_cli(
        ["scripts/challenge_finalize.py", "--run-dir", str(run_dir), "--status", "manual_stop"],
        check=False,
    )
    assert changed_status.returncode != 0
