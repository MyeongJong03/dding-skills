#!/usr/bin/env python3
"""Register local-only browser storage-state metadata."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.browser_state import BrowserStateError, profile_summary, register_browser_profile
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--profile", "--profile-name", dest="profile_name", required=True)
    parser.add_argument("--storage-state", help="existing Playwright storage state JSON path outside the repo")
    parser.add_argument("--notes", default="")
    parser.add_argument("--print-login-instructions", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _instructions(platform: str, event: str, profile_name: str) -> list[str]:
    return [
        "Create a Playwright storage state manually outside this repository.",
        "Keep cookies, tokens, and session storage local-only.",
        (
            "After creating the file, register it with: "
            f"python3 scripts/browser_state_init.py --platform {platform} --event {event} "
            f"--profile {profile_name} --storage-state <path-outside-repo>"
        ),
    ]


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = register_browser_profile(
            platform=args.platform,
            event=args.event,
            profile_name=args.profile_name,
            storage_state_path=args.storage_state,
            notes=args.notes,
        )
    except BrowserStateError as exc:
        output = {"ok": False, "reason": str(exc)}
        if args.json:
            print(json_dumps(output), end="")
        else:
            print(f"browser state registration failed: {exc}", file=sys.stderr)
        return 1

    summary = profile_summary(result)
    if args.print_login_instructions:
        summary["login_instructions"] = _instructions(args.platform, args.event, args.profile_name)
    if args.json:
        print(json_dumps(summary), end="")
    else:
        print(f"registered {summary['platform']}/{summary['event']} profile {summary['profile_name']}")
        print(f"profile metadata: {summary['profile_path']}")
        print(f"storage state configured: {summary['storage_state_configured']}")
        if args.print_login_instructions:
            print("")
            for line in summary["login_instructions"]:
                print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
