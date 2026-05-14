# Platform Automation

P1 resource automation is a policy and queue scaffold. It coordinates multiple
Codex/Claude terminals without storing platform secrets or implementing browser
automation yet.

## Operating Modes

1. User-provided challenge mode: the user gives a file, URL, server, or run
   directory. The worker initializes or resumes that run and may acquire a
   remote lease only when remote testing is needed.
2. Platform login/session discovery mode: a worker registers local-only browser
   profile metadata, then an adapter can discover problems, download files, and
   request servers. The mock/local adapter remains the regression baseline, the
   CTFd adapter adds local CTFd-style fixture support, and the Dreamhack adapter
   adds fixture discovery plus explicit VM control. Real site scraping and
   Playwright login automation are future work.

Never commit cookies, session storage, API keys, tokens, passwords, OAuth data,
emails, account UUIDs, organization UUIDs, private server URLs, writeups,
exploits, flags, raw transcripts, or private run logs.

## Platform Resource Constraints

Platform policies live in YAML. The example config is
`config/platforms.example.yaml`; real configs should normally be generated
outside the repo:

```bash
python3 scripts/platform_config_init.py --platform thcon --event THCON --max-active-vms 1 --output ~/.ctf-solver/platforms/thcon.yaml
python3 scripts/platform_config_init.py --print-template
```

For THCON-like platforms, set `resources.remote_server.max_active_leases: 1`,
`lease_scope: event`, and `release_required_before_next: true`. Workers must not
create a second remote server while an event-scoped lease is active.

For Dreamhack, use `adapter: dreamhack`, `max_active_leases: 1`, and
`lease_scope: platform_event`. Dreamhack is a platform adapter only; the
canonical MCP server name remains `ctf_solver`. VM actions are performed with
`scripts/dreamhack_vm_control.py` and require both `--live` and local-only auth
inputs. The adapter records only action/status/vm-state summaries and redacts
host values; it never stores Dreamhack session values, CSRF values, cookies, raw
responses, flags, exploit code, or private VM URLs. See
`docs/dreamhack-adapter.md`.

Dreamhack private fixtures default to `~/.ctf-solver/fixtures/dreamhack` and can
be moved with `CTF_DREAMHACK_FIXTURE_ROOT`. The repo only allows synthetic dummy
fixtures under `tests/fixtures/dreamhack/`; live response captures, cookies,
session values, CSRF values, and raw platform responses must stay outside the
repo.

Before attaching a real site adapter, use `scripts/platform_live_smoke.py` in
dry-run mode. For CTFd read-only discovery, generate the checklist with
`scripts/ctfd_live_smoke_runbook.py` first. Add `--live` only for explicit
manual smoke checks; smoke mode never submits flags, queue registration requires
explicit `--queue`, and download/server-acquire checks require separate
`--allow-download` or `--allow-server-acquire` flags. CTFd live download also
requires `--live`, writes files under `CTF_DOWNLOAD_ROOT`, and records only
file count/bytes/hashes. See `docs/live-smoke.md` and
`docs/ctfd-live-smoke-runbook.md`.

## Local-First Scheduling

Workers should ask the queue before idling:

```bash
python3 scripts/queue_update.py --platform thcon --event THCON --challenge-id A --category web --state downloaded --local-capable true --remote-required true --local-exploit-ready false --confidence 0.4 --destructive-risk 0.1
python3 scripts/queue_next.py --platform thcon --event THCON --policy ~/.ctf-solver/platforms/thcon.yaml
```

If remote capacity exists, the scheduler returns `acquire_remote` for the
highest-priority remote-ready item. If capacity is blocked, it returns
`do_local_work` for local-capable items that still need triage, analysis,
exploit planning, or local exploit skeleton work. `local_exploit_ready` items
receive a large priority boost so they get remote leases first when capacity is
released.

## Lease Commands

```bash
python3 scripts/resource_acquire.py --platform thcon --event THCON --challenge-id A --run-id RUN_A --resource remote_server --mode primary --policy ~/.ctf-solver/platforms/thcon.yaml
python3 scripts/resource_heartbeat.py --lease-id <lease-id> --once
python3 scripts/resource_release.py --run-id RUN_A --platform thcon --event THCON --all-for-run
```

Dreamhack VM start/restart should go through the platform adapter wrapper so the
lease and VM action stay coupled:

```bash
python3 scripts/dreamhack_vm_control.py --challenge-id 1001 --run-id RUN_A --action start --confirm --live --session-id-file ~/.ctf-solver/auth/dreamhack-session.txt --csrf-token-file ~/.ctf-solver/auth/dreamhack-csrf.txt --json
```

Lease records are stored under `CTF_LEASE_ROOT` or `~/.ctf-solver/leases`.
Queue records are stored under `CTF_QUEUE_ROOT` or `~/.ctf-solver/queue`. Both
paths should remain outside the repo.

## Queue Worker Runner

The P1-3 worker scaffold combines queue state, worker claims, remote lease
policy, verifier state, and finalization state. It does not invoke Codex,
Claude, browser automation, GDB, Docker, Sage, or exploit commands.

```bash
python3 scripts/worker_next.py --platform thcon --event THCON --policy ~/.ctf-solver/platforms/thcon.yaml --require-verifier true
python3 scripts/worker_run_once.py --platform thcon --event THCON --auto-acquire-remote --auto-finalize --require-verifier --json
python3 scripts/worker_loop.py --platform thcon --event THCON --interval-sec 10
python3 scripts/worker_status.py --platform thcon --event THCON --show-claims --show-queue
```

