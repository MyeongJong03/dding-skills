# Queue Worker Runner

P1-3 adds a local worker/orchestrator scaffold for multi-terminal CTF work. It
coordinates existing queue, remote lease, verifier, and finalization helpers.
It does not invoke Codex, Claude, browser automation, GDB, Docker, Sage, or
exploit commands.

## Model

Each terminal may run a worker with a `worker_id`. Before doing challenge work,
the worker claims a queue item under `CTF_WORKER_ROOT` or
`~/.ctf-solver/workers`. Active non-stale claims are exclusive per challenge,
so another worker will not duplicate the same local work. Helper mode is the
exception: it is only selected when the platform policy allows remote sharing
and a primary remote lease exists.

Claim fields:

- `worker_id`
- `challenge_id`
- `run_id`
- `claimed_at`
- `heartbeat_at`
- `stale_after_sec`
- `action`

## Actions

- `do_local_work`: claim local triage, analysis, or exploit-planning work.
- `acquire_remote`: claim a remote-ready item and suggest or perform lease acquire.
- `join_remote_as_helper`: join an active shared remote challenge as read-only helper.
- `verify_solution`: run `verify_run.py` before solved finalization.
- `finalize_challenge`: run `challenge_finalize.py` before moving on.
- `wait`: queue exists but is blocked by claims, policy, or capacity.
- `no_work`: no selectable queue item exists.

## Commands

```bash
python3 scripts/worker_next.py --platform thcon --event THCON --worker-id w1 --require-verifier true
python3 scripts/worker_run_once.py --platform thcon --event THCON --worker-id w1 --auto-acquire-remote --auto-finalize --require-verifier --json
python3 scripts/worker_loop.py --platform thcon --event THCON --worker-id w1 --interval-sec 10 --max-iterations 5
python3 scripts/worker_status.py --platform thcon --event THCON --show-claims --show-queue --json
```

`worker_next.py` returns JSON with `action`, `challenge_id`, `run_id`,
`reason`, `worker_id`, `claimed`, `priority_score`, and an optional
`suggested_command`.

`worker_run_once.py` executes only orchestration-safe actions when explicitly
enabled:

- `--auto-acquire-remote` calls the lease helper.
- `--auto-finalize` calls finalization.
- verifier and local exploit work remain suggested commands/manual work.

`worker_loop.py` repeats `worker_run_once.py`, heartbeats active claims, sleeps
between iterations, and handles Ctrl-C gracefully.

## Scheduling Policy

The worker chooses ended work before new work. With `--require-verifier`,
`solved` queue items go to `verify_solution` unless a successful verifier
already exists. Ended items then go to `finalize_challenge`; the worker does
not advance to unrelated work until finalization succeeds.

For active work, remote-ready items with available capacity choose
`acquire_remote`. If remote capacity is unavailable and a local-capable item
exists, the worker chooses `do_local_work`. If no local work exists and sharing
is allowed, it may choose `join_remote_as_helper`.

## Event Log

Worker events are appended to `CTF_QUEUE_ROOT/events.jsonl`:

- `worker_claimed`
- `worker_claim_heartbeat`
- `worker_claim_released`
- `worker_claim_stale_detected`
- `worker_claim_stale_reclaimed`
- `worker_action_selected`
- `worker_wait`
- `worker_auto_finalize`
- `worker_auto_acquire_remote`

Events contain public-safe metadata only. Raw flags, exploit code, transcripts,
private run logs, writeup contents, tokens, cookies, private URLs, and verifier
raw evidence must not be written to repo metrics.

## Metrics

Public-safe metrics may include optional aggregate worker fields such as
worker count, worker action/wait count, claim reclaim count,
`auto_finalize_used`, and `require_verifier_used`. Raw worker IDs and hostnames
should be omitted or hashed.

## Limitations

- No automatic Codex or Claude invocation.
- No browser automation.
- No GDB-specific session automation.
- No full verifier reconstruction; verifier command choice remains explicit.
