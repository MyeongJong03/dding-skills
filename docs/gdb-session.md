# GDB Debug Sessions

GDB sessions are local-only pwn debugging helpers for crash analysis and exploit refinement. They are not a full exploit solver and they do not connect to live remote CTF targets.

## Storage

- Metadata root: `CTF_GDB_ROOT` or `~/.ctf-solver/gdb`
- Artifact root: `CTF_GDB_ARTIFACT_ROOT` or `~/.ctf-solver/gdb-artifacts`
- Session metadata: `<gdb_root>/<gdb_session_id>/gdb_session.json`
- Bounded local log: `<gdb_root>/<gdb_session_id>/gdb.log`
- Core dumps and memory dumps, if manually created later, belong under `<gdb_artifact_root>/<gdb_session_id>/`

These roots should not be inside the repo. `scripts/doctor.py` reports the resolved roots and warns if they are repo-local.

## Modes

- `docker`: default. Runs `gdb` inside `ctf-pwn:latest` through the persistent session daemon, mounting the workspace at `/workspace`.
- `local`: runs local `gdb` when available. On macOS this may be absent or codesign-limited, so a clear error is acceptable.
- `mock`: uses canned GDB output for parser and CLI tests. It requires no Docker or GDB.

Docker mode checks that the Docker CLI, daemon, and `ctf-pwn:latest` image are available. If not, it returns a clear error; regression tests use mock mode by default.

## Docker Runtime Smoke

Build or rebuild the pwn image when needed:

```bash
docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest .
docker run --rm --platform linux/amd64 --network none ctf-pwn:latest bash -lc 'python3 -c "import pwn,z3,Crypto,gmpy2,sympy,requests,httpx; print(\"python-modules-ok\")"; gdb --version | head -1; pwninit --version; one_gadget --version; seccomp-tools --version; r2 -v | head -1'
```

Validate the real Docker GDB runtime against a local toy crash binary:

```bash
python3 scripts/gdb_docker_smoke.py --json
```

Optional pytest validation is disabled by default and only runs when explicitly enabled:

```bash
CTF_RUN_DOCKER_GDB_TESTS=1 python3 -m pytest tests/test_gdb_docker_smoke.py -q
```

On macOS, Docker mode is preferred for pwn debugging. The smoke script compiles and debugs only a local toy binary; it does not attach GDB to live remote services or external CTF targets.

## CLI

```bash
sid=$(python3 scripts/gdb_start.py --binary ./chall --mode docker --workspace "$PWD" --run-id "$RUN_ID")
python3 scripts/gdb_cmd.py --gdb-session-id "$sid" --cmd "break main" --json
python3 scripts/gdb_continue.py --gdb-session-id "$sid" --json
python3 scripts/gdb_wait_crash.py --gdb-session-id "$sid" --timeout-ms 5000 --json
python3 scripts/gdb_registers.py --gdb-session-id "$sid" --json
python3 scripts/gdb_backtrace.py --gdb-session-id "$sid" --json
python3 scripts/gdb_vmmap.py --gdb-session-id "$sid" --json
python3 scripts/gdb_telescope.py --gdb-session-id "$sid" --address '$rsp' --count 8 --json
python3 scripts/gdb_close.py --gdb-session-id "$sid" --reason done --json
```

Mock mode:

```bash
sid=$(python3 scripts/gdb_start.py --binary ./toy --mode mock --run-id "$RUN_ID")
python3 scripts/gdb_list.py --run-id "$RUN_ID" --include-closed --json
```

## MCP Tools

The `ctf_solver` MCP server exposes `gdb_start`, `gdb_cmd`, `gdb_continue`, `gdb_wait_crash`, `gdb_registers`, `gdb_backtrace`, `gdb_vmmap`, `gdb_telescope`, `gdb_close`, and `gdb_list`.

All command output is bounded and redacted before it is returned.

## Finalize And Metrics

`scripts/challenge_finalize.py` closes GDB sessions for the run by default. Use `--keep-gdb-sessions` only for explicit handoff.

Finalization records public-safe counters:

- `gdb_session_count`
- `closed_gdb_session_count`
- `gdb_crash_count`
- `gdb_command_count`
- `gdb_used`

Writeup generation can include a redacted GDB summary: session ids, modes, statuses, command counts, and crash signal/PC summaries. It does not include raw logs, core dumps, memory dumps, exploit code from GDB logs, flags, or private paths.

## Limitations

- No full exploit solver.
- No live remote target testing.
- No automatic core dump collection.
- Windows/WSL2 validation is a future phase.
