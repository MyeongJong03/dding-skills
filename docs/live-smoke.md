# Live Platform Smoke

`scripts/platform_live_smoke.py` is a manual, opt-in framework for checking
whether platform policies, browser profile metadata, read-only discovery,
downloads, and server lease gates are wired correctly before a real site
adapter is implemented.

The default is dry-run and no-network. Without `--live`, the command validates
configuration and prints what would happen. It does not contact external CTF
sites.

## Storage

Live smoke output is local-only:

```text
CTF_LIVE_SMOKE_ROOT/<smoke_id>/result.json
CTF_LIVE_SMOKE_ROOT/<smoke_id>/summary.md
```

Default root:

```text
Path.home() / ".ctf-solver" / "live-smoke"
```

Override:

```bash
export CTF_LIVE_SMOKE_ROOT="$HOME/.ctf-solver/live-smoke"
```

Do not place this root inside the repo. `scripts/doctor.py` reports the
resolved path and warns if it is repo-internal.

## Modes

- `dry-run`: validate policy/profile metadata only.
- `discovery`: read-only challenge discovery.
- `download`: challenge file download smoke, requires `--allow-download`.
- `server-status`: public-safe server and lease status summary.
- `server-acquire`: server acquire scaffold, requires
  `--allow-server-acquire`.
- `full-readonly`: discovery plus server status, no download, no acquire, no
  submit.

## Dry-Run First

```bash
python3 scripts/platform_live_smoke.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --base-url https://ctfd.example.invalid \
  --mode discovery \
  --json
```

This does not open the URL because `--live` is absent. Output includes bounded
policy/profile summaries, planned actions, and result file paths.

## Live Opt-In

Live mode must be explicit:

```bash
python3 scripts/platform_live_smoke.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid \
  --mode discovery \
  --live \
  --json
```

If the policy requires browser profile auth, `--profile` must name metadata
registered with `browser_state_init.py`. The smoke check only verifies metadata
and storage-state file existence; it never reads or prints cookies, tokens, or
storage state contents.

## Downloads

Downloads require both platform policy and an explicit CLI flag:

```bash
python3 scripts/platform_live_smoke.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --challenge-id ctfd/local-fixture/web/web-baby \
  --base-url https://ctfd.example.invalid \
  --mode download \
  --live \
  --allow-download \
  --json
```

Result summaries record file counts, sizes, relative names, and hashes. They do
not store raw response bodies by default.

## Server Status And Acquire

Status is read-only:

```bash
python3 scripts/platform_live_smoke.py \
  --platform thcon \
  --event THCON \
  --adapter mock \
  --mode server-status \
  --live \
  --json
```

Acquire requires `--allow-server-acquire` and still respects the platform
resource policy:

```bash
python3 scripts/platform_live_smoke.py \
  --platform thcon \
  --event THCON \
  --policy ~/.ctf-solver/platforms/thcon.yaml \
  --adapter mock \
  --challenge-id web-1 \
  --run-id RUN_A \
  --mode server-acquire \
  --live \
  --allow-server-acquire \
  --json
```

For THCON-like one-server platforms, keep:

```yaml
resources:
  remote_server:
    provisioning: true
    max_active_leases: 1
    lease_scope: event
automation:
  allow_server_create: ask
  allow_submission: ask
```

The acquire smoke calls the normal lease path, so it will not create a second
event-scoped server while an active primary lease exists.

## No Submit

Smoke mode never submits flags. This is true even if
`automation.allow_submission: true`; the result always records
`submission.attempted=false`. Use the normal platform submission command only
outside smoke mode and only when the policy explicitly allows it.

## Metrics

The result includes a public-safe `public_metrics` object. Allowed fields are:

- `live_smoke_count`
- `live_smoke_mode`
- `live_smoke_success`
- `live_smoke_discovered_count`
- `live_smoke_downloaded_count`
- `live_smoke_server_acquire_attempted`

These fields can be passed to `scripts/update_metrics.py`. Do not put raw
responses, flags, cookies, tokens, private URLs with secrets, storage state,
download contents, screenshots, or private absolute paths in `metrics/`.

## Regression Tests

Tests must stay local/mock only. Use `--source` with a local fixture for mock or
fixture-first adapters. Do not add pytest cases that contact live CTF sites,
download real challenge files, provision real servers, submit flags, start
Playwright against external sites, or depend on real credentials.

## Never Commit

- live smoke result directories
- raw response bodies or HAR files
- browser storage state, cookies, tokens, OAuth values, passwords, account data
- flags, exploit code, raw transcripts, verifier evidence
- private URLs with secrets or private local paths
