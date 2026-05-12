# Web Callback Listener

The callback listener is a local-only scaffold for Web CTF workflows such as
XSS, admin bot confirmation, SSRF probes, CSP leak tests, CSS exfil, and
webhook-style blind bugs.

It does not start ngrok, cloudflared, bore, or any other tunnel provider. If an
external tunnel is configured manually, pass its base URL as metadata with
`--external-base-url`.

## Storage

| Purpose | Default | Override |
| --- | --- | --- |
| Callback hit logs and listener metadata | `Path.home() / ".ctf-solver" / "callbacks"` | `CTF_CALLBACK_ROOT` |
| Callback daemon state | `Path.home() / ".ctf-solver" / "callbackd"` | `CTF_CALLBACKD_ROOT` |

Hit logs are stored as local-only JSONL:

```text
<callback_root>/<listener_id>/hits.jsonl
<callback_root>/<listener_id>/listener.json
```

Do not put callback roots inside the repo. `scripts/doctor.py` warns if either
root resolves under the repository.

## Start

```bash
python3 scripts/callback_start.py \
  --run-id "$RUN_ID" \
  --challenge-id "$CHALLENGE_ID" \
  --json
```

The default bind host is `127.0.0.1`. Binding `0.0.0.0` or another public
interface is refused unless `--allow-public-bind` is explicitly supplied.

Manual external URL metadata:

```bash
python3 scripts/callback_start.py \
  --run-id "$RUN_ID" \
  --external-base-url "https://example-callback.invalid" \
  --json
```

The listener stores that base URL but does not create or manage a tunnel.

## Get URL

```bash
python3 scripts/callback_url.py --listener-id <listener_id> --json
python3 scripts/callback_url.py --listener-id <listener_id> --external --json
python3 scripts/callback_url.py --listener-id <listener_id> --path extra/probe --json
```

Local URL shape:

```text
http://127.0.0.1:<port>/<listener_id>
```

If `--token-path <segment>` was used at start time, the URL includes that
segment after the listener id.

## Payload Helper

```bash
python3 scripts/web_payload_helper.py --callback-url "$CALLBACK_URL" --json
```

Example snippets:

```html
<img src="http://127.0.0.1:9000/LISTENER" alt="">
<script>fetch("http://127.0.0.1:9000/LISTENER",{mode:'no-cors'})</script>
<script>fetch("http://127.0.0.1:9000/LISTENER",{method:'POST',mode:'no-cors',body:'callback=1'})</script>
```

CSS example:

```css
body{background-image:url("http://127.0.0.1:9000/LISTENER")}
```

Markdown image example:

```markdown
![callback](http://127.0.0.1:9000/LISTENER)
```

These snippets are helpers only. They do not submit payloads, launch browsers,
or solve exploits automatically.

## Wait And Inspect

Wait for a bot/admin/browser hit:

```bash
python3 scripts/callback_wait.py \
  --listener-id <listener_id> \
  --timeout-sec 15 \
  --min-hits 1 \
  --json
```

Inspect redacted hits:

```bash
python3 scripts/callback_hits.py --listener-id <listener_id> --limit 20 --json
```

List listeners by run:

```bash
python3 scripts/callback_list.py --run-id "$RUN_ID" --json
```

Close a listener:

```bash
python3 scripts/callback_close.py --listener-id <listener_id> --reason done --json
```

## Redaction

The listener stores redacted, bounded hit records by default.

Redacted headers include:

- `Authorization`
- `Cookie`
- `Set-Cookie`
- `X-Api-Key`
- `X-CSRF-Token`
- `X-Auth-Token`

Query and body fields are redacted when their key contains sensitive words such
as token, session, cookie, password, secret, key, auth, or flag. Flag-like values
are also redacted from text previews. Body preview size is bounded; raw request
bodies are not stored by default.

## Finalize, Verifier, Metrics

Associate listeners with `run_id`. `scripts/challenge_finalize.py` closes
callback listeners for the run by default and records public-safe counters:

- `callback_listener_count`
- `closed_callback_listener_count`
- `callback_hit_count`

Use `--keep-callbacks` only for explicit handoff.

Verifier manual mode can consume callback evidence directly:

```bash
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode manual \
  --callback-listener-id <listener_id> \
  --callback-min-hits 1 \
  --local
```

Generated writeups include callback listener/hit summaries when available.
Public metrics include only aggregate callback counters, never URLs, headers,
bodies, cookies, or private paths.

## MCP Tools

MCP server `ctf_solver` exposes:

- `callback_start`
- `callback_url`
- `callback_hits`
- `callback_wait`
- `callback_close`
- `callback_list`
- `web_payload_helper`

## Limitations

- No automatic tunnel provider.
- No live external network regression tests.
- No real CTF site callback tests in the test suite.
- No full web exploit solver.
- No Codex or Claude subprocess orchestration.
