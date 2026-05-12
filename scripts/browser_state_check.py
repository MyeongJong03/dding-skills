#!/usr/bin/env python3
"""Check local-only browser profile metadata without reading storage contents."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.browser_state import check_browser_profile
from ctf_solver_core.paths import display_path
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--profile", "--profile-name", dest="profile_name", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = check_browser_profile(args.platform, args.event, args.profile_name)
    result["profile_path"] = display_path(Path(str(result.get("profile_path") or "")))
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(f"exists: {result['exists']}")
        print(f"storage state configured: {result['storage_state_configured']}")
        print(f"storage state file exists: {result['storage_state_exists']}")
        print(f"profile metadata: {result['profile_path']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
