# Challenge Lifecycle

Every challenge run is isolated by `challenge_id` and `run_id`. Do not rely on a single global "current challenge" state when multiple terminals are solving different problems.

## Flow

```text
init -> solve -> finalize -> writeup -> cleanup -> metrics -> git sync -> next
```

The next challenge should not start until finalization succeeds for the current run. Finalization is the mandatory handoff point that preserves useful artifacts, writes local notes, performs safe cleanup, and records public-safe metrics.

When a solve is claimed, run `scripts/verify_run.py` first when possible. The
verifier stores private solve evidence under `<run_dir>/verifier.json` and lets
finalization, writeups, and metrics consume a redacted summary.

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

Use `--require-verifier` when solved status must be backed by a successful
verifier. Without it, solved finalization warns if no successful verifier exists.

By default finalization releases active platform server records and remote
leases for the run, then marks a matching queue item as `finalized`. Use
`--keep-server` or `--keep-lease` only for intentional handoff.

By default finalization also closes active persistent sessions associated with
the run and records aggregate session counters in `finalization.json`. Use
`--keep-sessions` only for explicit handoff.

By default finalization closes browser action sessions associated with the run
and records aggregate browser counters. Use `--keep-browser-sessions` only for
explicit handoff.

By default finalization closes callback listeners associated with the run and
records aggregate callback counters. Use `--keep-callbacks` only for explicit
handoff.

By default finalization also collects redacted web workflow evidence and closes
web workflows associated with the run. Use `--keep-web-workflows` only for
explicit handoff.

If the run belongs to a benchmark, pass `--benchmark-id` and optionally
`--attempt-index`. Finalization records the normal public metrics and appends a
deduplicated public-safe benchmark result. If a manual AI usage record is known,
pass `--ai-usage-id` so the run and benchmark result can be correlated without
storing prompts or transcripts.

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
- Worker claim coordination uses JSON records under `CTF_WORKER_ROOT` or `~/.ctf-solver/workers`.
- Browser profile metadata uses `CTF_BROWSER_STATE_ROOT` or `~/.ctf-solver/browser-states`.
- Browser action session metadata uses `CTF_BROWSER_ROOT` or `~/.ctf-solver/browser`.
- Browser screenshots/artifacts use `CTF_BROWSER_ARTIFACT_ROOT` or `~/.ctf-solver/browser-artifacts`.
- Callback listener metadata and redacted hit logs use `CTF_CALLBACK_ROOT` or `~/.ctf-solver/callbacks`.
- Callback daemon state uses `CTF_CALLBACKD_ROOT` or `~/.ctf-solver/callbackd`.
- Web workflow metadata and redacted evidence use `CTF_WEB_WORKFLOW_ROOT` or `~/.ctf-solver/web-workflows`.
- Live platform smoke results use `CTF_LIVE_SMOKE_ROOT` or `~/.ctf-solver/live-smoke`.
- Platform automation records use `CTF_PLATFORM_AUTOMATION_ROOT` or `~/.ctf-solver/platforms`.
- Downloaded private challenge files use `CTF_DOWNLOAD_ROOT` or `~/CTF/downloads`.
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

## Queue Worker Runner

P1-3 adds a worker layer above queue, leases, verifier, and finalization:

```bash
python3 scripts/worker_next.py --platform thcon --event THCON --require-verifier true
python3 scripts/worker_run_once.py --platform thcon --event THCON --auto-acquire-remote --auto-finalize --require-verifier --json
python3 scripts/worker_loop.py --platform thcon --event THCON --interval-sec 10 --max-iterations 3
python3 scripts/worker_status.py --platform thcon --event THCON --show-claims --json
```

Each worker has a `worker_id` and must claim a queue item before local work,
remote acquire, verify, or finalize orchestration. Active non-stale claims block
other workers from taking the same challenge. Stale claims can be reclaimed
after `stale_after_sec`. Finalized queue items are never selected.

Solved queue items are selected for `verify_solution` first when
`--require-verifier` is enabled and no successful verifier exists. Only after
verification passes does the worker select `finalize_challenge`. The worker
does not invoke Codex, Claude, browser automation, Docker, Sage, or exploit
commands by itself.

