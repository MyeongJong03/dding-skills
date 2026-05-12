# Browser / Platform Automation

P1-4 adds a safe scaffold for platform-driven CTF workflows. It does not log in
to real sites, scrape Dreamhack/THCON, run Playwright, submit flags by default,
or solve challenges. The generic CTFd adapter is fixture-first and does not use
live network access unless a future manual smoke command explicitly opts in.

## Two Modes

User-provided challenge mode remains supported: the user gives a file, URL,
server, or run directory, and the lifecycle starts from that artifact.

Platform login/session discovery mode is the future path: the user provides a
local browser/session profile, then an adapter can discover challenges, download
files, request servers, check status, and enqueue work. P1-4 only stores profile
metadata and runs mock/local fixtures.

## Local-Only Roots

| Purpose | Default | Override |
| --- | --- | --- |
| Browser profile metadata | `Path.home() / ".ctf-solver" / "browser-states"` | `CTF_BROWSER_STATE_ROOT` |
| Platform automation records | `Path.home() / ".ctf-solver" / "platforms"` | `CTF_PLATFORM_AUTOMATION_ROOT` |
| Downloaded private challenge files | `Path.home() / "CTF" / "downloads"` | `CTF_DOWNLOAD_ROOT` |

`scripts/doctor.py` warns if any of these roots resolve inside the repo.
Storage state files, cookies, tokens, downloaded challenge files, server records,
writeups, exploits, flags, raw transcripts, and private run logs must stay out
of git.

## Register Browser State

`browser_state_init.py` creates metadata only. It never opens or prints storage
state contents.

```bash
python3 scripts/browser_state_init.py \
  --platform thcon \
  --event THCON \
  --profile main \
  --print-login-instructions

python3 scripts/browser_state_init.py \
  --platform thcon \
  --event THCON \
  --profile main \
  --storage-state ~/.ctf-solver/browser-auth/thcon-main.json \
  --json

python3 scripts/browser_state_check.py --platform thcon --event THCON --profile main --json
```

If `--storage-state` points inside the repo, registration is refused. The check
command verifies only metadata existence and file existence.

## Adapter Interface

`ctf_solver_core/platform_adapters.py` defines the adapter surface:

- `discover_challenges`
- `download_files`
- `create_server`
- `release_server`
- `server_status`
- `submit_flag`

The `generic` adapter intentionally returns a clear not-implemented error. The
`mock` adapter parses local JSON/HTML fixtures, copies local files, creates fake
server records under the platform automation root, and simulates submission only
when policy explicitly allows it. The `ctfd` adapter parses CTFd-like local
JSON/HTML fixtures, normalizes CTFd challenge records, copies local attachment
fixtures, blocks server provisioning, and keeps live network behavior opt-in
manual-only.

## Discovery

Discovery respects `automation.allow_problem_discovery`.

```bash
python3 scripts/platform_discover.py \
  --platform thcon \
  --event THCON \
  --adapter mock \
  --source fixtures/challenges.json \
  --queue \
  --json

python3 scripts/platform_discover.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --source fixtures/ctfd-challenges.json \
  --queue \
  --json
```

Discovered fields are `challenge_id`, `name`, `category`, optional `url`,
optional `files`, optional `remote_required`, and optional `local_capable`.
`--queue` creates or updates queue items with state `discovered` and records a
public-safe queue event.

## Download

Downloads respect `automation.allow_file_download`. The default destination is
outside the repo:

```text
CTF_DOWNLOAD_ROOT/<platform>/<event>/<challenge_id>/
```

```bash
python3 scripts/platform_download.py \
  --platform thcon \
  --event THCON \
  --challenge-id web-1 \
  --adapter mock \
  --source fixtures/challenges.json \
  --json
```

The mock adapter copies local fixture files and writes `download_metadata.json`
with platform, event, challenge id, relative file names, sizes, SHA-256 hashes,
total size, combined SHA-256, and timestamp. It does not write cookies, tokens,
URLs with secrets, or private absolute paths to public metrics.

