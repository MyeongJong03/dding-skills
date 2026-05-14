# Offline E2E Smoke

`scripts/offline_e2e_smoke.py` validates the platform lifecycle without using
external network access or live CTF credentials. It runs a synthetic fixture
flow through discovery, queue registration, fixture download, `challenge_init`,
manual verifier evidence, `challenge_finalize`, local-only writeup generation,
public-safe metrics, and cleanup.

The smoke is intended for regression coverage after platform adapter changes.
It does not submit flags, start servers, read browser storage, inspect live
credentials, or store raw challenge transcripts.

## Usage

```bash
python3 scripts/offline_e2e_smoke.py --platform ctfd --json
python3 scripts/offline_e2e_smoke.py --platform dreamhack --json
```

Optional arguments:

- `--fixture-root <dir>`: use local fixtures instead of generated temp fixtures.
- `--category <category>`: override the synthetic category, default `web`.
- `--challenge-id <id>`: carry an explicit platform challenge ID through queue,
  init, verifier, finalize, and metrics.
- `--keep-temp`: keep temp directories for local debugging. The JSON summary
  still does not print private paths.

Fixture roots may use either `<root>/<platform>/discovery.json` and
`<root>/<platform>/detail.json`, or the same file names directly under
`<root>`. URL fixture roots are rejected.

## JSON Summary

The script prints public-safe booleans:

- `discovery_ok`
- `queue_ok`
- `download_ok`
- `init_ok`
- `verifier_ok`
- `finalize_ok`
- `writeup_ok`
- `metrics_ok`
- `cleanup_ok`
- `public_safe_ok`

The summary includes only public-safe counters and IDs. It intentionally omits
temp paths, writeup paths, file contents, raw verifier output, flags, exploit
code, cookies, sessions, CSRF values, and raw platform responses.

## Storage Policy

Every run creates an isolated temp environment:

- `HOME`
- `CTF_WORK_ROOT`
- `CTF_LOCAL_RUN_ROOT`
- `CTF_SOLVED_WRITEUP_ROOT`
- `CTF_QUEUE_ROOT`
- `CTF_LOCK_ROOT`
- `CTF_DOWNLOAD_ROOT`
- `CTF_PLATFORM_AUTOMATION_ROOT`
- `CTF_SOLVER_REPO_ROOT`

The writeup root is temp local-only storage outside the temp public repo.
Metrics are written only to the temp public repo `metrics/` directory and are
validated with `scripts/update_metrics.py --check`. Cleanup is checked by
creating scratch artifacts and verifying that finalize removes them.

## Regression Command

```bash
python3 -m pytest tests/test_offline_e2e_smoke.py
python3 scripts/offline_e2e_smoke.py --platform ctfd --json
python3 scripts/offline_e2e_smoke.py --platform dreamhack --json
```
