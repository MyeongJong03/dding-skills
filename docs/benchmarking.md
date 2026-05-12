# Benchmarking

P2-0 adds measurement scaffolding before adding more solver features. The goal is to compare changes with public-safe aggregate data instead of guessing whether automation improved.

This scaffold does not invoke Codex, Claude, Docker, browsers, GDB, or live CTF sites. It records benchmark definitions and result summaries that were produced by normal challenge lifecycle commands.

## Storage

- Public definitions: `config/benchmarks/*.json`
- Private definitions: `CTF_BENCHMARK_ROOT` or `Path.home() / ".ctf-solver" / "benchmarks"`
- Public results: `metrics/benchmark_summary.jsonl`
- Public dashboard: `metrics/benchmark_dashboard.md`

Public benchmark data must not contain flags, exploit code, raw output, transcripts, private absolute paths, cookies, tokens, private URLs, browser artifact paths, or problem text by default.

## Create a Benchmark

```bash
python3 scripts/benchmark_init.py \
  --benchmark-id dh-web-example-001 \
  --platform dreamhack \
  --event dreamhackWargame \
  --category web \
  --local-capable true \
  --remote-required true \
  --timeout-sec 1800 \
  --verifier-required true \
  --json
```

Use `--private` for definitions that contain private naming or event details.

## Record a Result

```bash
python3 scripts/benchmark_record_result.py \
  --benchmark-id dh-web-example-001 \
  --run-id RUN-DEMO-1 \
  --status solved \
  --attempt-index 1 \
  --duration-sec 420 \
  --time-to-flag-sec 390 \
  --verifier-success true \
  --verifier-flag-found true \
  --platform dreamhack \
  --event dreamhackWargame \
  --category web \
  --json
```

The duplicate key is `(benchmark_id, run_id, attempt_index)`. A duplicate append is skipped unless `--replace` is supplied.

Finalization can also record a benchmark result:

```bash
python3 scripts/challenge_finalize.py \
  --run-dir <run-dir> \
  --status solved \
  --update-metrics \
  --benchmark-id dh-web-example-001 \
  --attempt-index 1
```

## Reports

```bash
python3 scripts/benchmark_report.py --json
python3 scripts/performance_report.py --json
```

`pass@1` is the percentage of benchmark items solved on attempt 1. `pass@3` is the percentage solved by attempt 3. The dashboard also reports solve, abandon, timeout, verifier success, and time-to-flag aggregates by category and platform/event.

## Do Not Commit

- private benchmark files
- flags or flag-like strings
- exploit source
- raw transcripts or verifier output
- private absolute paths
- private URLs or callback payload bodies
- screenshots or browser storage state