For CTFd fixtures, file entries may be local paths relative to the fixture file
or dictionaries with `name` and `path`/`source`. HTTP file URLs are refused in
fixture mode; live download support belongs to a manual opt-in phase.

Repo-internal destinations are refused unless `--allow-repo-dest` is explicit.

See `docs/ctfd-adapter.md` for CTFd-specific fixture and command examples.

## Server Acquire / Release

Server creation is tied to `remote_server` leases. The scaffold acquires a lease
before calling the adapter create hook. If `max_active_leases=1` is already
occupied, server creation is not attempted.

```bash
python3 scripts/platform_server_acquire.py \
  --platform thcon \
  --event THCON \
  --challenge-id web-1 \
  --run-id RUN1 \
  --adapter mock \
  --confirm \
  --json

python3 scripts/platform_server_status.py --platform thcon --event THCON --adapter mock --json

python3 scripts/platform_server_release.py \
  --platform thcon \
  --event THCON \
  --run-id RUN1 \
  --adapter mock \
  --reason manual_release \
  --json
```

For `allow_server_create: ask`, `platform_server_acquire.py` returns
`requires_confirmation` unless `--confirm` is supplied. Disabled policy refuses
the action. Helper role cannot create or release servers.

## THCON-Like One-Server Policy

Use an event-scoped lease:

```yaml
resources:
  remote_server:
    provisioning: true
    max_active_leases: 1
    lease_scope: event
    release_required_before_next: true
    sharing:
      allowed: false
      max_workers: 1
automation:
  allow_problem_discovery: true
  allow_file_download: true
  allow_server_create: ask
  allow_submission: ask
```

If acquire fails because the single lease is active, workers should continue
local-capable queue work. `local_exploit_ready` items get remote priority when
capacity is released.

## Primary / Helper Rules

Primary worker:

- owns the lease
- may create/restart/release server when policy allows it
- may submit flags only when submission policy is explicitly true
- performs destructive actions

Helper worker:

- read-only analysis
- non-destructive requests
- artifact review and exploit idea generation
- no server restart/release
- no submission

Helpers may join only when platform sharing policy allows it and an active
primary lease exists.

## Submission Safety

`platform_submit.py` does not submit unless `automation.allow_submission: true`.
`ask` and disabled modes return a blocked result. Helper role is always blocked.
CLI output redacts the flag, and public metrics must store only aggregate
submission booleans/policy labels.

## Lifecycle And Metrics

`challenge_finalize.py` releases local platform server records and remote leases
by default. Use `--keep-server` or `--keep-lease` only for an explicit handoff.

Public metrics may include:

- `platform_discovery_count`
- `downloaded_file_count`
- `downloaded_bytes`
- `ctfd_challenge_count`
- `ctfd_download_count`
- `server_acquire_attempted`
- `server_acquire_success`
- `server_release_count`
- `submission_attempted`
- `ctfd_submit_attempted`
- `submission_policy`
- `platform_adapter`

They must not include cookies, tokens, private URLs, flags, raw response bodies,
downloaded file absolute paths, writeups, exploit code, or transcripts.

## Manual Smoke Tests

`platform_smoke_test.py` is dry-run only by default. It prints planned checks for
manual adapter validation and does not perform live network activity.

```bash
python3 scripts/platform_smoke_test.py --platform thcon --event THCON --adapter generic
```

Live CTFd smoke tests are future manual work, must require `--live`, and must not
be regression tests.

## Limitations

- Real Dreamhack and THCON-like adapters are future work.
- CTFd live network access is a manual opt-in future path.
- Playwright login automation is optional future work.
- No live network regression tests.
- No default flag auto-submit.
- No Codex/Claude subprocess orchestration.
- No full browser solver, full exploit solver, GDB-specific automation, Docker,
  Sage, or live browser dependency in tests.
