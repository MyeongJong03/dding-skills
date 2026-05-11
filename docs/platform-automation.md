# Platform Automation

P1 resource automation is a policy and queue scaffold. It coordinates multiple
Codex/Claude terminals without storing platform secrets or implementing browser
automation yet.

## Operating Modes

1. User-provided challenge mode: the user gives a file, URL, server, or run
   directory. The worker initializes or resumes that run and may acquire a
   remote lease only when remote testing is needed.
2. Platform login/session discovery mode: a future worker uses a local browser
   or session profile to discover problems, download files, and request servers.
   Login/session storage must stay outside the repo. Browser/session automation
   is future P1-2 work and is not implemented in this scaffold.

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

Lease records are stored under `CTF_LEASE_ROOT` or `~/.ctf-solver/leases`.
Queue records are stored under `CTF_QUEUE_ROOT` or `~/.ctf-solver/queue`. Both
paths should remain outside the repo.

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
acquire/release, stale detection/reclaim, and finalization.

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
