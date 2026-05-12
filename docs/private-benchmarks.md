# Private Benchmark Packs

Private benchmark packs are real solver evaluation inputs. They may point at
local challenge artifacts, private notes, or event-specific fixtures, so the
pack root must stay outside this repo.

This scaffold does not run Codex, Claude, Docker, GDB, browsers, or live CTF
targets. It only creates pack structure, validates manifests, exports
public-safe summaries, and compares before/after result snapshots.

## Storage Policy

- Private pack root: `CTF_BENCHMARK_ROOT`, default `Path.home() / ".ctf-solver" / "benchmarks"`
- Private run result root: `CTF_BENCHMARK_RUN_ROOT`, default `Path.home() / ".ctf-solver" / "benchmark-runs"`
- Public comparison reports: `metrics/comparisons`
- Public benchmark exports: `metrics/benchmark_exports`

`scripts/doctor.py` warns if either private benchmark root resolves inside the
repo. `scripts/benchmark_pack_init.py` refuses repo output by default.

## Pack Manifest

Each pack contains `benchmark_pack.yaml` plus local-only subdirectories:

```text
<pack>/
├── benchmark_pack.yaml
├── artifacts/
├── results/
└── notes/
```

Manifest schema:

```yaml
pack_id: "dh-private-core"
name: "Dreamhack private core pack"
version: 1
created_at: "2026-05-12T00:00:00Z"
owner: ""
public_safe_description: "Private benchmark metadata only."
challenges:
  - benchmark_id: "dh-web-001"
    challenge_id: "private-web-id"
    platform: "dreamhack"
    event: "dreamhackWargame"
    category: "web"
    difficulty: "medium"
    local_capable: true
    remote_required: true
    artifact_dir: "artifacts/dh-web-001"
    expected_timeout_sec: 1800
    tags: ["web", "bot"]
    public_notes: "Browser and callback flow."
    private_notes_path: "notes/dh-web-001.md"
```

Do not put flags, exploit code, raw transcripts, cookies, tokens, private
absolute paths, copied private challenge statements, private URLs, screenshots,
browser storage state, or raw model output in the manifest.

## Create And Validate

```bash
python3 scripts/benchmark_pack_init.py \
  --pack-id dh-private-core \
  --name "Dreamhack private core pack" \
  --json

python3 scripts/benchmark_pack_validate.py \
  "$CTF_BENCHMARK_ROOT/dh-private-core/benchmark_pack.yaml" \
  --json
```

`artifact_dir` and `private_notes_path` must be relative paths that stay under
the private pack root.

## Record Private Results

The live solver runner is intentionally not implemented here. Store raw private
run output under `CTF_BENCHMARK_RUN_ROOT` or the pack `results/` directory.
Those private files may contain raw transcripts, internal paths, or verifier
evidence and must not be committed.

Use existing lifecycle/finalize/verifier scripts to produce public-safe result
fields when possible. A private result JSON can also contain extra private
fields; export strips them before writing repo metrics.

## Export Public-Safe Results

```bash
python3 scripts/benchmark_export_public.py \
  --input "$CTF_BENCHMARK_RUN_ROOT/feature-a/run-results.jsonl" \
  --output metrics/benchmark_exports/feature-a.jsonl \
  --json
```

The export keeps only benchmark id, category, platform, event, status, duration,
time-to-flag, verifier booleans, aggregate tool/session/browser/callback
counts, cleanup bytes, remote wait time, and aggregate AI token/cost fields.
It strips flags, exploits, raw logs, private paths, private challenge
descriptions, cookies, tokens, and private URLs.

## Before/After Comparison

Run the same private pack before and after a feature change, export both runs,
then compare public-safe snapshots:

```bash
python3 scripts/benchmark_compare.py \
  --before metrics/benchmark_exports/before.jsonl \
  --after metrics/benchmark_exports/after.jsonl \
  --output metrics/comparisons/feature-a.json \
  --json
```

The comparison reports deltas for solve rate, pass@1, pass@3, median
time-to-flag, verifier success, AI cost, tokens, category groups, and
platform/event groups. The report is safe to keep under `metrics/comparisons`.

## Never Commit

- private benchmark packs or artifacts
- private benchmark raw run results
- flags or flag-like values
- exploit source or payload bodies
- raw transcripts, verifier output, screenshots, or browser storage state
- private absolute paths or private URLs
- cookies, bearer headers, API keys, OAuth values, passwords, or account data
