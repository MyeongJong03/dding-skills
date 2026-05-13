# Generic CTFd Adapter

The CTFd adapter is a first real platform-family adapter with local fixture
support. It is not a site-specific scraper and does not assume server
provisioning buttons or custom deployment endpoints.

## Supports

- CTFd API-like discovery fixtures with `success` and `data`
- CTFd-like HTML discovery fixtures with `data-*` challenge attributes
- Challenge detail fixtures with description, files, connection info, hints,
  tags, and state
- Local attachment fixture copy to `CTF_DOWNLOAD_ROOT`
- Queue registration through `platform_discover.py --queue`
- Manual opt-in live read-only discovery from `/api/v1/challenges`
- Manual opt-in live attachment download from challenge detail only with
  `--live` and `--allow-download`
- Policy-gated submit scaffold with flag redaction
- Public-safe aggregate metrics fields for CTFd counts

## Fixture Discovery

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "web baby",
      "category": "web",
      "type": "standard",
      "solves": 0,
      "value": 100,
      "tags": [{"name": "starter"}],
      "files": []
    }
  ]
}
```

```bash
python3 scripts/platform_discover.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --source fixtures/ctfd-challenges.json \
  --queue \
  --json
```

Challenge IDs are stable slug paths such as
`ctfd/local-fixture/web/web-baby`. Queue records store only normalized public
fields, not full descriptions or raw responses.

## Detail And Downloads

Detail fixtures may contain one CTFd-style object under `data`:

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "web baby",
    "category": "web",
    "description": "local-only challenge text",
    "files": [{"name": "handout.txt", "path": "attachments/handout.txt"}],
    "connection_info": "nc example.invalid 31337",
    "tags": [{"name": "starter"}],
    "hints": []
  }
}
```

```bash
python3 scripts/platform_download.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --challenge-id ctfd/local-fixture/web/web-baby \
  --source fixtures/ctfd-detail.json \
  --queue \
  --json
```

Files are copied to:

```text
CTF_DOWNLOAD_ROOT/<platform>/<event>/<challenge_id>/
```

The metadata file records names, sizes, and SHA-256 hashes. Repo-internal
destinations are refused unless `--allow-repo-dest` is explicit. Queue state is
updated only when `--queue` is explicit; use `--queue-state downloaded` or
`--queue-state local_triage`.

## Live Mode

Regression tests must use local fixtures or local mock HTTP servers only. Live
CTFd discovery is manual and opt-in. Without `--live`, neither
`platform_discover.py` nor `platform_live_smoke.py` opens `--base-url`; direct
URL use without opt-in returns `ctfd_live_mode_requires_opt_in`.

Use the P1-12 runbook helper to generate the operator checklist without making
network requests:

```bash
python3 scripts/ctfd_live_smoke_runbook.py \
  --platform ctfd \
  --event local-fixture \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid
```

The helper prints dry-run first by default. It includes live discovery commands
only with `--include-live-command`, and includes queue registration only with
`--include-queue-command`.

The live adapter fetches only:

- `GET /api/v1/challenges`
- `GET /api/v1/challenges/{id}`
- attachment URLs from the detail `files`/`attachments` list only when
  live download is explicitly allowed

Discovery output is normalized to public-safe fields such as `challenge_id`,
`external_id`, `name`, `category`, `value`, `tags`, `solves`,
`local_capable`, `remote_required`, and `url`. Full descriptions are never
added to public metrics or queue events. Detail output may include bounded
description and connection text for local/private use.

```bash
python3 scripts/platform_live_smoke.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --base-url https://ctfd.example.invalid \
  --mode discovery \
  --json

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

```bash
python3 scripts/platform_discover.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid \
  --live \
  --queue \
  --json
```

Do not add `--queue` to direct discovery unless queue registration is explicitly
intended.

Smoke mode never submits flags. Downloads require `--allow-download`; server
acquire requires `--allow-server-acquire` and the normal resource lease policy.
CTFd live download is still opt-in and narrow:

```bash
python3 scripts/platform_download.py \
  --platform ctfd \
  --event local-fixture \
  --adapter ctfd \
  --policy ~/.ctf-solver/platforms/ctfd.yaml \
  --profile main \
  --base-url https://ctfd.example.invalid \
  --external-id 1 \
  --live \
  --allow-download \
  --json
```

Without `--live`, URL-backed CTFd downloads return
`ctfd_live_mode_requires_opt_in` and do not open the network. Without
`--allow-download`, they return `allow_download_flag_required`. Supported file
references are absolute HTTP(S) URLs, root-relative paths, and CTFd file paths
resolved against `base_url`. `file://`, path traversal, and localhost/private
network attachment hosts are rejected unless they are the same local mock origin
as `base_url` in tests. Download metadata contains `platform`, `event`,
`challenge_id`, `adapter`, `file_count`, and per-file `name`, `size`, `sha256`,
and relative path only; raw URL queries are not stored.

The generic CTFd adapter still does not implement server acquire or flag submit.

Store authentication outside the repo. Use `browser_state_init.py` for local
profile metadata. The current live discovery path does not parse browser
storage state contents; when a site requires auth, provide a local-only cookie
header through `CTF_CTFD_COOKIE_HEADER` or a repo-external
`CTF_CTFD_COOKIE_FILE`. Cookie values are never printed or stored in result
JSON. If auth is required and no usable local-only auth source/profile is
configured, the adapter returns `auth_required_or_profile_missing`.

Expected failure handling for live discovery:

- `auth_required_or_profile_missing`: provide local-only auth/profile metadata.
- `ctfd_api_error`: check CTFd API compatibility without storing raw responses.
- `base_url_missing`: provide `--base-url` or policy `base_url`.
- `network_timeout`: check platform/network availability and keep retries
  bounded.

## Submission Policy

`platform_submit.py` blocks by default when `automation.allow_submission` is
`ask`, absent, or false. `allow_submission: true` and `--role primary` are both
required before the adapter submit hook runs. Helper workers cannot submit.
Normal output and JSON results redact the flag.

## Server Provisioning

CTFd has no universal server create/release API. The adapter reports
`ctfd_server_provisioning_unsupported` unless a future custom hook is explicitly
configured. Do not automate arbitrary site-specific server buttons in this
generic adapter.

## Queue And Metrics

Use `platform_discover.py --queue` before workers start solving. Downloads move
matching queue items only when `platform_download.py --queue` is explicit; the
state can be `downloaded` or `local_triage`.

Public metrics may include `platform_adapter=ctfd`, `ctfd_challenge_count`,
`ctfd_download_count`, `ctfd_submit_attempted`,
`ctfd_live_discovery_attempted`, `ctfd_live_discovery_success`, and
`ctfd_live_discovered_count`, plus live download counters
`ctfd_live_download_attempted`, `ctfd_live_download_success`,
`ctfd_live_downloaded_count`, and `ctfd_live_downloaded_bytes`. Metrics must
not include descriptions, raw responses, flags, cookies, tokens, private URLs
with secrets, absolute download paths, writeups, exploits, transcripts, or
verifier evidence.
