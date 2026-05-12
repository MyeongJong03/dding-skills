# Persistent Sessions

Persistent sessions keep interactive processes alive across separate CLI or MCP calls. The backend is a local-only session daemon, so Codex and Claude can use the same session tools even when a single MCP process is not holding the child process handle.

## Daemon And Storage

- Daemon bind: `127.0.0.1` only.
- Daemon state: `~/.ctf-solver/sessiond/sessiond.json`.
- Session metadata: `~/.ctf-solver/sessions/<session_id>/session.json`.
- Overrides: `CTF_SESSIOND_ROOT`, `CTF_SESSION_ROOT`, `CTF_SESSIOND_HOST`, `CTF_SESSIOND_PORT`.
- `CTF_SESSIOND_HOST` must be `127.0.0.1`.
- The daemon control token is random, stored only in the local daemon state file, and not printed by normal commands.

Session metadata stores bounded process facts such as `session_id`, `run_id`, `challenge_id`, `kind`, `status`, `pid`, command, cwd, and byte counters. Raw transcripts are not written by default.

## Supported Kinds

- `shell`: interactive shell, `bash` on POSIX when available.
- `python`: `python3 -i` REPL.
- `sage`: Sage REPL from `SAGE_PATH` or `sage`.
- `nc`: interactive `nc <host> <port>` connection.
- `docker-shell`: interactive `ctf-pwn:latest` shell with `/workspace` mounted and ptrace-friendly Docker flags for local pwn debugging.

Docker and Sage are optional runtime dependencies. If unavailable, the session start returns a clear error instead of failing the full test suite.

## CLI Examples

```bash
sid=$(python3 scripts/session_start.py shell --run-id "$RUN_ID")
python3 scripts/session_write.py "$sid" "echo hello"
python3 scripts/session_expect.py "$sid" hello --timeout-ms 1000 --max-bytes 4000
python3 scripts/session_close.py "$sid" --reason done
```

Python REPL:

```bash
sid=$(python3 scripts/session_start.py python --run-id "$RUN_ID")
python3 scripts/session_write.py "$sid" "print(1+1)"
python3 scripts/session_expect.py "$sid" "2" --timeout-ms 1000
```

Netcat menu service:

```bash
sid=$(python3 scripts/session_start.py nc --host 127.0.0.1 --port 31337 --run-id "$RUN_ID")
python3 scripts/session_expect.py "$sid" "choice:" --timeout-ms 2000
python3 scripts/session_write.py "$sid" "1"
python3 scripts/session_read.py "$sid" --timeout-ms 500 --max-bytes 4000
```

Docker shell:

```bash
sid=$(python3 scripts/session_start.py docker-shell --workspace "$PWD" --run-id "$RUN_ID")
python3 scripts/session_write.py "$sid" "checksec ./chall"
python3 scripts/session_expect.py "$sid" "RELRO" --timeout-ms 2000
```

Daemon management:

```bash
python3 scripts/session_daemon.py status
python3 scripts/session_daemon.py stop
```

Use `--json` on session scripts for automation.

## MCP Tools

The `ctf_solver` MCP server exposes the same backend:

- `session_start(kind, command, cwd, run_id, challenge_id, worker_id, host, port, image, workspace, timeout_ms, env_json)`
- `session_write(session_id, data, newline, encoding)`
- `session_read(session_id, timeout_ms, max_bytes)`
- `session_expect(session_id, patterns, timeout_ms, max_bytes)`
- `session_close(session_id, reason)`
- `session_list(run_id, challenge_id, include_closed)`

Use `session_expect` for menus, prompts, and leak parsing. Use one-shot tools for non-interactive commands.

## Run Integration

Pass `--run-id` or `run_id` whenever a challenge run exists. `scripts/challenge_finalize.py` closes active sessions for that `run_id` by default and records:

- `closed_session_count`
- `session_count`
- `session_bytes_read`
- `session_bytes_written`

Use `--keep-sessions` only for explicit handoff. Session metrics are aggregate counters only; transcripts, flags, exploit code, private paths, and raw logs do not enter public metrics.

## Multi-Terminal Behavior

All clients talk to the same local daemon for the selected `CTF_SESSIOND_ROOT`. A stale daemon status file is recovered automatically when a new session starts. Session listing can filter by `run_id` and `challenge_id`; do not reuse a session from a different run.

## Security

The daemon never binds to external interfaces. Do not set session roots inside the repo. `scripts/doctor.py` warns when `CTF_SESSION_ROOT` or `CTF_SESSIOND_ROOT` resolves under the repo.

The child process environment is allowlisted by default: `PATH`, `TERM`, `LANG`, `LC_ALL`, and `SAGE_PATH`. Explicit environment values can be passed for a session, but sensitive-looking metadata is redacted. Avoid sending cookies, bearer tokens, API keys, OAuth values, passwords, or private keys through session commands.

## Related Debug Sessions

Pwn-specific GDB helpers live in [docs/gdb-session.md](gdb-session.md). They use the persistent session daemon for Docker/local process management, but keep separate GDB metadata and local-only logs under `CTF_GDB_ROOT`.

## Limitations

- Browser automation sessions are future work.
- Full verifier implementation is future work.
- Docker and Sage sessions depend on local Docker/Sage availability.
