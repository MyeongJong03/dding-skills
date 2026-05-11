# Challenge Lifecycle

Every challenge run is isolated by `challenge_id` and `run_id`. Do not rely on a single global "current challenge" state when multiple terminals are solving different problems.

## Flow

```text
init -> solve -> finalize -> writeup -> cleanup -> metrics -> git sync -> next
```

The next challenge should not start until finalization succeeds for the current run. Finalization is the mandatory handoff point that preserves useful artifacts, writes local notes, performs safe cleanup, and records public-safe metrics.

## Mandatory Finalization Before Next Challenge

Every challenge end state must pass through `scripts/challenge_finalize.py` before another challenge starts in that terminal. This applies to successful and non-successful outcomes:

- `solved`
- `abandoned`
- `skipped`
- `already_solved`
- `timeout`
- `budget_exhausted`
- `manual_stop`

Use the `run_dir` returned by `scripts/challenge_init.py`. If a user provides an existing workspace or `run_dir`, continue with that path instead of creating an unrelated run.

```bash
python3 scripts/challenge_init.py --platform dreamhack --event dreamhackWargame --challenge-name "Example" --category web
python3 scripts/challenge_finalize.py --run-dir <run-dir> --status solved --generate-writeup --cleanup --update-metrics --git-sync --no-push
```

Finalization should generate a local writeup whenever there is enough information to produce one. If exploit files exist, pass them with `--exploit <path>` or keep them under `<run_dir>/exploit/` so the writeup includes the full exploit code.

By default finalization releases active remote leases for the run and marks a
matching queue item as `finalized`. Use `--keep-lease` only for intentional
handoff.

## Multi-Terminal Run ID Discipline

There is no supported global "current challenge". Each terminal/session must keep its own `challenge_id`, `run_id`, and `run_dir`.

- Do not infer the active run from the latest directory timestamp.
- Do not mix exploit files, notes, logs, or cleanup records across different `run_id` values.
- Keep terminal-local shell variables or notes for the current `run_dir`.
- When resuming, read `<run_dir>/challenge.json` and continue that exact run.

## Parallel Safety

- `challenge_id` is derived from platform, event, category, and challenge name.
- `run_id` is timestamp plus a short UUID, so simultaneous terminals create separate run directories.
- Challenge finalization uses a per-`challenge_id`/`run_id` directory lock.
- Remote server/VM coordination uses file-backed leases under `CTF_LEASE_ROOT` or `~/.ctf-solver/leases`.
- Challenge queue coordination uses JSON records under `CTF_QUEUE_ROOT` or `~/.ctf-solver/queue`.
- Metrics updates use a global metrics lock and atomic file replacement.
- Git sync uses a global git lock so concurrent commits and pushes serialize.
- Locks are atomic directories created with `Path.mkdir(exist_ok=False)` and include `owner.json` with pid, timestamp, purpose, and a stale timeout.

## Resource-Aware Queue

Platform policies describe remote server/VM limits, including THCON-like
`max_active_leases: 1` event-scoped constraints. If a worker cannot acquire a
remote lease, it should continue local-capable work instead of idling. Queue
items marked `local_exploit_ready` receive remote priority when capacity is
released.

If sharing is allowed and safe, helper workers may join an active remote
challenge. Helper workers are non-destructive only. Primary workers own submit,
restart, release, and other destructive actions. See
`docs/platform-automation.md` for commands and examples.

## Idempotent Finalization

`scripts/challenge_finalize.py` records finalization state in the run directory. Re-running finalization for the same `run_id` and same status is a no-op by default and must not append duplicate metrics.

If a run is already finalized with a different status, finalization refuses to proceed unless `--force` is supplied. Forced finalization replaces the public metrics entry for the same `run_id` instead of appending another record.

## Paths

Defaults are portable and may be overridden with environment variables:

| Purpose | Default | Override |
| --- | --- | --- |
| Work root | `Path.home() / "CTF" / "work"` | `CTF_WORK_ROOT` |
| Private run root | `Path.home() / ".ctf-solver" / "runs"` | `CTF_LOCAL_RUN_ROOT` |
| Lock root | `Path.home() / ".ctf-solver" / "locks"` | `CTF_LOCK_ROOT` |
| Lease root | `Path.home() / ".ctf-solver" / "leases"` | `CTF_LEASE_ROOT` |
| Queue root | `Path.home() / ".ctf-solver" / "queue"` | `CTF_QUEUE_ROOT` |
| Local writeup root | `Path.home() / "SolvedWriteUp"` | `CTF_SOLVED_WRITEUP_ROOT` |
| Public metrics root | `repo_root / "metrics"` | `CTF_SOLVER_REPO_ROOT` for repo root |

