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
python3 scripts/resource_release.py --run-id RUN_A --platform thcon --event THCON --all-for-run
```

Lease records are stored under `CTF_LEASE_ROOT` or `~/.ctf-solver/leases`.
Queue records are stored under `CTF_QUEUE_ROOT` or `~/.ctf-solver/queue`. Both
paths should remain outside the repo.

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
state, or perform destructive actions.

## Finalization

Every challenge end state still goes through `scripts/challenge_finalize.py`.
By default finalization releases active leases for the run and marks a matching
queue item as `finalized`. Use `--keep-lease` only when a human intentionally
keeps a remote resource alive for handoff.

Public-safe metrics may record aggregate resource timing and collaboration
booleans, but must not include URLs, lease metadata with secrets, flags,
writeups, exploit code, or raw transcripts.
