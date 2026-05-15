# Operator Mode Runbook

This is the runbook to keep open during real CTF solving. It is procedural:
status, start, solve, verify, finalize, then move on. Background explanations
belong in [GUIDE.md](../GUIDE.md); status marker details belong in
[docs/regression.md](regression.md).

## 0. Status First

Start from `~/CTF` or the repo:

```bash
ctf-status
```

Fallback:

```bash
cd ~/ctf-solver
python3 scripts/status_summary.py
```

Share the marker block for handoff. It does not print raw `~/.claude.json`,
cookies, tokens, flags, browser storage, platform raw responses, writeups,
exploits, or private run logs.

After routine edits:

```bash
ctf-check
```

Fallback:

```bash
cd ~/ctf-solver
python3 scripts/regression_check.py --quick
```

Before larger handoffs or commits:

```bash
ctf-regression
```

Fallback:

```bash
cd ~/ctf-solver
python3 scripts/regression_check.py
```

Regression is local by default. Live platform smoke is separate and requires an
explicit `--live` flow.

## 1. Start Challenge

Every challenge needs a concrete `challenge_id`, `run_id`, and `run_dir`. Do
not rely on a global current challenge. If a workspace or `run_dir` already
exists, continue that run instead of creating an unrelated one.

```bash
cd ~/ctf-solver
python3 scripts/challenge_init.py \
  --platform <platform> \
  --event <event> \
  --challenge-name "<name>" \
  --category <category>
```

Record:

- `challenge_id`
- `run_id`
- `run_dir`
- workspace path
- remote endpoint, if any

For queued work, register/update the item and claim it before solving from
another terminal:

```bash
python3 scripts/queue_update.py \
  --platform <platform> \
  --event <event> \
  --challenge-id <challenge-id> \
  --category <category> \
  --state downloaded \
  --local-capable true \
  --remote-required false \
  --local-exploit-ready false \
  --confidence 0.2 \
  --destructive-risk 0.0
```

```bash
python3 scripts/worker_next.py \
  --platform <platform> \
  --event <event> \
  --worker-id <worker-id> \
  --require-verifier true
```

`worker_next.py` chooses the next public-safe action. It does not run Codex,
Claude, browser automation, GDB, or exploit code by itself.

For one public-safe orchestration step:

```bash
python3 scripts/worker_run_once.py \
  --platform <platform> \
  --event <event> \
  --worker-id <worker-id> \
  --auto-acquire-remote \
  --auto-finalize \
  --require-verifier \
  --json
```

## 2. During Solving

Keep every helper tied to the current `run_id`.

- Persistent sessions: menus, REPLs, shells, Docker shell state.
- Browser sessions: DOM, JavaScript, redirects, uploads, parser behavior.
- Callback listeners: XSS, admin bot, SSRF, CSP leak, CSS exfil, blind hits.
- GDB sessions: local pwn crash analysis only.
- Web workflows: browser/callback/evidence bundles for one web exploit path.

Useful entry commands:

```bash
python3 scripts/session_start.py shell --run-id <run-id> --cwd <workspace>
uv run --with playwright python scripts/browser_start.py --run-id <run-id>
python3 scripts/callback_start.py --run-id <run-id> --json
python3 scripts/gdb_start.py --run-id <run-id> --challenge-id <challenge-id> --binary <local-binary> --mode docker --json
```

Rules:

- Do not mix artifacts from different `run_id` values.
- Use bounded reads and expects for interactive sessions.
- Store raw evidence only under the private `run_dir` or the local-only helper
  roots.
- Do not attach GDB to live remote targets.
- Close run-scoped helpers during finalize unless a deliberate handoff needs a
  keep flag.

## 3. Platform And Resource Operations

Platform work is opt-in and policy-driven. Do not print, paste, commit, or
metric raw cookies, session values, CSRF values, storage state, account
metadata, raw platform responses, private VM URLs, or private attachment URLs
with query strings.

For single-remote platforms, acquire and heartbeat a lease:

```bash
python3 scripts/resource_acquire.py \
  --platform <platform> \
  --event <event> \
  --challenge-id <challenge-id> \
  --run-id <run-id> \
  --resource remote_server \
  --mode primary \
  --policy <policy.yaml>
```

```bash
python3 scripts/resource_heartbeat.py --lease-id <lease-id> --once
python3 scripts/resource_reclaim_stale.py --dry-run
```

### CTFd

CTFd live discovery/download is explicit. Generate the runbook or dry-run first,
then use `--live` only after approval. Use `--queue` only when queue
registration is intended.

