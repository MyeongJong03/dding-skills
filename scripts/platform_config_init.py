#!/usr/bin/env python3
"""Create a repo-external platform policy template."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.paths import display_path, resolve_path
from ctf_solver_core.schemas import atomic_write_text, json_dumps


def render_template(platform: str, event: str, max_active_vms: int) -> str:
    return f"""# Platform resource policy template.
# Keep real cookies, tokens, passwords, OAuth data, account IDs, and session
# storage outside this repository. session_profile is only a local profile name.
platforms:
  - platform: {platform}
    event: {event}
    auth:
      mode: browser_profile
      session_profile: local-profile-placeholder
    resources:
      remote_server:
        provisioning: true
        max_active_leases: {max_active_vms}
        lease_scope: event
        release_required_before_next: true
        sharing:
          allowed: false
          max_workers: 1
          mode: exclusive
          destructive_actions_require_primary: true
    automation:
      allow_problem_discovery: true
      allow_file_download: true
      allow_server_create: ask
      allow_submission: ask
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default="thcon")
    parser.add_argument("--event", default="THCON")
    parser.add_argument("--max-active-vms", type=int, default=1)
    parser.add_argument("--output", help="default: ~/.ctf-solver/platforms/<platform>.yaml")
    parser.add_argument("--print-template", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    text = render_template(args.platform, args.event, args.max_active_vms)
    if args.print_template:
        print(text, end="")
        return 0

    output = resolve_path(args.output) if args.output else Path.home() / ".ctf-solver" / "platforms" / f"{args.platform}.yaml"
    atomic_write_text(output, text)
    print(
        json_dumps(
            {
                "created": True,
                "path": str(output),
                "display_path": display_path(output),
                "contains_secrets": False,
            }
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
