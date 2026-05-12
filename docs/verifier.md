# Solve Verifier

The verifier records independent solve evidence before a run is marked solved.
It stores private results in `<run_dir>/verifier.json` and can optionally store
private command/session output in `<run_dir>/logs/verifier-output.txt`.

Verifier data is local-first. Public metrics may include only summary booleans
and small counters, never raw flags, exploit code, transcripts, or private paths.

## Command Mode

Use command mode for exploit scripts and one-shot proof commands.

```bash
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode command \
  --command "python3 exploit.py" \
  --cwd <workspace> \
  --timeout-sec 10 \
  --retries 1 \
  --flag-regex 'DH\{[^}]+\}' \
  --local
```

`--success-regex` can be used instead of a flag regex when the proof is a marker
such as `pwned` or `verified`. `--fail-regex` forces failure if an error marker
appears.

## Session Mode

Use session mode when an exploit depends on an existing persistent shell, REPL,
or menu interaction.

```bash
sid=$(python3 scripts/session_start.py shell --run-id "$RUN_ID" --json | jq -r .session.session_id)
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode session \
  --session-id "$sid" \
  --session-input "echo verified" \
  --expect verified \
  --timeout-sec 2 \
  --local
```

Session verification uses bounded reads/expects through the local session daemon.
It does not implement browser automation or GDB-specific behavior.

## Manual Evidence Mode

Use manual mode when another terminal already produced evidence.

```bash
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode manual \
  --evidence-text "remote exploit printed DH{...}" \
  --flag-regex 'DH\{[^}]+\}' \
  --remote
```

The stored preview is redacted and bounded by default. The raw flag value is not
stored in `verifier.json`.

## Local Vs Remote

Use `--local` for local proof and `--remote` for remote target proof. If neither
is supplied, the target is `unknown`. This target is reflected in writeups and
public metrics summaries.

## Finalization

`challenge_finalize.py` reads `<run_dir>/verifier.json`.

```bash
python3 scripts/challenge_finalize.py \
  --run-dir <run-dir> \
  --status solved \
  --require-verifier \
  --generate-writeup \
  --update-metrics
```

Without `--require-verifier`, finalization warns on `status=solved` without a
successful verifier. With `--require-verifier`, solved finalization fails unless
a successful verifier exists or `--force` is supplied.

Generated writeups include a Verification section with verifier ID, target, mode,
attempt count, duration, and redacted bounded preview.

## Public Metrics Boundary

Allowed public fields:

- `verifier_success`
- `verifier_flag_found`
- `verifier_target`
- `verifier_attempts`
- `verifier_duration_sec`

Forbidden public data:

- raw flag values
- exploit code
- raw stdout/stderr or session transcripts
- private absolute paths
- cookies, tokens, API keys, OAuth data, passwords, private keys

Writeups remain local-only under `CTF_SOLVED_WRITEUP_ROOT` or `~/SolvedWriteUp`
and are not pushed to GitHub by the lifecycle tools.
