# CTFd Live Smoke Runbook

This runbook is for a manually approved CTFd environment after local CTFd
fixture discovery already works. It is read-only. It does not add exploit
execution, downloads, server acquire, Dreamhack automation, or flag submit.

Use `scripts/ctfd_live_smoke_runbook.py` to print the command plan. The helper
is a checklist generator only; it never performs network requests.

```bash
python3 scripts/ctfd_live_smoke_runbook.py \
  --platform ctfd \
  --event event-name \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid
```

Add `--include-live-command` only after live access is approved. Add
`--include-queue-command` only when queue registration is approved.

## 1. Preflight

Run these before live access:

```bash
git status --short
python3 scripts/doctor.py
python3 scripts/secret_scan.py --strict
python3 scripts/dump_mcp_tools.py --check
```

Expected state:

- git status is clean or every local change is intentional.
- doctor has hard failures 0.
- secret scan is clean.
- canonical MCP server is `ctf_solver`.
- ReVa may be disconnected when Ghidra/ReVa is not running.

## 2. Auth Setup

Use local-only auth material. Do not print raw auth values and do not place auth
files inside the repo.

Browser profile metadata:

```bash
python3 scripts/browser_state_init.py \
  --platform ctfd \
  --event event-name \
  --profile main \
  --storage-state ~/.ctf-solver/browser-auth/ctfd-main.json \
  --json

python3 scripts/browser_state_check.py \
  --platform ctfd \
  --event event-name \
  --profile main \
  --json
```

The check verifies metadata and storage-state file existence only. It must not
read or print storage-state contents.

Cookie file:

```bash
export CTF_CTFD_COOKIE_FILE=~/.ctf-solver/browser-auth/ctfd-cookie.txt
```

Cookie header:

```bash
export CTF_CTFD_COOKIE_HEADER='<redacted-cookie-header>'
```

Prefer `CTF_CTFD_COOKIE_FILE` for shell history hygiene. Both auth sources must
stay local-only.

## 3. Dry-Run First

Run dry-run before adding `--live`:

```bash
python3 scripts/platform_live_smoke.py \
  --platform ctfd \
  --event event-name \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid \
  --mode discovery \
  --no-submit \
  --json
```

Without `--live`, this must not contact the base URL. It should produce planned
actions, policy/profile summaries, and local-only result paths under
`CTF_LIVE_SMOKE_ROOT`.

## 4. Live Read-Only Discovery

After approval, add `--live`:

```bash
python3 scripts/platform_live_smoke.py \
  --platform ctfd \
  --event event-name \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid \
  --mode discovery \
  --live \
  --no-submit \
  --json
```

The CTFd adapter may request only `GET /api/v1/challenges` for smoke discovery.
Smoke mode never submits flags, even if policy allows submission. It must not
store raw API responses, auth values, or browser storage contents.

## 5. Direct Platform Discover

Use direct discovery only after dry-run smoke succeeds:

```bash
python3 scripts/platform_discover.py \
  --platform ctfd \
  --event event-name \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid \
  --live \
  --json
```

The output is normalized for local use. Public metrics and queue events must
use only public-safe aggregate fields.

## 6. Optional Queue Registration

Queue registration is opt-in. Do not queue from live discovery unless
`--queue` is explicit:

```bash
python3 scripts/platform_discover.py \
  --platform ctfd \
  --event event-name \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid \
  --live \
  --queue \
  --json
```

Queued items should contain challenge id, category, local capability, remote
requirement, and other normalized public-safe fields. They must not contain raw
challenge descriptions or raw responses.

## 7. Failure Handling

- `auth_required_or_profile_missing`: register a browser_state profile or
  provide `CTF_CTFD_COOKIE_FILE` / `CTF_CTFD_COOKIE_HEADER` from a local-only
  source, then rerun dry-run before live discovery.
- `ctfd_api_error`: confirm the base URL points to a CTFd-compatible API and
  that discovery is allowed. Do not paste the raw response into repo docs.
- `base_url_missing`: provide `--base-url` or policy `base_url`.
- `network_timeout`: retry only after checking platform availability and local
  network state. Keep retries bounded.
- `ctfd_live_auth_failed`: refresh local auth material without printing it.

## 8. Public-Safe Result Check

Inspect only public-safe counters:

- `actions.discovery.challenge_count`
- `public_metrics.ctfd_live_discovered_count`
- `discovered_count` in any manual summary derived from the JSON
- success booleans and mode labels

Do not copy raw responses, auth values, browser storage_state contents, private
URLs with secrets, challenge descriptions, flags, exploit code, or download
artifacts into `metrics/`, docs, commits, or issue comments.

## 9. What Not To Do

- no submit
- no exploit execution
- no live download
- no server acquire
- no browser storage_state dump
- no raw `~/.claude.json` or `~/.codex/config.toml` inspection
- no live external CTF access from pytest

Regression tests must use local fixtures or local mock servers only.
