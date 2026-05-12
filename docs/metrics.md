# Public-Safe Metrics

`metrics/summary.jsonl` and `metrics/dashboard.md` are intended to be safe for GitHub. They are aggregate operational records, not challenge writeups.

`summary.jsonl` is created on the first successful `scripts/update_metrics.py` run; the repo starts with `metrics/.gitkeep` and an empty dashboard scaffold.

## Public Record Fields

- `timestamp`
- `run_id`
- `platform`
- `event`
- `category`
- `status`
- `duration_sec`
- `tool_call_counts`
- `cleanup_bytes_saved`
- `writeup_generated`
- `exploit_included`
- optional `remote_wait_time_sec`
- optional `local_prework_time_sec`
- optional `remote_lease_time_sec`
- optional `resource_blocked_count`
- optional `shared_remote_used`
- optional `helper_workers_used`
- optional `local_ready_before_remote`
- optional `verifier_success`
- optional `verifier_flag_found`
- optional `verifier_target`
- optional `verifier_attempts`
- optional `verifier_duration_sec`
- optional `worker_id_hash`
- optional `worker_count`
- optional `worker_action_count`
- optional `worker_wait_count`
- optional `worker_claim_reclaim_count`
- optional `auto_finalize_used`
- optional `require_verifier_used`
- optional `model_tooling_summary`

Challenge names are excluded by default. Use `--include-challenge-name` only for private repos or events where challenge names are intentionally public.

`run_id` is stored to prevent duplicate appends. Public metrics updates require `--run-dir` or `--run-id`. Re-running `scripts/update_metrics.py` for an existing `run_id` is skipped by default. Use `--replace` or `--force` only when the existing public-safe entry should be replaced.

## Forbidden Public Data

Do not put the following in public metrics:

- flags
- exploit code
- raw transcripts
- private absolute paths with usernames
- cookies, tokens, API keys, OAuth data, passwords, private keys
- account email, account UUID, organization UUID
- detailed artifact paths
- private remote URLs or secret-bearing lease metadata
- verifier raw output, raw evidence path, or exploit command
- raw worker ID or hostname

`scripts/update_metrics.py --check` validates existing public metrics before git sync.

Metrics writes use a global lock and atomic file replacement. Public records must remain free of private absolute paths even when generated from private run directories.

Verifier fields are copied only as public-safe summaries from
`<run_dir>/verifier.json` or finalization state. `verifier_flag_found` is a
boolean and must never be replaced with the flag text.

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
