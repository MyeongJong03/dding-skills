# Regression Command Pack

`scripts/status_summary.py` and `scripts/regression_check.py` provide
paste-safe, marker-based status and regression output. They are meant for
handoff: run one command, paste the whole marker block, and the next terminal or
agent can judge the state without seeing raw secrets.

Shortcuts are preferred when installed:

```bash
ctf-status
ctf-check
ctf-regression
```

Direct fallbacks:

```bash
python3 scripts/status_summary.py
python3 scripts/regression_check.py --quick
python3 scripts/regression_check.py
```

## Status Summary

Use this when someone asks for current setup or repo status:

```bash
ctf-status
```

Fallback and optional formats:

```bash
python3 scripts/status_summary.py
python3 scripts/status_summary.py --verbose
python3 scripts/status_summary.py --json
```

Default output is bounded by:

```text
===== CTF_SOLVER_STATUS_BEGIN =====
[git]
[docker]
[mcp_json_summary]
[mcp_raw_consistency]
[mcp_live]
[redaction]
[repo_raw_grep]
[doctor]
===== CTF_SOLVER_STATUS_END =====
```

The command performs quick checks only. It does not run the full pytest suite
and does not run live platform smoke.

## `[mcp_raw_consistency]`

This section checks whether the active MCP config uses the expected canonical
server names without printing the active config body.

What it reports:

- whether the raw config text contains quoted `ctf_solver`
- whether the raw config text contains quoted `dreamhack_solver`
- whether the raw config text contains quoted `ReVa`
- whether parsed `mcpServers` contains those same names
- whether raw-text booleans and parsed-JSON booleans match

Normal current setup:

```text
raw_contains_ctf_solver=true
raw_contains_dreamhack_solver=false
json_has_ctf_solver=true
json_has_dreamhack_solver=false
raw_json_ctf_solver_match=true
raw_json_dreamhack_solver_match=true
ok=true
```

`raw_contains_dreamhack_solver=false` is the expected active-config result.
`dreamhack_solver` can still appear inside this repo because legacy detector,
migration guidance, and regression fixtures need to recognize the old name.
That repo-local legacy text is different from registering `dreamhack_solver` as
an active MCP server.

Safety guarantee:

- `~/.claude.json` is never printed.
- The script summarizes MCP server names from `mcpServers`.
- Raw cookies, auth headers, tokens, account metadata, browser storage, flags,
  platform responses, writeups, exploits, and private run logs are not printed.

Use `--verbose` only when you need benign grep locations for debugging. Even in
verbose mode, grep details are location-only, not matched line bodies.

## Regression Check

Use the quick check after routine edits:

```bash
ctf-check
```

Fallback:

```bash
python3 scripts/regression_check.py --quick
```

Use the full check before larger handoffs, release-like changes, or commits:

```bash
ctf-regression
```

Fallback:

```bash
python3 scripts/regression_check.py
```

Default full output is bounded by:

```text
===== CTF_SOLVER_REGRESSION_BEGIN =====
[git]
[secret_scan]
[mcp_raw_consistency]
[pytest]
[doctor]
[update_metrics]
[dump_mcp_tools]
[redact_self_test]
[offline_e2e_ctfd]
[offline_e2e_dreamhack]
[compileall]
[git_diff_check]
===== CTF_SOLVER_REGRESSION_END =====
```

The full command runs:

- strict secret scan, including untracked files
- `python3 -m pytest tests`
- `python3 scripts/doctor.py`
- public metrics safety check
- MCP tools documentation drift check
- redaction self-test
- fixture-only offline E2E smoke for CTFd and Dreamhack
- compileall for `tools`, `server.py`, `scripts`, and `ctf_solver_core`
- worktree and staged `git diff --check`

`--quick` replaces the full pytest suite with selected fast regression tests.
It still keeps the marker layout. `--skip-offline-e2e` is available when you
need a faster local-only check and have already run the offline E2E smoke.

## Paste-Safe Marker Usage

Good handoff:

```bash
ctf-status
```

or:

```bash
ctf-check
```

Then paste the whole marker block.

Avoid pasting:

- raw `~/.claude.json`
- raw `~/.codex/config.toml`
- cookies, bearer headers, session values, CSRF values
- browser storage state contents
- platform raw responses
- flags
- exploit code
- private run logs
- private URLs with secret query strings

The receiving agent should judge status by section names and `ok=true/false`
lines, not by asking for raw config files.

## Operator Shortcuts

`scripts/install_shortcuts.py` installs macOS-friendly wrappers into
`~/.local/bin` by default.

Dry-run first:

```bash
python3 scripts/install_shortcuts.py --dry-run
```

Install:

```bash
python3 scripts/install_shortcuts.py
```

Uninstall:

```bash
python3 scripts/install_shortcuts.py --uninstall
```

Installed commands:

- `ctf-status` runs `python3 <repo>/scripts/status_summary.py`
- `ctf-check` runs `python3 <repo>/scripts/regression_check.py --quick`
- `ctf-regression` runs `python3 <repo>/scripts/regression_check.py`

The wrappers embed the absolute repo path from the current checkout. If the
repo is moved, rerun the installer from the new checkout.

If `~/.local/bin` is not on `PATH`, add it in the shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Options:

- `--dry-run` shows the planned install/uninstall without writing files.
- `--bin-dir <path>` installs into a different wrapper directory.
- `--uninstall` removes wrappers managed by this installer.
- `--force` replaces or removes an existing unmanaged file with the same name.

Windows/WSL2 shortcuts are a later phase. For now, use direct Python commands
there, or install wrappers only inside a WSL shell after checking the target
`PATH`.

## Network And Secret Policy

Regression commands follow a no live network default and do not perform live
platform actions. Offline E2E uses synthetic local fixtures and temp roots only.
Live smoke remains a separate explicit step using the live smoke runbook and
`--live` approval.

The command pack captures child command output and only prints redacted,
bounded summaries on failure. Do not paste raw global config files, browser
storage state, cookies, auth headers, platform responses, flags, writeups,
exploit code, or private run logs.
