# Benchmarking

P2-0 adds measurement scaffolding before adding more solver features. The goal is to compare changes with public-safe aggregate data instead of guessing whether automation improved.

This scaffold does not invoke Codex, Claude, Docker, browsers, GDB, or live CTF sites. It records benchmark definitions and result summaries that were produced by normal challenge lifecycle commands.

## Storage

- Public definitions: `config/benchmarks/*.json`
- Private definitions: `CTF_BENCHMARK_ROOT` or `Path.home() / ".ctf-solver" / "benchmarks"`
- Private benchmark run details: `CTF_BENCHMARK_RUN_ROOT` or `Path.home() / ".ctf-solver" / "benchmark-runs"`
- Public results: `metrics/benchmark_summary.jsonl`
- Public dashboard: `metrics/benchmark_dashboard.md`
- Public exports: `metrics/benchmark_exports`
- Public comparisons: `metrics/comparisons`

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

## Public Smoke Pack

`benchmarks/smoke/*.yaml` contains fixed public-safe benchmark definitions for
pipeline testing. These examples are synthetic and illustrative. They are meant
to keep `benchmark_report.py`, `performance_report.py`, and regression tests
stable; they are not actual solver evaluation tasks.

The smoke pack must stay local-only and deterministic. Do not add live CTF
targets, browser runs, Docker exploit runs, GDB sessions, provider calls, raw
outputs, copied challenge statements, private file mappings, or private URLs.

Private benchmark packs may contain real event names, local fixture wiring, or
private challenge naming, but they must live outside the repo under
`CTF_BENCHMARK_ROOT`. Raw private benchmark run data must live outside the repo
under `CTF_BENCHMARK_RUN_ROOT`.

Create and validate a private pack skeleton:

```bash
python3 scripts/benchmark_pack_init.py --pack-id dh-private-core --name "Dreamhack private core pack" --json
python3 scripts/benchmark_pack_validate.py "$CTF_BENCHMARK_ROOT/dh-private-core/benchmark_pack.yaml" --json
```

Export private run results into a public-safe JSONL and compare before/after
feature changes:

```bash
python3 scripts/benchmark_export_public.py --input "$CTF_BENCHMARK_RUN_ROOT/before/results.jsonl" --output metrics/benchmark_exports/before.jsonl --json
python3 scripts/benchmark_export_public.py --input "$CTF_BENCHMARK_RUN_ROOT/after/results.jsonl" --output metrics/benchmark_exports/after.jsonl --json
python3 scripts/benchmark_compare.py --before metrics/benchmark_exports/before.jsonl --after metrics/benchmark_exports/after.jsonl --output metrics/comparisons/feature-change.json --json
```

See [private-benchmarks.md](private-benchmarks.md) for the manifest schema and
runbook.

Use the smoke fixtures to compare before and after feature changes:

```bash
python3 scripts/benchmark_report.py --json
python3 scripts/ai_usage_report.py --json
python3 scripts/performance_report.py --json
```

Compare pass@1, pass@3, solve rate, verifier success rate, time-to-flag
aggregates, and token/cost totals.

## Do Not Commit

- private benchmark files
- flags or flag-like strings
- exploit source
- raw transcripts or verifier output
- private absolute paths
- private URLs or callback payload bodies
- screenshots or browser storage state