Worker claims are stored under `CTF_WORKER_ROOT` or
`~/.ctf-solver/workers`. Claim records contain `worker_id`, `challenge_id`,
`run_id`, `claimed_at`, `heartbeat_at`, `stale_after_sec`, and `action`.
Non-helper active claims are exclusive per challenge, so another terminal will
not duplicate local work on the same problem. Helper claims are shared and are
only selected when platform sharing policy allows it and an active primary
lease exists.

Actions are:

- `do_local_work`
- `acquire_remote`
- `join_remote_as_helper`
- `verify_solution`
- `finalize_challenge`
- `wait`
- `no_work`

Solved queue items go to `verify_solution` first when `--require-verifier` is
enabled and `<run_dir>/verifier.json` is missing or unsuccessful. Ended items
then go to `finalize_challenge`, and the worker will not select unrelated new
work until finalization is complete.

## Lease Heartbeat

Lease records include `heartbeat_at`, `heartbeat_interval_sec`,
`stale_after_sec`, `renewed_at`, and `renewal_count`. Defaults are a 30 second
heartbeat interval and a 180 second stale threshold. Long-running remote work
should heartbeat its lease:

```bash
python3 scripts/resource_heartbeat.py --lease-id <lease-id> --interval 30
```

`--once` records a single heartbeat and exits. If the worker process or
terminal dies, heartbeats stop and the lease becomes stale after
`stale_after_sec`.

## Stale Lease Recovery

Stale detection uses the last heartbeat or renewal time, plus explicit
`expires_at` when present. Released leases are not active. Helper leases are
invalid when the primary lease is stale or released. `resource_acquire.py`
reclaims stale leases for the platform/event before enforcing
`max_active_leases`, so stale leases are excluded from the active capacity
calculation after they are marked `stale_reclaimed`.

Check before reclaiming:

```bash
python3 scripts/resource_reclaim_stale.py --dry-run
```

Apply only when the target lease is not heartbeating:

```bash
python3 scripts/resource_reclaim_stale.py --apply
```

Reclaim marks the lease with `released_at` and
`release_reason=stale_reclaimed`; it does not print private URLs, session
values, tokens, or cookies. The reclaim script refuses to operate when the
lease root resolves inside the canonical repo.

## Queue Event History

Queue state changes and scheduler decisions are written to
`CTF_QUEUE_ROOT/events.jsonl`. The log is public-safe metadata only and is meant
for multi-terminal debugging:

```bash
python3 scripts/queue_history.py --tail 20
python3 scripts/queue_history.py --platform thcon --event THCON --json
```

Events include queue item creation/update, state and priority changes,
scheduler decisions, remote blockage, local-work selection, helper joins, lease
acquire/release, stale detection/reclaim, worker claim lifecycle, worker action
selection, optional worker auto-acquire/finalize, and finalization.

## Remote Collaboration

If `resources.remote_server.sharing.allowed: true` and the active challenge is
known to be multi-client safe, helper workers may join an active remote
challenge:

- Primary worker: lease owner, destructive action authority, release authority,
  submit authority.
- Helper worker: read-only analysis, non-destructive requests, artifact
  analysis, exploit idea generation.

If sharing is unsafe or disabled, helper assignment is forbidden. Helper workers
must never submit flags, restart services, release remote servers, delete remote
state, or perform destructive actions. A helper must stop when the primary
lease becomes stale or released.

## Multi-Terminal Debugging

Use the queue history first when workers appear stuck. `remote_blocked` means a
remote-ready item existed but capacity was occupied. `local_work_selected` means
the scheduler intentionally chose local-first progress while remote capacity was
blocked. `wait_selected` means no remote capacity, no eligible local work, and no
safe helper assignment were available.

Use `worker_status.py` when contention is claim-related. It reports active and
stale claim counts, active and stale lease counts, queue counts by state, and
worker action counts without printing private paths, raw transcripts, flags, or
tokens.

## THCON-Like Stale Worker Example

With `max_active_leases: 1`, worker A acquires the event-scoped remote server and
starts testing. If its terminal closes, worker B initially sees capacity blocked.
After `stale_after_sec`, worker B runs `resource_reclaim_stale.py --dry-run` to
confirm the lease is stale, then `--apply` to mark it reclaimed. A new
`resource_acquire.py` call can then acquire the single allowed remote lease.

## Safe Reclaim Procedure

1. Inspect `queue_history.py --tail 20` to confirm why workers are waiting.
2. Run `resource_reclaim_stale.py --dry-run` and verify only stale leases are
   listed.
3. Confirm there is no active heartbeat for that lease.
4. Run `resource_reclaim_stale.py --apply`.
5. Re-run `queue_next.py`; remote-ready work should now be schedulable.

Do not reclaim a lease that is still heartbeating.

## Finalization

Every challenge end state still goes through `scripts/challenge_finalize.py`.
By default finalization releases active leases for the run and marks a matching
queue item as `finalized`. Release records keep `release_reason=finalized`.
Use `--keep-lease` only when a human intentionally keeps a remote resource alive
for handoff; that choice is also recorded in queue event history.

Public-safe metrics may record aggregate resource timing and collaboration
booleans, but must not include URLs, lease metadata with secrets, flags,
writeups, exploit code, or raw transcripts.

Worker metrics are optional aggregate fields such as worker action count, wait
count, claim reclaim count, auto-finalize usage, and require-verifier usage.
Raw worker IDs and hostnames should be omitted or hashed.

Browser/platform discovery, download, server adapter, submission scaffolds, and
browser action automation are documented in `docs/browser-platform-automation.md`
and `docs/browser-actions.md`. CTFd-specific fixture mode and policy details
are documented in `docs/ctfd-adapter.md`.

## Limitations

- Worker runner does not invoke Codex or Claude automatically.
- Full browser solver and real-site browser adapters are future phases.
- GDB-specific persistent sessions are a future phase.
- Verifier execution remains explicit because the worker cannot infer the
  correct exploit command safely.
