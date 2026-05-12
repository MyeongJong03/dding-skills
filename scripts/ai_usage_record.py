#!/usr/bin/env python3
"""Record one manual AI usage entry."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.ai_usage import PROVIDERS, build_ai_usage_record, record_ai_usage
from ctf_solver_core.schemas import CATEGORIES, json_dumps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--challenge-id", default="")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--ended-at", default="")
    parser.add_argument("--input-tokens", type=int, required=True)
    parser.add_argument("--output-tokens", type=int, required=True)
    parser.add_argument("--cache-read-tokens", type=int, default=0)
    parser.add_argument("--cache-creation-tokens", type=int, default=0)
    parser.add_argument("--web-search-requests", type=int)
    parser.add_argument("--cost-usd", type=float)
    parser.add_argument("--duration-sec", type=float)
    parser.add_argument("--tool-duration-ms", type=int)
    parser.add_argument("--api-duration-ms", type=int)
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--platform")
    parser.add_argument("--event")
    parser.add_argument("--status", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    record = build_ai_usage_record(
        run_id=args.run_id,
        provider=args.provider,
        model=args.model,
        challenge_id=args.challenge_id,
        session_id=args.session_id,
        started_at=args.started_at,
        ended_at=args.ended_at,
        duration_sec=args.duration_sec,
        input_tokens=args.input_tokens,
        output_tokens=args.output_tokens,
        cache_creation_input_tokens=args.cache_creation_tokens,
        cache_read_input_tokens=args.cache_read_tokens,
        web_search_requests=args.web_search_requests,
        cost_usd=args.cost_usd,
        tool_duration_ms=args.tool_duration_ms,
        api_duration_ms=args.api_duration_ms,
        source="manual",
        notes=args.notes,
        category=args.category or "",
        platform=args.platform or "",
        event=args.event or "",
        status=args.status,
    )
    result = record_ai_usage(record, dry_run=args.dry_run)
    if args.json:
        print(json_dumps(result), end="")
    else:
        print(record["ai_usage_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
