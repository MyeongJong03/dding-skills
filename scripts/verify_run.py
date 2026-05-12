#!/usr/bin/env python3
"""Verify solve evidence for a challenge run."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.schemas import json_dumps
from ctf_solver_core.verifier import DEFAULT_MAX_OUTPUT_BYTES, DEFAULT_TIMEOUT_SEC, verify_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir")
    parser.add_argument("--mode", choices=("command", "session", "manual"), required=True)
    parser.add_argument("--command")
    parser.add_argument("--cwd")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--flag-regex")
    parser.add_argument("--success-regex")
    parser.add_argument("--fail-regex")
    parser.add_argument("--session-id")
    parser.add_argument("--session-input")
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--evidence-text")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--label", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--save",
        action="store_true",
        help="also save private raw verifier evidence under <run_dir>/logs/verifier-output.txt",
    )
    parser.add_argument("--no-save", action="store_true", help="do not save <run_dir>/verifier.json")
    parser.add_argument("--redact-output", action="store_true", default=True)
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_MAX_OUTPUT_BYTES)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = verify_run(
        mode=args.mode,
        run_dir=args.run_dir,
        command=args.command,
        cwd=args.cwd,
        timeout_sec=args.timeout_sec,
        retries=args.retries,
        flag_regex=args.flag_regex,
        success_regex=args.success_regex,
        fail_regex=args.fail_regex,
        session_id=args.session_id,
        session_input=args.session_input,
        expect=args.expect,
        evidence_text=args.evidence_text,
        local=args.local,
        remote=args.remote,
        label=args.label,
        save_result=False if args.no_save else None,
        save_evidence=bool(args.save),
        redact_output=True,
        max_output_bytes=args.max_output_bytes,
    )
    print(json_dumps(result), end="")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
