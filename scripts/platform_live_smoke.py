#!/usr/bin/env python3
"""Manual opt-in live platform smoke framework."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.live_smoke import LiveSmokeError, LiveSmokeRequest, SMOKE_MODES, run_live_smoke
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--adapter", default="generic", choices=["ctfd", "generic", "mock", "local"])
    parser.add_argument("--profile")
    parser.add_argument("--policy")
    parser.add_argument("--base-url")
    parser.add_argument("--source", help="local fixture/source for mock or fixture-first adapters")
    parser.add_argument("--mode", default="dry-run", choices=SMOKE_MODES)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--no-submit", action="store_true", default=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", help="optional output directory outside the repo")
    parser.add_argument("--run-id")
    parser.add_argument("--challenge-id")
    parser.add_argument("--max-challenges", type=int)
    parser.add_argument("--allow-server-acquire", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    request = LiveSmokeRequest(
        platform=args.platform,
        event=args.event,
        adapter_name=args.adapter,
        profile=args.profile,
        policy_path=args.policy,
        base_url=args.base_url,
        source=args.source,
        mode=args.mode,
        live=args.live,
        no_submit=True,
        output=args.output,
        run_id=args.run_id,
        challenge_id=args.challenge_id,
        max_challenges=args.max_challenges,
        allow_server_acquire=args.allow_server_acquire,
        allow_download=args.allow_download,
    )
    try:
        result = run_live_smoke(request)
    except LiveSmokeError as exc:
        result = {"ok": False, "reason": str(exc), "live": args.live, "mode": args.mode}

    if args.json:
        print(json_dumps(result), end="")
    else:
        status = "ok" if result.get("ok") else "failed"
        print(f"live smoke {status}: {result.get('platform')}/{result.get('event')} mode={result.get('mode')}")
        if result.get("reason"):
            print(f"reason: {result.get('reason')}")
        if result.get("result_path"):
            print(f"result: {result.get('result_path')}")
        if result.get("summary_path"):
            print(f"summary: {result.get('summary_path')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
