# Operator Mode Runbook

This is the one-page operating procedure for real CTF solving with multiple
terminals. It ties together lifecycle, queue, leases, verifier, cleanup,
writeup, metrics, and platform adapters. It is not a new exploit feature.

## Quick Status

Use the shortcut first when it is installed. Paste the full marker block when
handing state to another terminal or agent.

```bash
ctf-status
```

Fallback:

```bash
python3 scripts/status_summary.py
```

The status command is paste-safe. It summarizes git, Docker, MCP server names,
redaction checks, repo raw grep, and doctor output without printing raw
`~/.claude.json`, cookies, tokens, flags, browser storage, platform responses,
writeups, exploits, or private run logs.

## Fast Regression

Run this after routine repo edits or before asking another terminal to continue.

```bash
ctf-check
```

Fallback:

```bash
python3 scripts/regression_check.py --quick
```

## Full Regression

Run this before larger handoffs, release-like changes, or commits.

```bash
ctf-regression
```

Fallback:

```bash
python3 scripts/regression_check.py
```

Regression is local by default. It does not run live CTF platform actions unless
a separate live smoke command is explicitly approved and run with `--live`.

## Start A Challenge

Every challenge needs a concrete `challenge_id`, `run_id`, and `run_dir`.
Never rely on a global current challenge. If the user provides an existing
workspace or `run_dir`, continue that run instead of creating a new one.

```bash
python3 scripts/challenge_init.py --platform <platform> --event <event> --challenge-name "<name>" --category <category>
```

If the challenge came from a queue or platform discovery, update the queue item
and let a worker claim it before solving from another terminal.

```bash
python3 scripts/queue_update.py --platform <platform> --event <event> --challenge-id <challenge-id> --category <category> --state downloaded --local-capable true --remote-required false --local-exploit-ready false --confidence 0.2 --destructive-risk 0.0
python3 scripts/worker_next.py --platform <platform> --event <event> --worker-id <worker-id> --require-verifier true
python3 scripts/worker_run_once.py --platform <platform> --event <event> --worker-id <worker-id> --auto-acquire-remote --auto-finalize --require-verifier --json
```

`worker_next.py` chooses the next public-safe action. It does not run Codex,
Claude, browser automation, GDB, or exploit code by itself.

## During Solving

Keep all interactive or long-running work associated with the current `run_id`.
Do not mix sessions, browser sessions, callback listeners, GDB sessions, notes,
or generated files across different runs.

Persistent shells and menu services:

```bash
python3 scripts/session_start.py shell --run-id <run-id> --cwd <workspace>
python3 scripts/session_write.py <session-id> "<input>"
python3 scripts/session_expect.py <session-id> "<pattern>" --timeout-ms 3000 --max-bytes 4096
python3 scripts/session_close.py <session-id>
```

Browser actions for DOM, JavaScript, redirects, uploads, and parser behavior:

```bash
uv run --with playwright python scripts/browser_start.py --run-id <run-id>
uv run --with playwright python scripts/browser_goto.py --browser-session-id <browser-session-id> --url <url>
uv run --with playwright python scripts/browser_eval.py --browser-session-id <browser-session-id> --expression "<expression>"
uv run --with playwright python scripts/browser_close.py --browser-session-id <browser-session-id>
```

Callback listeners for XSS, admin bot, SSRF, CSP leak, CSS exfil, and blind hit
confirmation:

```bash
python3 scripts/callback_start.py --run-id <run-id> --json
python3 scripts/callback_url.py --listener-id <listener-id>
python3 scripts/callback_wait.py --listener-id <listener-id> --timeout-sec 30 --json
python3 scripts/callback_hits.py --listener-id <listener-id> --json
python3 scripts/callback_close.py --listener-id <listener-id> --json
```

GDB sessions for local pwn crash analysis only:

```bash
python3 scripts/gdb_start.py --run-id <run-id> --challenge-id <challenge-id> --binary <local-binary> --mode docker --json
python3 scripts/gdb_cmd.py --gdb-session-id <gdb-session-id> --command "info registers"
python3 scripts/gdb_backtrace.py --gdb-session-id <gdb-session-id>
python3 scripts/gdb_close.py --gdb-session-id <gdb-session-id>
```

Verifier before solved finalization:

```bash
python3 scripts/verify_run.py --run-dir <run-dir> --mode command --command "<solve-command>" --cwd <workspace> --flag-regex '<flag-regex>' --local
```

Verifier output and raw evidence stay under the private `run_dir`.

## Platform Flows

CTFd live discovery and download are opt-in. Start with no-network command
generation or dry-run, then use `--live` only after explicit approval. Use
`--queue` only when queue registration is intended.

```bash
python3 scripts/ctfd_live_smoke_runbook.py --platform ctfd --event <event> --base-url <base-url>
python3 scripts/platform_live_smoke.py --platform ctfd --event <event> --adapter ctfd --mode discovery --base-url <base-url> --json
python3 scripts/platform_discover.py --platform ctfd --event <event> --adapter ctfd --base-url <base-url> --live --queue --json
python3 scripts/platform_live_smoke.py --platform ctfd --event <event> --adapter ctfd --mode download --base-url <base-url> --challenge-id <external-id> --allow-download --json
python3 scripts/platform_download.py --platform ctfd --event <event> --adapter ctfd --base-url <base-url> --external-id <external-id> --live --allow-download --queue --json
```

Dreamhack VM control is also opt-in. It uses the Dreamhack platform adapter
inside `ctf_solver`, not a Dreamhack-specific canonical MCP server. Start,
restart, stop, and status actions require explicit `--live`; start/restart with
ask policy also require `--confirm`.

