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
  --json
```

Files are copied to:

```text
CTF_DOWNLOAD_ROOT/<platform>/<event>/<challenge_id>/
```

The metadata file records names, sizes, and SHA-256 hashes. Repo-internal
destinations are refused unless `--allow-repo-dest` is explicit.

## Live Mode

Regression tests must use local fixtures only. Live CTFd smoke work is manual
and opt-in. Supplying a live URL without opt-in returns
`ctfd_live_mode_requires_opt_in`; opting in currently returns
`ctfd_live_network_not_implemented` until the live fetch path is deliberately
implemented.

Store authentication outside the repo. Use `browser_state_init.py` for local
profile metadata, or provide any future cookie header through an environment
variable or local-only profile. Do not commit cookies, storage state, tokens,
account metadata, or private URLs.

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
matching queue items to `downloaded`; workers can then perform local triage.

Public metrics may include `platform_adapter=ctfd`, `ctfd_challenge_count`,
`ctfd_download_count`, and `ctfd_submit_attempted`. Metrics must not include
descriptions, raw responses, flags, cookies, tokens, private URLs, absolute
download paths, writeups, exploits, transcripts, or verifier evidence.
