# Public Smoke Benchmarks

This directory contains fixed, public-safe smoke benchmark definitions for the
metrics pipeline. They are illustrative fixtures for report stability checks,
not actual solve evaluation targets.

The smoke pack deliberately avoids live CTF sites, browser automation, Docker
exploit runs, GDB, and provider calls. A runner may use these records to test
`benchmark_report.py`, `performance_report.py`, and dashboard rendering, but it
must not treat them as proof that a solver can solve a real challenge.

## Public Definition Rules

Allowed fields are:

- `benchmark_id`
- `category`
- `platform`
- `event`
- `local_capable`
- `remote_required`
- `difficulty`
- `timeout_sec`
- `tags`
- `notes`

Do not add flags, exploit code, raw transcripts, private challenge paths,
private URLs, copied problem statements, cookies, provider account metadata, or
raw model output.

## Private Packs

Private benchmark packs can contain real event names, private challenge naming,
local file mapping, or verifier wiring, but they must live outside this repo.
Use `CTF_BENCHMARK_ROOT` for private definitions.

## Recording And Reporting

Record a public-safe smoke result:

```bash
python3 scripts/benchmark_record_result.py \
  --benchmark-id web-xss-callback \
  --run-id smoke-run-001 \
  --status solved \
  --attempt-index 1 \
  --duration-sec 120 \
  --time-to-flag-sec 90 \
  --verifier-success true \
  --verifier-flag-found true \
  --platform smoke \
  --event smoke \
  --category web \
  --json
```

Generate reports:

```bash
python3 scripts/benchmark_report.py --json
python3 scripts/ai_usage_report.py --json
python3 scripts/performance_report.py --json
```

Before and after solver feature changes, compare pass@1, pass@3, solve rate,
verifier success rate, time-to-flag aggregates, and token/cost totals. Keep
private benchmark packs and private usage exports out of git.