```bash
python3 scripts/ctfd_live_smoke_runbook.py \
  --platform ctfd \
  --event <event> \
  --base-url <base-url>
```

```bash
python3 scripts/platform_discover.py \
  --platform ctfd \
  --event <event> \
  --adapter ctfd \
  --base-url <base-url> \
  --live \
  --queue \
  --json
```

Attachment download also requires `--allow-download`.

### Dreamhack

Dreamhack is a platform adapter inside `ctf_solver`, not a Dreamhack-specific
canonical MCP server. VM status/start/restart/stop are explicit live
operations.

```bash
python3 scripts/dreamhack_vm_control.py \
  --challenge-id <dreamhack-id> \
  --run-id <run-id> \
  --action status \
  --live \
  --session-id-file <repo-external-session-file> \
  --csrf-token-file <repo-external-csrf-file> \
  --json
```

Start/restart require `--confirm` when policy is `ask`.

## 4. Verify

Run verifier before claiming solved when possible. Raw verifier evidence stays
under the private `run_dir`.

```bash
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode command \
  --command "<solve-command>" \
  --cwd <workspace> \
  --flag-regex '<flag-regex>' \
  --local
```

Manual mode is acceptable when the evidence came from another terminal:

```bash
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode manual \
  --evidence-text "<redacted-evidence-summary>" \
  --success-regex "<success-marker>" \
  --remote
```

## 5. Finalize

Finalize every terminal state before another challenge: `solved`, `abandoned`,
`skipped`, `already_solved`, `timeout`, `budget_exhausted`, or `manual_stop`.

Solved path:

```bash
python3 scripts/challenge_finalize.py \
  --run-dir <run-dir> \
  --status solved \
  --require-verifier \
  --generate-writeup \
  --cleanup \
  --update-metrics
```

Doctor marker equivalent: `challenge_finalize.py --run-dir <run-dir> --status solved --require-verifier --generate-writeup --cleanup --update-metrics`.

Manual stop path:

```bash
python3 scripts/challenge_finalize.py \
  --run-dir <run-dir> \
  --status manual_stop \
  --generate-writeup \
  --cleanup \
  --update-metrics
```

Finalize closes run-scoped sessions, browser sessions, callback listeners, GDB
sessions, web workflows, and platform resources unless an explicit keep flag is
used.

Storage boundaries:

- `~/SolvedWriteUp` or `CTF_SOLVED_WRITEUP_ROOT`: local-only writeups and copied
  exploit files.
- `~/.ctf-solver`: private runs, helper metadata, artifacts, platform state,
  live smoke output, and private benchmark details.
- `metrics/`: public-safe aggregate metrics only.

Never commit writeups, exploit code, flags, raw transcripts, private URLs,
private paths, cookies, tokens, browser storage, platform raw responses, or
private run logs.

## 6. Move To Next Challenge

Only move on after finalize succeeds for the current `run_dir`.

Checklist:

- Finalize completed with the intended status.
- Verifier result exists if `--require-verifier` was used.
- Cleanup either completed or a keep flag was intentional.
- Writeup, exploit copies, and private evidence stayed local-only.
- Public metrics contain only safe aggregate fields.
- Queue state and worker claim reflect the terminal result.
- Resource leases were released or intentionally kept.

For multi-terminal state:

```bash
python3 scripts/worker_status.py --platform <platform> --event <event> --show-claims --json
python3 scripts/queue_history.py --platform <platform> --event <event> --tail 20
python3 scripts/resource_release.py --run-id <run-id> --platform <platform> --event <event> --all-for-run
```

## 7. Troubleshooting During A Run

- Shortcut missing or repo moved:
  `python3 scripts/install_shortcuts.py --dry-run && python3 scripts/install_shortcuts.py`
- `ctf-pwn:latest` missing: optional unless a pwn/GDB task needs Docker.
- ReVa off: expected unless Ghidra/ReVa is running; required only for
  ReVa-dependent PWN/REV analysis.
- Playwright missing: use
  `uv run --with playwright python scripts/browser_playwright_check.py --json`.
- Docker GDB on macOS: validate with
  `python3 scripts/gdb_docker_smoke.py --json` before depending on it.
- Status confusion: run `ctf-status` and share the marker block, not raw global
  config files.

## Final Local Checks

Before handoff or commit after repo changes:

```bash
ctf-status
ctf-check
python3 -m pytest tests
python3 scripts/secret_scan.py --strict --include-untracked
python3 scripts/doctor.py
python3 scripts/dump_mcp_tools.py --check
python3 scripts/redact_sensitive.py --self-test
python3 scripts/update_metrics.py --check
git diff --check
```
