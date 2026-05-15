# dding-skills

Codex-first CTF solving environment for local challenge work. It helps track a
challenge from init to solve, verifier, cleanup, local writeup, and public-safe
metrics.

The normal entrypoint is `codex` from `~/CTF`. The repo itself lives at
`~/ctf-solver`.

## What This Is

This repo provides:

- MCP tools and CLI helpers for CTF analysis and operations.
- Challenge lifecycle commands: init, verify, finalize, cleanup, metrics.
- Operator shortcuts for status and regression checks.
- Local-only storage boundaries for writeups, private run logs, browser data,
  callback hits, GDB artifacts, and platform state.
- Public-safe metrics scaffolding that can be committed without flags or
  exploit evidence.

It is not a new exploit feature. It is the workflow glue around real CTF
solving.

## Daily Commands

```bash
ctf-status
```

Quick setup/status summary. Use this before starting work or when handing state
to another terminal. It prints paste-safe markers, not raw config files.

```bash
ctf-check
```

Fast local regression after routine edits. Fallback:
`python3 ~/ctf-solver/scripts/regression_check.py --quick`.

```bash
ctf-regression
```

Full local regression before larger handoffs or commits. It is still local by
default; live platform smoke is a separate explicit flow.

Marker details live in [docs/regression.md](docs/regression.md).

## Start Using It

For an already installed MacBook setup:

```bash
cd ~/CTF
ctf-status
codex
```

Then give Codex the challenge name, category, local files, remote endpoint, and
flag format if known.

For install/deploy details, see [GUIDE.md](GUIDE.md).

## Solve One Challenge Flow

Run lifecycle commands from the repo:

```bash
cd ~/ctf-solver
```

1. Init

   ```bash
   python3 scripts/challenge_init.py \
     --platform <platform> \
     --event <event> \
     --challenge-name "<name>" \
     --category <category>
   ```

2. Solve

   Keep the returned `challenge_id`, `run_id`, and `run_dir`. Associate
   sessions, browsers, callbacks, GDB sessions, notes, and helper artifacts with
   that run.

3. Verify

   ```bash
   python3 scripts/verify_run.py \
     --run-dir <run-dir> \
     --mode command \
     --command "<solve-command>" \
     --cwd <workspace> \
     --flag-regex '<flag-regex>' \
     --local
   ```

4. Finalize

   ```bash
   python3 scripts/challenge_finalize.py \
     --run-dir <run-dir> \
     --status solved \
     --require-verifier \
     --generate-writeup \
     --cleanup \
     --update-metrics
   ```

5. Check

   ```bash
   ctf-check
   ```

Do not move to the next challenge until finalize succeeds for the current
`run_dir`.

## Where Details Live

- [GUIDE.md](GUIDE.md): detailed manual, install/deploy, repo structure,
  lifecycle, queue/worker/resource, sessions, browser, callback, GDB,
  verifier, platforms, metrics, benchmarking, troubleshooting.
- [docs/operator-mode.md](docs/operator-mode.md): real solving runbook to keep
  open during a challenge.
- [docs/regression.md](docs/regression.md): `ctf-status`, `ctf-check`,
  `ctf-regression`, marker interpretation, and shortcut installer behavior.
- [docs/dreamhack-adapter.md](docs/dreamhack-adapter.md): Dreamhack adapter and
  VM control boundaries.
- [docs/ctfd-adapter.md](docs/ctfd-adapter.md): CTFd adapter behavior.
- [docs/tools.md](docs/tools.md): generated MCP tool signatures.

## Important Boundaries

- Writeups and copied exploit files are local-only under `~/SolvedWriteUp` or
  `CTF_SOLVED_WRITEUP_ROOT`.
- Public metrics under `metrics/` must not contain flags, exploit code, raw
  transcripts, cookies, tokens, private URLs, or private absolute paths.
- The active canonical MCP server name is `ctf_solver`.
- `dreamhack_solver` is legacy detector/migration text only, not an active MCP
  name.
- Dreamhack is a platform adapter inside `ctf_solver`, not a separate canonical
  MCP server.
- ReVa is connected only when Ghidra/ReVa is running.
- Missing `ctf-pwn:latest` is optional unless the current task needs pwn/GDB
  Docker mode.
- Do not paste raw `~/.claude.json`, cookies, tokens, session values, CSRF
  values, browser storage, raw platform responses, flags, exploits, or private
  run logs. Use `ctf-status` or `ctf-check` marker output instead.
