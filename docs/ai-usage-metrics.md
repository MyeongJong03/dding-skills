# AI Usage Metrics

P2-0 records AI usage as local-only detail plus public-safe aggregates. It is a manual/import scaffold only. It does not call Codex, Claude, OpenAI, Anthropic, or any other provider.

## Storage

- Private detailed usage: `CTF_AI_USAGE_ROOT` or `Path.home() / ".ctf-solver" / "ai-usage"`
- Private metrics root: `CTF_PRIVATE_METRICS_ROOT` or `Path.home() / ".ctf-solver" / "metrics-private"`
- Public aggregate usage: `metrics/ai_usage_summary.jsonl`
- Public dashboard: `metrics/ai_usage_dashboard.md`

Private roots must stay outside the repo. `scripts/doctor.py` warns when private metrics or AI usage roots resolve inside the git root.

## Manual Record

```bash
python3 scripts/ai_usage_record.py \
  --run-id RUN-DEMO-1 \
  --provider codex \
  --model gpt-example \
  --input-tokens 12000 \
  --output-tokens 2400 \
  --cache-read-tokens 3000 \
  --cache-creation-tokens 500 \
  --cost-usd 0.42 \
  --duration-sec 600 \
  --platform dreamhack \
  --event dreamhackWargame \
  --category web \
  --json
```

The private record keeps `run_id`, optional session id, timing, token counts, cost, source, and notes. The public record keeps aggregate provider/model/date/category/platform totals only.

## Import From Explicit JSON

Imports require an explicit input path. The importer never reads provider config files by default and never stores the raw input.

```bash
python3 scripts/ai_usage_import.py \
  --input /path/to/redacted-usage-fixture.json \
  --source claude-json \
  --json
```

The importer extracts numeric usage-like fields such as input tokens, output tokens, cache token counts, duration, and cost. Account metadata fields are filtered and are not printed in the preview.

## Reports

```bash
python3 scripts/ai_usage_report.py --json
python3 scripts/performance_report.py --json
```

The AI dashboard reports aggregate token and cost totals by provider. The performance dashboard includes those totals alongside solve rate, verifier rate, time to flag, tool usage, session/browser/callback counters, cleanup bytes, and remote wait time.

## Public-Safe Rules

Public AI usage metrics may include provider, model, date, category, platform, event, aggregate token counts, aggregate cost, run count, solved count, and median time-to-flag if already public-safe.

Public AI usage metrics must not include prompts, transcripts, account metadata, private config paths, raw provider output, browser storage state, cookies, tokens, private URLs, flags, exploit code, or local evidence paths.
