# Browser / Platform Automation

P1-4 adds a safe scaffold for platform-driven CTF workflows. P1-6 adds the
optional Playwright browser action layer used by future adapters and solvers. It
does not log in to real sites, scrape Dreamhack/THCON, submit flags by default,
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
| Browser action session metadata | `Path.home() / ".ctf-solver" / "browser"` | `CTF_BROWSER_ROOT` |
| Browser screenshots/artifacts | `Path.home() / ".ctf-solver" / "browser-artifacts"` | `CTF_BROWSER_ARTIFACT_ROOT` |
| Browser profile metadata | `Path.home() / ".ctf-solver" / "browser-states"` | `CTF_BROWSER_STATE_ROOT` |
| Live platform smoke results | `Path.home() / ".ctf-solver" / "live-smoke"` | `CTF_LIVE_SMOKE_ROOT` |
| Platform automation records | `Path.home() / ".ctf-solver" / "platforms"` | `CTF_PLATFORM_AUTOMATION_ROOT` |
| Downloaded private challenge files | `Path.home() / "CTF" / "downloads"` | `CTF_DOWNLOAD_ROOT` |

`scripts/doctor.py` warns if any of these roots resolve inside the repo.
Storage state files, cookies, tokens, downloaded challenge files, screenshots,
browser action metadata, server records, writeups, exploits, flags, raw
transcripts, and private run logs must stay out of git.

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

## Browser Actions

Browser action automation is documented in `docs/browser-actions.md`. It is
optional and requires:

```bash
uv run --with playwright python -c "import playwright; print('ok')"
uv run --with playwright python -m playwright install chromium
```

On Homebrew Python, do not use `--break-system-packages` to force a system pip
install. Use uv or a repo-external venv as documented in
`docs/browser-actions.md`.

Start sessions with a `run_id`, then use DOM actions:

```bash
python3 scripts/browser_start.py --run-id RUN1 --challenge-id CHAL1 --json
python3 scripts/browser_goto.py --browser-session-id <browser_session_id> --url 'data:text/html,<title>Local</title>' --json
python3 scripts/browser_eval.py --browser-session-id <browser_session_id> --expression 'document.title' --json
python3 scripts/browser_close.py --browser-session-id <browser_session_id> --json
```

Regression tests must use local HTML, data URLs, or mock servers. External CTF
sites are manual-only. Cookie, network, console, and eval outputs are bounded
and redacted. Screenshots are saved under `CTF_BROWSER_ARTIFACT_ROOT`, not in
the repo.

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
JSON/HTML fixtures, can perform opt-in read-only discovery through
`/api/v1/challenges`, copies local attachment fixtures, and blocks generic live
download, server provisioning, and submit paths.

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

python3 scripts/platform_discover.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --base-url https://ctfd.example.invalid \
  --live \
  --queue \
  --json
```

Discovered fields are `challenge_id`, `name`, `category`, optional `url`,
optional `external_id`, `value`, `tags`, `solves`, `files`,
`remote_required`, and `local_capable`. `--queue` creates or updates queue
items with state `discovered` and records a public-safe queue event. Live CTFd
discovery requires `--live`; no raw API response or full description is stored.

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
fixture mode. Live CTFd attachment download is available only as a manual
opt-in path with both `--live` and `--allow-download`.

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
by default. It also closes browser action sessions associated with the run
unless `--keep-browser-sessions` is supplied. Use `--keep-server`,
`--keep-lease`, or `--keep-browser-sessions` only for an explicit handoff.

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
- `ctfd_live_discovery_attempted`
- `ctfd_live_discovery_success`
- `ctfd_live_discovered_count`
- `ctfd_live_download_attempted`
- `ctfd_live_download_success`
- `ctfd_live_downloaded_count`
- `ctfd_live_downloaded_bytes`
- `submission_policy`
- `platform_adapter`
- `live_smoke_count`
- `live_smoke_mode`
- `live_smoke_success`
- `live_smoke_discovered_count`
- `live_smoke_downloaded_count`
- `live_smoke_server_acquire_attempted`
- `browser_session_count`
- `browser_actions_count`
- `browser_screenshot_count`
- `browser_network_event_count`

They must not include cookies, tokens, private URLs, flags, raw response bodies,
downloaded file absolute paths, browser artifact paths, writeups, exploit code,
or transcripts.

## Manual Smoke Tests

`platform_smoke_test.py` is the legacy dry-run-only scaffold. The manual opt-in
framework is `platform_live_smoke.py`. Start with dry-run:

```bash
python3 scripts/platform_smoke_test.py --platform thcon --event THCON --adapter generic
python3 scripts/ctfd_live_smoke_runbook.py --platform ctfd --event local-fixture --base-url https://ctfd.example.invalid
python3 scripts/platform_live_smoke.py --platform ctfd --event local-fixture --adapter ctfd --mode discovery --base-url https://ctfd.example.invalid --json
```

`platform_live_smoke.py --live` is required before any live network-capable
adapter path may run. For CTFd, discovery mode uses `/api/v1/challenges` and
returns only bounded normalized summaries. Smoke mode never submits flags.
Queue registration uses `platform_discover.py --queue` only when that flag is
explicitly supplied. `ctfd_live_smoke_runbook.py` is a no-network command
generator for the dry-run-first procedure.
CTFd live download requires both `--live` and `--allow-download`; without either
flag it must not open the network. Downloaded files stay under
`CTF_DOWNLOAD_ROOT` outside the repo, and queue state changes only when
`platform_download.py --queue` is explicit. Server acquire requires
`--allow-server-acquire` and still respects `max_active_leases`. Browser profile
metadata is checked through `browser_state_check`-equivalent helpers without
reading storage state contents. If the API needs auth, use a local-only
`CTF_CTFD_COOKIE_HEADER` or repo-external `CTF_CTFD_COOKIE_FILE`; do not print
or commit either value. Results are written under `CTF_LIVE_SMOKE_ROOT` and
only public-safe summaries may be reflected in metrics. Regression tests remain
mock/local only.

See [live-smoke.md](live-smoke.md) and
[ctfd-live-smoke-runbook.md](ctfd-live-smoke-runbook.md).

## Limitations

- Real Dreamhack and THCON-like adapters are future work.
- CTFd server acquire and submit are unsupported in the generic adapter; live
  download is opt-in and attachment-only.
- Real site browser login automation is optional future work.
- No live network regression tests.
- No default flag auto-submit.
- No Codex/Claude subprocess orchestration.
- No full browser solver, full exploit solver, GDB-specific automation, Docker,
  Sage, or live browser dependency in tests.
