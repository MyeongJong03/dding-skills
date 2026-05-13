#!/usr/bin/env python3
"""Generate a no-network CTFd live smoke command checklist."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse


DEFAULT_PLATFORM = "ctfd"
DEFAULT_EVENT = "manual-live"
DEFAULT_BASE_URL = "https://ctfd.example.invalid"


class RunbookError(ValueError):
    """Raised when a planned command would carry unsafe or incomplete input."""


@dataclass(frozen=True)
class PlannedCommand:
    name: str
    description: str
    command: list[str]
    network: str = "none"

    def as_record(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "command": shlex.join(self.command),
            "argv": self.command,
            "network": self.network,
        }


def _safe_base_url(value: str | None) -> str:
    raw = (value or DEFAULT_BASE_URL).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RunbookError("base_url_missing")
    if parsed.username or parsed.password:
        raise RunbookError("base_url_must_not_include_userinfo")
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _append_optional(args: list[str], *, policy: str | None, profile: str | None) -> None:
    if policy:
        args.extend(["--policy", policy])
    if profile:
        args.extend(["--profile", profile])


def _smoke_args(
    *,
    platform: str,
    event: str,
    base_url: str,
    policy: str | None,
    profile: str | None,
    live: bool,
) -> list[str]:
    args = [
        "python3",
        "scripts/platform_live_smoke.py",
        "--platform",
        platform,
        "--event",
        event,
        "--adapter",
        "ctfd",
        "--mode",
        "discovery",
        "--base-url",
        base_url,
        "--no-submit",
        "--json",
    ]
    _append_optional(args, policy=policy, profile=profile)
    if live:
        args.append("--live")
    return args


def _discover_args(
    *,
    platform: str,
    event: str,
    base_url: str,
    policy: str | None,
    profile: str | None,
    queue: bool,
) -> list[str]:
    args = [
        "python3",
        "scripts/platform_discover.py",
        "--platform",
        platform,
        "--event",
        event,
        "--adapter",
        "ctfd",
        "--base-url",
        base_url,
        "--live",
        "--json",
    ]
    _append_optional(args, policy=policy, profile=profile)
    if queue:
        args.append("--queue")
    return args


def build_plan(args: argparse.Namespace) -> dict[str, object]:
    base_url = _safe_base_url(args.base_url)
    commands = [
        PlannedCommand(
            "preflight_git_status",
            "Confirm the repo is clean before manual live access.",
            ["git", "status", "--short"],
        ),
        PlannedCommand(
            "preflight_doctor",
            "Confirm doctor has no hard failures before live access.",
            ["python3", "scripts/doctor.py"],
        ),
        PlannedCommand(
            "preflight_secret_scan",
            "Confirm tracked files do not contain secrets.",
            ["python3", "scripts/secret_scan.py", "--strict"],
        ),
        PlannedCommand(
            "smoke_dry_run",
            "Dry-run first; this command must not open the base URL.",
            _smoke_args(
                platform=args.platform,
                event=args.event,
                base_url=base_url,
                policy=args.policy,
                profile=args.profile,
                live=False,
            ),
        ),
    ]
    if args.include_live_command:
        commands.append(
            PlannedCommand(
                "smoke_live_discovery",
                "Manual approved read-only CTFd discovery; the helper prints only and never executes it.",
                _smoke_args(
                    platform=args.platform,
                    event=args.event,
                    base_url=base_url,
                    policy=args.policy,
                    profile=args.profile,
                    live=True,
                ),
                network="manual-live-readonly",
            )
        )
        commands.append(
            PlannedCommand(
                "platform_discover_live",
                "Direct read-only discovery after the dry-run smoke passes.",
                _discover_args(
                    platform=args.platform,
                    event=args.event,
                    base_url=base_url,
                    policy=args.policy,
                    profile=args.profile,
                    queue=False,
                ),
                network="manual-live-readonly",
            )
        )
    if args.include_queue_command:
        commands.append(
            PlannedCommand(
                "platform_discover_live_queue",
                "Optional queue registration; include only when queueing is explicitly approved.",
                _discover_args(
                    platform=args.platform,
                    event=args.event,
                    base_url=base_url,
                    policy=args.policy,
                    profile=args.profile,
                    queue=True,
                ),
                network="manual-live-readonly",
            )
        )

    return {
        "ok": True,
        "network_performed": False,
        "platform": args.platform,
        "event": args.event,
        "base_url": base_url,
        "profile_configured": bool(args.profile),
        "policy_configured": bool(args.policy),
        "live_commands_included": bool(args.include_live_command),
        "queue_command_included": bool(args.include_queue_command),
        "auth_sources": [
            "browser_state profile metadata via --profile",
            "repo-external CTF_CTFD_COOKIE_FILE",
            "local-only CTF_CTFD_COOKIE_HEADER",
        ],
        "safety": {
            "dry_run_first": True,
            "no_submit": True,
            "no_exploit": True,
            "download_requires_live_and_allow_download": True,
            "no_server_acquire": True,
            "raw_auth_not_read": True,
            "raw_responses_not_stored": True,
        },
        "failure_reasons": [
            "auth_required_or_profile_missing",
            "ctfd_api_error",
            "base_url_missing",
            "network_timeout",
        ],
        "commands": [command.as_record() for command in commands],
    }


def render_text(plan: dict[str, object]) -> str:
    lines = [
        "CTFd live smoke runbook command plan",
        "This helper does not execute commands and performs no network requests.",
        "",
        "Safety:",
        "- dry-run first",
        "- smoke commands never submit flags",
        "- no exploit or server acquire path is generated",
        "- live download requires a separate command with both --live and --allow-download",
        "- auth values and storage_state contents are not read",
        "",
        "Auth sources:",
        "- browser_state profile metadata via --profile",
        "- repo-external CTF_CTFD_COOKIE_FILE",
        "- local-only CTF_CTFD_COOKIE_HEADER",
        "",
        "Commands:",
    ]
    commands = plan.get("commands") if isinstance(plan.get("commands"), list) else []
    for index, command in enumerate(commands, start=1):
        if not isinstance(command, dict):
            continue
        lines.append(f"{index}. {command.get('name')}: {command.get('description')}")
        lines.append(f"   {command.get('command')}")
    lines.extend(
        [
            "",
            "Public-safe result check:",
            "- read discovered_count, ctfd_live_discovered_count, or live download count/bytes only",
            "- do not copy cookies, tokens, storage_state contents, raw URL queries, or raw responses into repo files",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--event", default=DEFAULT_EVENT)
    parser.add_argument("--base-url")
    parser.add_argument("--profile")
    parser.add_argument("--policy")
    parser.add_argument("--include-live-command", action="store_true")
    parser.add_argument("--include-queue-command", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        plan = build_plan(args)
    except RunbookError as exc:
        result = {"ok": False, "reason": str(exc), "network_performed": False}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"runbook plan blocked: {exc}")
        return 1

    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(render_text(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
