# Dreamhack Adapter

Dreamhack is a platform adapter, not the canonical MCP server name. The MCP
server remains `ctf_solver`; Dreamhack-specific platform automation is selected
with `--adapter dreamhack` or the policy entry in `config/platforms.example.yaml`.

## Scope

This scaffold covers:

- Local fixture discovery for problem metadata
- Local fixture attachment copy into `CTF_DOWNLOAD_ROOT`
- VM `start`, `stop`, `restart`, and `status` actions through an explicit live
  command
- Remote-server lease integration for one Dreamhack VM per policy scope
- Public-safe queue events and metrics counters

It does not implement exploit execution, full solver automation, browser login,
raw response storage, or flag submission.

## Discovery

Discovery is fixture-first. Tests and regression runs must use local JSON or
HTML fixtures:

```bash
DH_FIXTURE_ROOT="${CTF_DREAMHACK_FIXTURE_ROOT:-$HOME/.ctf-solver/fixtures/dreamhack}"
python3 scripts/platform_discover.py \
  --platform dreamhack \
  --event dreamhackWargame \
  --adapter dreamhack \
  --source "$DH_FIXTURE_ROOT/discovery.json" \
  --queue \
  --json
```

Live Dreamhack discovery is intentionally unsupported in this scaffold. Passing
a URL without `--live` is blocked as a live-mode request, and passing `--live`
returns an unsupported-live-discovery result.

## Private Fixtures

Private Dreamhack fixtures are local-only. The default private fixture root is
`~/.ctf-solver/fixtures/dreamhack`; set `CTF_DREAMHACK_FIXTURE_ROOT` to override
it. Keep real Dreamhack discovery/detail/download responses, account metadata,
session values, CSRF values, cookies, raw platform responses, and private VM
URLs out of the repo.

The repo may contain dummy parser fixtures only under
`tests/fixtures/dreamhack/`. Those files must be synthetic and must not be
copied from live Dreamhack responses. The adapter rejects repo-local fixture
sources outside that dummy fixture directory and rejects fixture JSON containing
Dreamhack auth/session/cookie/raw-response field names.

`scripts/doctor.py` prints the resolved private fixture root and warns when it
resolves inside the repo.

## Attachments

Fixture downloads copy local `files`, `attachments`, `handouts`, or `downloads`
entries into `CTF_DOWNLOAD_ROOT`. Network attachment download is not
implemented.

```bash
DH_FIXTURE_ROOT="${CTF_DREAMHACK_FIXTURE_ROOT:-$HOME/.ctf-solver/fixtures/dreamhack}"
python3 scripts/platform_download.py \
  --platform dreamhack \
  --event dreamhackWargame \
  --adapter dreamhack \
  --challenge-id dreamhack/dreamhackwargame/web/web-baby \
  --source "$DH_FIXTURE_ROOT/detail.json" \
  --json
```

Repo-internal download destinations remain blocked unless
`--allow-repo-dest` is explicit.

## VM Control

Use the Dreamhack VM control script for live VM actions:

```bash
python3 scripts/dreamhack_vm_control.py \
  --challenge-id 1001 \
  --run-id RUN_ID \
  --action start \
  --confirm \
  --live \
  --session-id-file ~/.ctf-solver/auth/dreamhack-session.txt \
  --csrf-token-file ~/.ctf-solver/auth/dreamhack-csrf.txt \
  --json
```

`start` and `restart` acquire a remote-server lease before the live request.
`stop` releases matching server records and leases after a successful live
request. `status` returns a public-safe summary without changing leases.

Local-only auth may be provided through CLI arguments, repo-external files, or
environment variables:

- `CTF_DREAMHACK_SESSION_ID`
- `CTF_DREAMHACK_CSRF_TOKEN`

Prefer files or environment variables over CLI arguments when shell history is
a concern. Auth values are never printed, written to server records, added to
queue events, or stored in metrics.

The public VM action summary includes only:

- `action`
- `challenge_id`
- `status`
- `status_code`
- `vm_state`
- redacted host presence
- `port` when available
- boolean auth-configuration flags

## Resource Policy

The example Dreamhack policy sets:

```yaml
resources:
  remote_server:
    provisioning: true
    max_active_leases: 1
    lease_scope: platform_event
    sharing:
      allowed: false
```

This prevents helper workers from starting a second VM while an event-scoped
Dreamhack lease is active. Queue and worker logic can still select local-first
work while the VM slot is occupied.

## Metrics

Only public-safe counters should be recorded:

- `dreamhack_vm_action_attempted`
- `dreamhack_vm_action_success`
- `dreamhack_vm_active_count`

Do not store raw Dreamhack responses, browser storage state, auth values, VM
URLs, flags, exploit code, or private transcripts in repo metrics.