```bash
python3 scripts/dreamhack_vm_control.py --challenge-id <dreamhack-id> --run-id <run-id> --action status --live --session-id-file <repo-external-session-file> --csrf-token-file <repo-external-csrf-file> --json
python3 scripts/dreamhack_vm_control.py --challenge-id <dreamhack-id> --run-id <run-id> --action start --confirm --live --session-id-file <repo-external-session-file> --csrf-token-file <repo-external-csrf-file> --json
```

Do not print, paste, commit, or metric raw cookies, session values, CSRF values,
storage state, account metadata, raw platform responses, private VM URLs, or
private attachment URLs with query strings.

## Finish A Challenge

When a challenge reaches any terminal state, finalize it before doing another
challenge. Terminal states include `solved`, `abandoned`, `skipped`,
`already_solved`, `timeout`, `budget_exhausted`, and `manual_stop`.

Solved path:

```bash
python3 scripts/verify_run.py --run-dir <run-dir> --mode command --command "<solve-command>" --cwd <workspace> --flag-regex '<flag-regex>' --local
python3 scripts/challenge_finalize.py --run-dir <run-dir> --status solved --require-verifier --generate-writeup --cleanup --update-metrics
```

Manual stop or unsolved terminal path:

```bash
python3 scripts/challenge_finalize.py --run-dir <run-dir> --status manual_stop --generate-writeup --cleanup --update-metrics
```

Finalize closes run-scoped sessions, browser sessions, callback listeners, GDB
sessions, web workflows, and platform resources unless an explicit keep flag is
used. Use keep flags only for a deliberate handoff.

## Move To Next Challenge

The next challenge can start only after finalization succeeds for the current
run. This rule applies even when the current run is skipped, abandoned, timed
out, already solved, or manually stopped.

Checklist before moving on:

- `challenge_finalize.py` returned success for the current `run_dir`.
- Required verifier evidence exists when status is `solved`.
- Writeup generation ran when enough information exists.
- Cleanup ran or an explicit keep flag was recorded for handoff.
- Metrics were updated only with public-safe aggregate fields.
- Queue item state and worker claim reflect the terminal result.
- Resource leases were released or intentionally kept.

## Multi-Terminal Safety

Multiple terminals must coordinate through queue claims and resource leases.

```bash
python3 scripts/worker_status.py --platform <platform> --event <event> --show-claims --json
python3 scripts/worker_next.py --platform <platform> --event <event> --worker-id <worker-id> --require-verifier true
python3 scripts/resource_acquire.py --platform <platform> --event <event> --challenge-id <challenge-id> --run-id <run-id> --resource remote_server --mode primary --policy <policy.yaml>
python3 scripts/resource_heartbeat.py --lease-id <lease-id> --once
python3 scripts/resource_reclaim_stale.py --dry-run
python3 scripts/queue_history.py --platform <platform> --event <event> --tail 20
python3 scripts/resource_release.py --run-id <run-id> --platform <platform> --event <event> --all-for-run
```

Rules:

- A terminal must claim a queue item before working on it.
- Do not work on an actively claimed challenge unless helper mode is selected.
- Primary workers own destructive actions, server restart/release, and submit
  authority.
- Helper workers are read-only and non-destructive.
- If remote capacity is unavailable, continue local-capable triage and exploit
  planning instead of idling.
- Long-running remote work needs lease heartbeat.
- Reclaim stale leases only after dry-run confirms the lease is not
  heartbeating.

## Storage

- `~/SolvedWriteUp` or `CTF_SOLVED_WRITEUP_ROOT`: local-only writeups and copied
  exploit files.
- `~/.ctf-solver`: private runs, sessions, browser artifacts, callback hits,
  GDB metadata/artifacts, platform state, live smoke output, benchmark raw
  details, and private metrics.
- `metrics/`: public-safe aggregate metrics only.
- `docs/`, `config/`, `scripts/`, `tools/`, `ctf_solver_core/`, and public repo
  metadata may be committed when they contain no private evidence.

Writeups, exploit code, flags, raw transcripts, private URLs, private paths,
cookies, tokens, browser storage, platform raw responses, and private run logs
must not be committed or pushed as public metrics.

## Troubleshooting

- `ctf-pwn:latest` missing: optional unless a pwn/GDB task needs Docker. Build
  it with `docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest .`.
- ReVa off: optional unless PWN/REV needs Ghidra MCP. Start Ghidra, then retry
  ReVa-dependent analysis.
- Playwright missing: use uv first,
  `uv run --with playwright python scripts/browser_playwright_check.py --json`.
  Avoid `--break-system-packages` as the default macOS path.
- Docker GDB on macOS: runs through linux/amd64 emulation and can be slow. Check
  runtime support with `python3 scripts/gdb_docker_smoke.py --json` before
  depending on Docker GDB.
- Shortcut missing or repo moved: reinstall wrappers with
  `python3 scripts/install_shortcuts.py --dry-run` and then
  `python3 scripts/install_shortcuts.py`.

## Final Local Checks

Before committing runbook or operator-mode changes:

```bash
ctf-status
ctf-check
python3 -m pytest tests
python3 scripts/secret_scan.py --strict --include-untracked
python3 scripts/doctor.py
python3 scripts/dump_mcp_tools.py --check
python3 scripts/redact_sensitive.py --self-test
python3 scripts/update_metrics.py --check
python3 -m compileall tools server.py scripts ctf_solver_core
git diff --check
```
