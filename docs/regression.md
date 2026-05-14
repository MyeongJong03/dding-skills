# Regression Command Pack

`scripts/status_summary.py` and `scripts/regression_check.py` provide
paste-safe, marker-based command output for routine repo health checks. They
are designed for manual handoff: run one command, paste the whole marker block,
and the receiving agent can judge the state without asking for every individual
command result.

## Status Summary

Use this when you ask for the current repo/setup status:

```bash
python3 scripts/status_summary.py
python3 scripts/status_summary.py --verbose
python3 scripts/status_summary.py --json
```

The default output is bounded by:

```text
===== CTF_SOLVER_STATUS_BEGIN =====
[git]
[docker]
[mcp_json_summary]
[mcp_live]
[redaction]
[repo_raw_grep]
[doctor]
===== CTF_SOLVER_STATUS_END =====
```

The command performs quick checks only. It does not run the full pytest suite
and does not run live platform smoke.

In the normal clean case, `[redaction]` and `[repo_raw_grep]` print only short
`result=... clean` lines. Use `--verbose` when you need the benign grep
locations for debugging. If a real finding appears, the default output includes
the finding count and file locations.

Safety rules:

- `~/.claude.json` is never printed. The script parses it only to summarize
  `mcpServers` names.
- Repo grep details, when shown with `--verbose` or on failure, are
  location-only (`relative-file:line`), never matched line bodies.
- Docker is optional. Missing Docker or missing `ctf-pwn:latest` is reported as
  info, not as a failure.
- The summary must not include raw cookies, auth headers, private CTF URLs,
  flags, account metadata, browser storage, or live credential values.

## Regression Check

Use this after larger changes, before committing or asking another terminal to
review the state:

```bash
python3 scripts/regression_check.py
python3 scripts/regression_check.py --quick
python3 scripts/regression_check.py --quick --skip-offline-e2e
```

The default output is bounded by:

```text
===== CTF_SOLVER_REGRESSION_BEGIN =====
[git]
[secret_scan]
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
- MCP docs drift check
- redaction self-test
- fixture-only offline E2E smoke for CTFd and Dreamhack
- compileall for `tools`, `server.py`, `scripts`, and `ctf_solver_core`
- worktree and staged `git diff --check`

`--quick` replaces the full pytest suite with selected fast regression tests.
It still keeps the marker layout. `--skip-offline-e2e` is available when you
need a faster local-only check and have already run the offline E2E smoke.

## Network And Secret Policy

Regression commands follow a no live network default and do not perform live
network platform actions. Offline E2E
uses synthetic local fixtures and temp roots only. Live smoke remains a
separate explicit step using the live smoke runbook and `--live` approval.

The command pack captures child command output and only prints redacted,
bounded summaries on failure. Do not paste raw global config files, browser
storage state, cookies, auth headers, platform responses, flags, writeups,
exploit code, or private run logs.