All lifecycle scripts use `pathlib.Path`; do not add OS-specific hardcoded paths.

## Writeup Policy

Writeups are local-only. They are stored under `~/SolvedWriteUp` or `CTF_SOLVED_WRITEUP_ROOT`, not inside the GitHub repo.

Dreamhack wargame writeups use:

```text
~/SolvedWriteUp/dreamhackWargame/<challenge-name>/writeup.md
```

General CTF writeups use:

```text
~/SolvedWriteUp/<event-or-ctf-name>/<challenge-name>/writeup.md
```

Writeups may include the full final exploit code and local-only flag. They must not be automatically pushed to GitHub.

## Local-Only Writeup Policy

Writeups, copied exploit files, flags, raw transcripts, private notes, and private run logs stay outside the repository. `~/SolvedWriteUp` and `CTF_SOLVED_WRITEUP_ROOT` are never valid git sync targets.

## Metrics Policy

Private detailed run data lives under:

```text
~/.ctf-solver/runs/<challenge_id>/<run_id>/
```

Public-safe aggregate metrics live in:

```text
metrics/summary.jsonl
metrics/dashboard.md
```

Public metrics may include timestamp, platform, event, category, status, duration, tool counts, cleanup bytes, writeup boolean, and exploit-included boolean. Public metrics must not include flags, exploit code, raw transcripts, cookies, tokens, account metadata, or private absolute paths.

Each public metrics entry includes a `run_id` so `scripts/update_metrics.py` can prevent duplicate appends. Re-running metrics update for the same `run_id` is skipped by default; use `--replace` or `--force` to replace the existing entry.

## Public-Safe Metrics Policy

Public metrics are GitHub-friendly aggregate records. They may live in repo `metrics/`, but they must not include:

- flags
- exploit code
- raw transcripts
- cookies, tokens, API keys, OAuth data, passwords, or private keys
- email addresses, account UUIDs, or organization UUIDs
- private absolute paths or local artifact paths

Run `python3 scripts/update_metrics.py --check` before git sync or release handoff.

## Regression Tests And Secret Scan

Run the regression suite before P1 persistent session MCP changes:

```bash
python3 -m pytest tests
python3 scripts/secret_scan.py --strict
```

Tests set `CTF_WORK_ROOT`, `CTF_LOCAL_RUN_ROOT`, `CTF_LOCK_ROOT`,
`CTF_SOLVED_WRITEUP_ROOT`, `CTF_LEASE_ROOT`, `CTF_QUEUE_ROOT`,
`CTF_SOLVER_REPO_ROOT`, and `CTF_PLATFORM_CONFIG` to temp directories. They do
not touch real HOME state such as `~/.ctf-solver`, `~/SolvedWriteUp`,
`~/.agents`, `~/.claude`, or `~/.codex`.

Never paste or commit `~/.claude.json`, `~/.codex/config.toml`, browser storage
state, cookies, tokens, OAuth values, account metadata, writeups, exploits, raw
transcripts, or flags.

## Git Sync Boundary

`scripts/git_sync_metrics.py` may stage only public-safe ctf-solver repository paths: `metrics/`, `skills/`, `memory/`, `docs/`, `config/`, `scripts/`, `tools/`, `ctf_solver_core/`, and top-level repo docs/config files.

It must never stage `~/SolvedWriteUp`, `~/.ctf-solver/runs`, private run logs, copied writeup exploits, raw transcripts, or accidental in-repo private directories such as `SolvedWriteUp/` or `.ctf-solver/`.

Git sync does not push by default. It pushes only with `--push` or when `CTF_AUTO_PUSH=1` is set and `--no-push` is not supplied.

## Commands

```bash
python3 scripts/challenge_init.py --platform dreamhack --event dreamhackWargame --challenge-name "Example" --category web
python3 scripts/challenge_finalize.py --run-dir <run-dir> --status solved --generate-writeup --cleanup --update-metrics --git-sync --no-push
CTF_AUTO_PUSH=1 python3 scripts/git_sync_metrics.py --push
```

`git_sync_metrics.py` only stages public-safe repo paths. It does not stage `~/SolvedWriteUp`, private run logs, flags, copied writeup exploits, or raw transcripts.
