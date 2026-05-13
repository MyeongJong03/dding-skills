#!/usr/bin/env python3
"""Download challenge files through a policy-gated platform adapter scaffold."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.platform_automation import download_files
from ctf_solver_core.schemas import json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--event", required=True)
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--challenge-id")
    id_group.add_argument("--external-id")
    parser.add_argument("--url")
    parser.add_argument("--source")
    parser.add_argument("--base-url")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--profile")
    parser.add_argument("--dest")
    parser.add_argument("--policy")
    parser.add_argument("--adapter", default="generic", choices=["generic", "mock", "local", "ctfd"])
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--allow-repo-dest", action="store_true")
    parser.add_argument("--queue", action="store_true")
    parser.add_argument("--queue-state", default="downloaded", choices=["downloaded", "local_triage"])
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = download_files(
        platform=args.platform,
        event=args.event,
        challenge_id=args.challenge_id,
        external_id=args.external_id,
        adapter_name=args.adapter,
        url=args.url,
        source=args.source,
        base_url=args.base_url,
        live=args.live,
        profile=args.profile,
        allow_download=args.allow_download,
        dest=args.dest,
        policy_path=args.policy,
        allow_repo_dest=args.allow_repo_dest,
        queue=args.queue,
        queue_state=args.queue_state,
    )
    if args.profile:
        result["profile"] = args.profile
    if args.json:
        print(json_dumps(result), end="")
    else:
        if result.get("ok"):
            metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
            print(f"downloaded {len(metadata.get('files', []))} files to {result.get('dest')}")
        else:
            print(f"platform download blocked: {result.get('reason')}", file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
