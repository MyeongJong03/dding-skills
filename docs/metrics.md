# Public-Safe Metrics

`metrics/summary.jsonl` and `metrics/dashboard.md` are intended to be safe for GitHub. They are aggregate operational records, not challenge writeups.

`summary.jsonl` is created on the first successful `scripts/update_metrics.py` run; the repo starts with `metrics/.gitkeep` and an empty dashboard scaffold.

## Public Record Fields

- `timestamp`
- `platform`
- `event`
- `category`
- `status`
- `duration_sec`
- `tool_call_counts`
- `cleanup_bytes_saved`
- `writeup_generated`
- `exploit_included`
- optional `model_tooling_summary`

Challenge names are excluded by default. Use `--include-challenge-name` only for private repos or events where challenge names are intentionally public.

## Forbidden Public Data

Do not put the following in public metrics:

- flags
- exploit code
- raw transcripts
- private absolute paths with usernames
- cookies, tokens, API keys, OAuth data, passwords, private keys
- account email, account UUID, organization UUID
- detailed artifact paths

`scripts/update_metrics.py --check` validates existing public metrics before git sync.

## Dashboard

`metrics/dashboard.md` is generated from `summary.jsonl` and includes:

- total attempts
- solved count
- abandoned/skipped count
- solve rate
- by-category table
- by-platform/event table
- writeup generation count
- exploit inclusion count
- cleanup bytes saved total
- last updated
