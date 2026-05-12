# Browser Actions

P1-6 adds a local-only browser action layer between platform adapters and future
web solvers. It can drive Playwright when installed, but Playwright is optional:
the rest of the repo and regression suite must pass without it.

## Playwright Runtime Validation

Playwright is an optional runtime. On macOS Homebrew Python,
`python3 -m pip install playwright` can fail with PEP 668
`externally-managed-environment`. Do not use `--break-system-packages` as the
default fix. Prefer either `uv` or a venv outside this repo.

Recommended path 1, uv:

```bash
uv run --with playwright python -c "import playwright; print('ok')"
uv run --with playwright python -m playwright install chromium
uv run --with pytest --with playwright python -m pytest tests/test_browser_actions.py -q
```

When using the CLI through uv, run the browser command in the same uv-provided
runtime:

```bash
uv run --with playwright python scripts/browser_start.py --run-id RUN1 --json
```

Recommended path 2, repo-external venv:

```bash
python3 -m venv ~/.ctf-solver/venvs/browser
~/.ctf-solver/venvs/browser/bin/python -m pip install playwright pytest
~/.ctf-solver/venvs/browser/bin/python -m playwright install chromium
~/.ctf-solver/venvs/browser/bin/python -m pytest tests/test_browser_actions.py -q
```

No live external CTF site should be used for browser regression tests. Use local
HTML files, data URLs, or mock loopback servers only.

Check the runtime without installing or contacting the network:

```bash
python3 scripts/browser_playwright_check.py --use-uv --json
python3 scripts/doctor.py
```

If Playwright is missing, `browser_start.py` and the MCP `browser_start` tool
return `reason: playwright_not_installed`. If the Python package exists but the
browser binary is missing, the result points to installing Chromium with
Playwright.

## Local-Only Roots

| Purpose | Default | Override |
| --- | --- | --- |
| Browser daemon/session metadata | `Path.home() / ".ctf-solver" / "browser"` | `CTF_BROWSER_ROOT` |
| Browser screenshots/artifacts | `Path.home() / ".ctf-solver" / "browser-artifacts"` | `CTF_BROWSER_ARTIFACT_ROOT` |
| Browser profile metadata | `Path.home() / ".ctf-solver" / "browser-states"` | `CTF_BROWSER_STATE_ROOT` |

Do not put these roots inside the repo. `scripts/doctor.py` warns if an override
resolves into the repo, and `browser_start` refuses repo-internal browser roots.

## Start A Session

```bash
python3 scripts/browser_start.py --run-id RUN1 --challenge-id CHAL1 --json
```

The JSON result includes `browser_session_id`. Use that id for all follow-up
actions. Default browser is Chromium and default mode is headless. Use
`--headed` only for explicit manual debugging.

With a registered browser state profile:

```bash
python3 scripts/browser_state_init.py \
  --platform thcon \
  --event THCON \
  --profile main \
  --storage-state ~/.ctf-solver/browser-auth/thcon-main.json \
  --json

python3 scripts/browser_start.py \
  --run-id RUN1 \
  --platform thcon \
  --event THCON \
  --profile main \
  --json
```

The profile helper stores metadata only. It does not print or parse storage
state contents. `browser_start --storage-state <path>` is also supported, but
the path must exist and must be outside the repo.

## Local Examples

Use local files, data URLs, or mock servers for tests and dry runs. Do not add
external CTF site regression tests.

```bash
python3 scripts/browser_goto.py \
  --browser-session-id <browser_session_id> \
  --url 'data:text/html,<title>Local</title><input id="name">' \
  --json

python3 scripts/browser_fill.py \
  --browser-session-id <browser_session_id> \
  --selector '#name' \
  --value 'local test value' \
  --json

python3 scripts/browser_eval.py \
  --browser-session-id <browser_session_id> \
  --expression 'document.title' \
  --json

python3 scripts/browser_screenshot.py \
  --browser-session-id <browser_session_id> \
  --name local-page \
  --json

python3 scripts/browser_close.py --browser-session-id <browser_session_id> --json
```

Uploads use file counts in output, not raw paths:

```bash
python3 scripts/browser_upload.py \
  --browser-session-id <browser_session_id> \
  --selector 'input[type=file]' \
  --file ./fixture.txt \
  --json
```

## Console, Network, Cookies

```bash
python3 scripts/browser_console.py --browser-session-id <browser_session_id> --limit 20 --json
python3 scripts/browser_network.py --browser-session-id <browser_session_id> --limit 20 --json
python3 scripts/browser_cookies.py --browser-session-id <browser_session_id> --json
```

Cookie output is summary-only: name, domain, path, expiry, `httpOnly`, `secure`,
and `sameSite`. Values are always redacted.

Network output is bounded and body-free. Sensitive headers such as authorization
and cookie headers are redacted. Query parameters with sensitive names are
redacted. Eval output is bounded and passed through the same text redactor.

## MCP Tools

The same operations are exposed through MCP server `ctf_solver`:

- `browser_start`
- `browser_goto`
- `browser_click`
- `browser_fill`
- `browser_eval`
- `browser_upload`
- `browser_screenshot`
- `browser_console`
- `browser_network`
- `browser_cookies`
- `browser_close`
- `browser_list`

If Claude MCP is expected to use browser tools, the registered `ctf_solver`
command may need Playwright in the same runtime. With uv, add
`--with playwright` to the MCP command, for example:

```bash
claude mcp add --scope user ctf_solver \
  -- <path-to-uv> run --with playwright --with "mcp[cli]" --with requests --with httpx \
  mcp run <path-to-repo>/server.py
```

Browser artifacts, including screenshots, stay under
`CTF_BROWSER_ARTIFACT_ROOT` and are local-only.

## Finalize Cleanup

`scripts/challenge_finalize.py` closes browser sessions linked to the run by
default and records aggregate public-safe counters in `finalization.json`:

- `browser_session_count`
- `closed_browser_session_count`
- `browser_actions_count`
- `browser_screenshot_count`
- `browser_network_event_count`

Use `--keep-browser-sessions` only for explicit handoff. If the browser daemon
is unavailable during finalization, the run records a warning-style result and
finalization continues.

## Multi-Terminal Isolation

Associate browser sessions with `run_id` and `challenge_id`. Do not reuse a
browser session across different runs. `browser_list.py --run-id <run_id>` is
the safe way to inspect active sessions for one terminal.

## Limitations

- Real Dreamhack, THCON, and CTFd live browser adapters are future work.
- No live external regression tests.
- No full browser solver.
- No browser-based flag submission unless future platform policy explicitly
  allows submission and the worker is primary.
- No Codex or Claude subprocess orchestration.
