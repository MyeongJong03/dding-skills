#!/usr/bin/env python3
"""Initialize a parallel-safe challenge run directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.locks import DirectoryLock
from ctf_solver_core.paths import display_path, local_run_root, resolve_path, work_root
from ctf_solver_core.schemas import (
    CATEGORIES,
    atomic_write_json,
    atomic_write_text,
    iso_now,
    json_dumps,
    make_challenge_id,
    make_run_id,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default="unknown")
    parser.add_argument("--event", default="unknown")
    parser.add_argument("--challenge-id", help="explicit stable challenge_id from a platform queue item")
    parser.add_argument("--challenge-name", required=True)
    parser.add_argument("--category", choices=CATEGORIES, default="unknown")
    parser.add_argument("--workspace", help="optional challenge workspace path")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def initialize_challenge(args: argparse.Namespace) -> dict[str, object]:
    challenge_id = str(args.challenge_id or "").strip() or make_challenge_id(
        args.platform,
        args.event,
        args.challenge_name,
        args.category,
    )
    workspace = resolve_path(args.workspace) if args.workspace else work_root() / challenge_id

    with DirectoryLock(f"challenge-init-{challenge_id}", "challenge initialization"):
        run_root = local_run_root() / challenge_id
        for _ in range(5):
            run_id = make_run_id()
            run_dir = run_root / run_id
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("could not allocate unique run_id")

        workspace.mkdir(parents=True, exist_ok=True)
        for name in ("artifacts", "exploit", "logs", "scratch"):
            (run_dir / name).mkdir(parents=True, exist_ok=True)

        metadata = {
            "challenge_id": challenge_id,
            "run_id": run_id,
            "created_at": iso_now(),
            "platform": args.platform,
            "event": args.event,
            "challenge_name": args.challenge_name,
            "category": args.category,
            "workspace": str(workspace),
            "run_dir": str(run_dir),
            "schema_version": 1,
        }
        atomic_write_json(run_dir / "challenge.json", metadata)
        atomic_write_text(
            run_dir / "notes.md",
            "\n".join(
                [
                    f"# {args.challenge_name}",
                    "",
                    "## Notes",
                    "- TODO: summarize initial analysis.",
                    "",
                    "## Attempts",
                    "- TODO: record meaningful attempts only.",
                    "",
                ]
            ),
        )

    result = {
        **metadata,
        "display_run_dir": display_path(run_dir),
        "display_workspace": display_path(workspace),
    }
    return result


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = initialize_challenge(args)
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(json_dumps(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
