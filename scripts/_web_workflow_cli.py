"""Shared CLI implementation for web exploit workflow scripts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.web_payloads import PAYLOAD_TYPES, ENCODINGS
from ctf_solver_core.web_workflow import (
    browser_probe,
    callback_probe,
    close_workflow,
    collect_evidence,
    generate_payloads_for_workflow,
    init_workflow,
    list_workflows,
)


def _types(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def build_parser(action: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Web exploit workflow: {action}")
    _common(parser)
    if action == "init":
        parser.add_argument("--run-id")
        parser.add_argument("--challenge-id")
        parser.add_argument("--worker-id")
        parser.add_argument("--target-url")
        parser.add_argument("--start-browser", action="store_true")
        parser.add_argument("--start-callback", action="store_true")
        parser.add_argument("--browser-profile")
        parser.add_argument("--external-base-url")
    elif action == "payload":
        parser.add_argument("--workflow-id")
        parser.add_argument("--callback-url")
        parser.add_argument("--types", help="comma-separated: " + ",".join(PAYLOAD_TYPES))
        parser.add_argument("--target-param")
        parser.add_argument("--encode", choices=ENCODINGS)
    elif action == "browser":
        parser.add_argument("--workflow-id", required=True)
        parser.add_argument("--url")
        parser.add_argument("--action", choices=("goto", "fill", "click", "upload", "eval", "screenshot"), required=True)
        parser.add_argument("--selector")
        parser.add_argument("--value")
        parser.add_argument("--file")
        parser.add_argument("--expression")
        parser.add_argument("--timeout-ms", type=int)
    elif action == "callback":
        parser.add_argument("--workflow-id", required=True)
        parser.add_argument("--wait-timeout-sec", type=float, default=15.0)
        parser.add_argument("--pattern")
        parser.add_argument("--min-hits", type=int, default=1)
    elif action == "evidence":
        parser.add_argument("--workflow-id", required=True)
        parser.add_argument("--include-browser-summary", action="store_true")
        parser.add_argument("--include-callback-summary", action="store_true")
        parser.add_argument("--include-verifier-summary", action="store_true")
    elif action == "close":
        parser.add_argument("--workflow-id", required=True)
        parser.add_argument("--close-browser", action=argparse.BooleanOptionalAction, default=True)
        parser.add_argument("--close-callback", action=argparse.BooleanOptionalAction, default=True)
        parser.add_argument("--reason", default="closed")
    elif action == "list":
        parser.add_argument("--run-id")
        parser.add_argument("--challenge-id")
        parser.add_argument("--include-closed", action="store_true")
    else:
        raise ValueError(f"unsupported web workflow action: {action}")
    return parser


def run_action(action: str, args: argparse.Namespace) -> dict[str, object]:
    if action == "init":
        return init_workflow(
            run_id=args.run_id,
            challenge_id=args.challenge_id,
            worker_id=args.worker_id,
            target_url=args.target_url,
            start_browser=args.start_browser,
            start_callback=args.start_callback,
            browser_profile=args.browser_profile,
            external_base_url=args.external_base_url,
        )
    if action == "payload":
        return generate_payloads_for_workflow(
            workflow_id=args.workflow_id,
            callback_url=args.callback_url,
            types=_types(args.types),
            target_param=args.target_param,
            encode=args.encode,
        )
    if action == "browser":
        return browser_probe(
            workflow_id=args.workflow_id,
            action=args.action,
            url=args.url,
            selector=args.selector,
            value=args.value,
            file=args.file,
            expression=args.expression,
            timeout_ms=args.timeout_ms,
        )
    if action == "callback":
        return callback_probe(
            workflow_id=args.workflow_id,
            wait_timeout_sec=args.wait_timeout_sec,
            pattern=args.pattern,
            min_hits=args.min_hits,
        )
    if action == "evidence":
        return collect_evidence(
            workflow_id=args.workflow_id,
            include_browser_summary=args.include_browser_summary,
            include_callback_summary=args.include_callback_summary,
            include_verifier_summary=args.include_verifier_summary,
        )
    if action == "close":
        return close_workflow(
            workflow_id=args.workflow_id,
            close_browser=args.close_browser,
            close_callback=args.close_callback,
            reason=args.reason,
        )
    if action == "list":
        return list_workflows(
            run_id=args.run_id,
            challenge_id=args.challenge_id,
            include_closed=args.include_closed,
        )
    raise ValueError(f"unsupported web workflow action: {action}")


def _print_human(action: str, result: dict[str, object]) -> None:
    if action == "init":
        workflow = result.get("workflow") if isinstance(result.get("workflow"), dict) else {}
        print(workflow.get("workflow_id") or "")
        local = str(workflow.get("local_callback_url") or "")
        external = str(workflow.get("external_callback_url") or "")
        if local:
            print(local)
        if external:
            print(external)
        return
    if action == "list":
        for item in result.get("workflows") or []:
            if isinstance(item, dict):
                print(
                    f"{item.get('workflow_id')} {item.get('status')} "
                    f"run={item.get('run_id') or '-'} payloads={item.get('payload_count') or 0}"
                )
        return
    print(json_dumps(result), end="")


def main(action: str) -> int:
    args = build_parser(action).parse_args()
    result = run_action(action, args)
    if args.json:
        print(json_dumps(result), end="")
    else:
        _print_human(action, result)
    return 0 if result.get("ok", True) else 1
