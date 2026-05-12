#!/usr/bin/env python3
"""Start a persistent CTF session through the local daemon."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.session_client import start_session
from ctf_solver_core.sessions import SESSION_KINDS


def _env_pairs(values: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"env must be KEY=VALUE: {value}")
        key, item = value.split("=", 1)
        env[key] = item
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=SESSION_KINDS)
    parser.add_argument("--command")
    parser.add_argument("--cwd")
    parser.add_argument("--run-id")
    parser.add_argument("--challenge-id")
    parser.add_argument("--worker-id")
    parser.add_argument("--host")
    parser.add_argument("--port")
    parser.add_argument("--image")
    parser.add_argument("--workspace")
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--env", action="append", default=[], help="explicit child env as KEY=VALUE")
    parser.add_argument("--env-json", help="explicit child env as a JSON object")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    env = _env_pairs(args.env)
    if args.env_json:
        parsed = json.loads(args.env_json)
        if not isinstance(parsed, dict):
            raise ValueError("--env-json must be a JSON object")
        env.update({str(key): str(value) for key, value in parsed.items()})

    result = start_session(
        kind=args.kind,
        command=args.command,
        cwd=args.cwd,
        run_id=args.run_id,
        challenge_id=args.challenge_id,
        worker_id=args.worker_id,
        host=args.host,
        port=args.port,
        image=args.image,
        workspace=args.workspace,
        timeout_ms=args.timeout_ms,
        env=env or None,
    )
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(result["session"]["session_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