GDB debug sessions associated with a `run_id` are closed by
`challenge_finalize.py` by default. Pass `--keep-gdb-sessions` only when a
debug session is being handed off intentionally.

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
| Worker root | `Path.home() / ".ctf-solver" / "workers"` | `CTF_WORKER_ROOT` |
| Session root | `Path.home() / ".ctf-solver" / "sessions"` | `CTF_SESSION_ROOT` |
| Session daemon root | `Path.home() / ".ctf-solver" / "sessiond"` | `CTF_SESSIOND_ROOT` |
| Browser action root | `Path.home() / ".ctf-solver" / "browser"` | `CTF_BROWSER_ROOT` |
| Browser artifact root | `Path.home() / ".ctf-solver" / "browser-artifacts"` | `CTF_BROWSER_ARTIFACT_ROOT` |
| Browser state root | `Path.home() / ".ctf-solver" / "browser-states"` | `CTF_BROWSER_STATE_ROOT` |
| Callback root | `Path.home() / ".ctf-solver" / "callbacks"` | `CTF_CALLBACK_ROOT` |
| Callback daemon root | `Path.home() / ".ctf-solver" / "callbackd"` | `CTF_CALLBACKD_ROOT` |
| Web workflow root | `Path.home() / ".ctf-solver" / "web-workflows"` | `CTF_WEB_WORKFLOW_ROOT` |
| Live smoke root | `Path.home() / ".ctf-solver" / "live-smoke"` | `CTF_LIVE_SMOKE_ROOT` |
| Platform automation root | `Path.home() / ".ctf-solver" / "platforms"` | `CTF_PLATFORM_AUTOMATION_ROOT` |
| Download root | `Path.home() / "CTF" / "downloads"` | `CTF_DOWNLOAD_ROOT` |
| Local writeup root | `Path.home() / "SolvedWriteUp"` | `CTF_SOLVED_WRITEUP_ROOT` |
| Public metrics root | `repo_root / "metrics"` | `CTF_SOLVER_REPO_ROOT` for repo root |
| Private metrics root | `Path.home() / ".ctf-solver" / "metrics-private"` | `CTF_PRIVATE_METRICS_ROOT` |
| AI usage root | `Path.home() / ".ctf-solver" / "ai-usage"` | `CTF_AI_USAGE_ROOT` |
| Private benchmark root | `Path.home() / ".ctf-solver" / "benchmarks"` | `CTF_BENCHMARK_ROOT` |

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

If `<run_dir>/verifier.json` exists, generated writeups include a Verification
section with verifier ID, target, mode, attempts, duration, and a redacted
bounded output preview.

If web workflow evidence is available, generated writeups include a redacted
workflow summary with workflow counts, payload counts, callback hit counts, and
evidence bundle counts.

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
metrics/benchmark_summary.jsonl
metrics/ai_usage_summary.jsonl
metrics/performance_summary.json
```

Public metrics may include timestamp, platform, event, category, status, duration, tool counts, cleanup bytes, writeup boolean, and exploit-included boolean. Public metrics must not include flags, exploit code, raw transcripts, cookies, tokens, account metadata, or private absolute paths.

Verifier metrics are summary-only: `verifier_success`,
`verifier_flag_found`, `verifier_target`, `verifier_attempts`, and
`verifier_duration_sec`. Verifier raw evidence and private evidence paths are not
public metrics.

Session metrics are public-safe aggregate counters only: session count, closed
session count, and byte counters. Session commands, transcripts, logs, flags,
and private paths are not public metrics.

Browser metrics are public-safe aggregate counters only: browser session count,
closed browser session count, action count, screenshot count, and network event
count. URLs, cookies, storage state paths, screenshot paths, console text, and
network bodies are not public metrics.

Callback metrics are public-safe aggregate counters only: listener count, closed
listener count, hit count, wait success, and wait duration. Callback URLs,
headers, bodies, cookies, tokens, flags, hit logs, and private paths are not
public metrics.

Worker metrics are optional public-safe aggregate fields only: worker count,
worker action/wait counts, claim reclaim count, `auto_finalize_used`, and
`require_verifier_used`. Raw worker IDs and hostnames should be omitted or
hashed.

Each public metrics entry includes a `run_id` so `scripts/update_metrics.py` can prevent duplicate appends. Re-running metrics update for the same `run_id` is skipped by default; use `--replace` or `--force` to replace the existing entry.

Benchmark results are deduplicated by `(benchmark_id, run_id, attempt_index)`.
AI usage is stored as private detailed JSONL plus public aggregate token/cost
rows by provider, model, date, category, platform, and event. Neither path
stores prompts, transcripts, account metadata, flags, exploit code, private
paths, or raw provider output in repo metrics.

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

Run the regression suite after lifecycle, resource, or persistent session changes:

```bash
python3 -m pytest tests
python3 scripts/secret_scan.py --strict
```

Tests set `CTF_WORK_ROOT`, `CTF_LOCAL_RUN_ROOT`, `CTF_LOCK_ROOT`,
`CTF_SOLVED_WRITEUP_ROOT`, `CTF_LEASE_ROOT`, `CTF_QUEUE_ROOT`,
`CTF_WORKER_ROOT`,
`CTF_SOLVER_REPO_ROOT`, and `CTF_PLATFORM_CONFIG` to temp directories. They do
not touch real HOME state such as `~/.ctf-solver`, `~/SolvedWriteUp`,
`~/.agents`, `~/.claude`, or `~/.codex`.

Never paste or commit `~/.claude.json`, `~/.codex/config.toml`, browser storage
state, cookies, tokens, OAuth values, account metadata, writeups, exploits, raw
transcripts, or flags.

Browser/platform automation details are documented in
`docs/browser-platform-automation.md`. Browser action commands are documented in
`docs/browser-actions.md`.

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

Persistent session details and examples are documented in `docs/sessions.md`.
Verifier details and examples are documented in `docs/verifier.md`.
