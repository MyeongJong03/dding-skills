# Challenge Lifecycle

Every challenge run is isolated by `challenge_id` and `run_id`. Do not rely on a single global "current challenge" state when multiple terminals are solving different problems.

## Flow

```text
init -> solve -> finalize -> writeup -> cleanup -> metrics -> git sync -> next
```

The next challenge should not start until finalization succeeds for the current run. Finalization is the mandatory handoff point that preserves useful artifacts, writes local notes, performs safe cleanup, and records public-safe metrics.

## Parallel Safety

- `challenge_id` is derived from platform, event, category, and challenge name.
- `run_id` is timestamp plus a short UUID, so simultaneous terminals create separate run directories.
- Challenge finalization uses a per-`challenge_id`/`run_id` directory lock.
- Metrics updates use a global metrics lock and atomic file replacement.
- Git sync uses a global git lock so concurrent commits and pushes serialize.
- Locks are atomic directories created with `Path.mkdir(exist_ok=False)` and include `owner.json` with pid, timestamp, purpose, and a stale timeout.

## Paths

Defaults are portable and may be overridden with environment variables:

| Purpose | Default | Override |
| --- | --- | --- |
| Work root | `Path.home() / "CTF" / "work"` | `CTF_WORK_ROOT` |
| Private run root | `Path.home() / ".ctf-solver" / "runs"` | `CTF_LOCAL_RUN_ROOT` |
| Lock root | `Path.home() / ".ctf-solver" / "locks"` | `CTF_LOCK_ROOT` |
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

## Commands

```bash
python3 scripts/challenge_init.py --platform dreamhack --event dreamhackWargame --challenge-name "Example" --category web
python3 scripts/challenge_finalize.py --run-dir <run-dir> --status solved --generate-writeup --cleanup --update-metrics --git-sync --no-push
CTF_AUTO_PUSH=1 python3 scripts/git_sync_metrics.py --push
```

`git_sync_metrics.py` only stages public-safe repo paths. It does not stage `~/SolvedWriteUp`, private run logs, flags, copied writeup exploits, or raw transcripts.

