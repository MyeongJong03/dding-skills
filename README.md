# dding-skills

CTF 문제 풀이를 위한 Codex-first, Claude-compatible AI 에이전트 세팅 모음입니다.
현재 주력 실행 환경은 Codex이며, Claude Code 설정은 optional/legacy compatibility로 유지합니다.

## 구성

```
dding-skills/
├── server.py              # MCP 서버 진입점
├── tools/                 # MCP 툴
├── ctf_solver_core/       # lifecycle path/lock/schema/session/browser/callback/platform helpers
├── scripts/               # doctor + lifecycle/finalization CLIs
├── metrics/               # public-safe metrics and dashboard
├── docs/                  # tools/lifecycle/metrics/GDB/platform/browser/callback/web workflow docs
├── Dockerfile.ctf         # CTF PWN/REV용 Docker 이미지
├── install.sh             # 자동 설치 스크립트
├── skills/
│   └── ctf-personal/      # 개인 CTF 풀이 패턴 (자동 학습으로 지속 업데이트)
└── config/
    ├── CLAUDE.base.md     # 공통 CTF workflow / rules
    ├── platforms.example.yaml
    ├── deploy.sh          # env.md + CLAUDE.base.md 배포
    ├── mac/env.md         # macOS 환경 정보
    └── windows/env.md     # Windows WSL2 환경 정보
```

### 동작 구조

```
Codex (primary)
  │
  ├─ ~/CTF/AGENTS.md  ──────────────────→  ~/CTF/CLAUDE.md
  │      └─ 스킬 로드 지시
  │             ├─ ctf-personal  ─────→  skills/ctf-personal/  (심볼릭 링크)
  │             ├─ ctf-pwn 등    ─────→  외부: ljagiello/ctf-skills
  │             └─ reva-*        ─────→  외부: cyberkaida/reverse-engineering-assistant
  │
  └─ MCP/CLI helper 호출
         └─ ctf_solver (CTF Solver) ───→  server.py → tools/*.py
                                      ├─ persistent session daemon (127.0.0.1)
                                      ├─ GDB pwn debug sessions (local/Docker/mock)
                                      ├─ web callback listener daemon (127.0.0.1)
                                      └─ web exploit workflow scaffold
```

`~/CTF/CLAUDE.md`는 심볼릭 링크가 아니라 `config/deploy.sh`가 `config/{mac|windows}/env.md`와 `config/CLAUDE.base.md`를 합쳐 생성하는 실제 파일입니다.
Codex는 `~/CTF/AGENTS.md`를 기본 설정 파일로 읽으며, deploy 단계에서 `CLAUDE.md`와 동기화됩니다.
Claude Code는 설치되어 있으면 같은 생성물을 compatibility 용도로 사용할 수 있지만, Claude CLI 부재는 Codex workflow의 실패가 아닙니다.

## MCP 툴 목록

MCP 서버명은 `ctf_solver`이고 표시명은 CTF Solver입니다. 실제 tool signature와 파라미터는 [docs/tools.md](docs/tools.md)를 기준으로 확인하세요.
문서 drift를 줄이려면 다음 명령으로 현재 코드에서 다시 생성할 수 있습니다.

```bash
python3 scripts/dump_mcp_tools.py --write docs/tools.md
```

### MCP 서버명 migration

- Old MCP server name: `dreamhack_solver`
- New canonical MCP server name: `ctf_solver`
- Reason: this server supports general CTF automation, not only Dreamhack.
- Dreamhack-specific helper tools such as `dreamhack_vm` remain unchanged.
- Codex-first users do not need Claude MCP registration unless they still use Claude Code.
- Default install does not modify global Claude/Codex config files. `--with-claude-mcp` is the explicit legacy compatibility path.

Legacy Claude Code users only:

    claude mcp remove dreamhack_solver
    claude mcp add ctf_solver -- <path-to-uv> run --with "mcp[cli]" --with requests --with httpx mcp run <path-to-repo>/server.py

## 외부 의존성

별도로 설치 필요한 것들입니다.

- **CTF Skills**: [ljagiello/ctf-skills](https://github.com/ljagiello/ctf-skills) — optional external 카테고리별 풀이 플레이북
- **ReVa**: [cyberkaida/reverse-engineering-assistant](https://github.com/cyberkaida/reverse-engineering-assistant) — Ghidra MCP 연동 스킬
- **Ghidra**: 리버싱 프레임워크 (ReVa 사용 시)

### Skills 설치 정책

- `ctf-personal`은 이 repo가 관리하는 personal skill이며, 기본 설치에서 `~/.agents/skills/ctf-personal`로 배포됩니다.
- `ljagiello/ctf-skills`는 optional external skills입니다. 성능과 커버리지 향상에 도움이 될 수 있지만, 외부 skill은 full agent permissions로 실행될 수 있으므로 설치 전에 내용을 검토해야 합니다.
- Codex를 실전에서 `~/CTF`에서 실행한다면 skills는 `~/.agents/skills` 또는 `~/CTF/.agents/skills`에 있어야 합니다.
- `~/ctf-solver/.agents/skills`는 repo-local/project scope라서, Codex를 `~/CTF`에서 실행하면 보이지 않을 수 있습니다.
- 이 repo의 external skills 설치 위치는 universal global `~/.agents/skills`입니다. `install.sh --with-external-skills`는 skills CLI의 all-agent 설치를 쓰지 않고, 임시 디렉터리에 clone한 뒤 고정된 11개 skill만 `~/.agents/skills`에 deterministic copy합니다.
- skills CLI는 여러 agent-specific directory에 설치할 수 있으므로, repo-local `.agents/skills`는 기본값으로 쓰지 않고 `install.sh`가 새로 만들지 않습니다.

## 설치

### 자동 설치 (권장)

```bash
git clone https://github.com/MyeongJong03/dding-skills.git ~/ctf-solver
cd ~/ctf-solver
bash install.sh          # macOS 기본값
bash install.sh windows  # Windows WSL2
```

기본 설치는 `config/deploy.sh` 실행, `~/CTF/CLAUDE.md` 생성, `~/CTF/AGENTS.md` 동기화, `ctf-personal` skill 설치, Docker 이미지 준비만 수행합니다.
Claude MCP 등록과 external skills 설치는 자동으로 실행하지 않습니다.

Optional:

```bash
bash install.sh --with-claude-mcp
bash install.sh --with-external-skills
bash install.sh --all
bash install.sh --help
```

### 수동 설치

#### 1. 클론

```bash
git clone https://github.com/MyeongJong03/dding-skills.git ~/ctf-solver
```

#### 2. Codex 설정 배포

macOS:
```bash
bash ~/ctf-solver/config/deploy.sh mac
```

Windows WSL2:
```bash
bash ~/ctf-solver/config/deploy.sh windows
```

#### 3. Claude Code MCP 등록 (optional/legacy)

Claude Code를 계속 쓰는 환경에서만 등록합니다.

macOS:
```bash
claude mcp add --scope user ctf_solver \
  -- <path-to-uv> run --with "mcp[cli]" --with requests --with httpx \
  mcp run $HOME/ctf-solver/server.py
```

Windows WSL2:
```bash
claude mcp add --scope user ctf_solver \
  -- <path-to-uv> run --with "mcp[cli]" --with requests --with httpx \
  mcp run $HOME/ctf-solver/server.py
```

Codex에서 MCP가 직접 붙지 않는 경우에도 같은 `server.py`와 `tools/*.py`를 CLI/Python helper로 사용할 수 있습니다.

#### 4. CTF Skills 설치 (optional external)

```bash
bash ~/ctf-solver/install.sh --with-external-skills
```

설치 위치는 `~/.agents/skills`입니다. `install.sh`는 skills CLI의 all-agent 설치를 사용하지 않고, `ljagiello/ctf-skills`를 임시 디렉터리에 clone한 뒤 expected external skill 11개만 global 위치에 copy합니다. `~/ctf-solver/.agents/skills`에만 설치하면 `~/CTF`에서 실행한 Codex가 skill을 보지 못할 수 있습니다.

#### 5. ReVa 설치 (리버싱 필요 시, optional)

```bash
claude plugin marketplace add cyberkaida/reverse-engineering-assistant
```

#### 6. Docker 이미지 빌드

```bash
docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest .
docker run --rm --platform linux/amd64 --network none ctf-pwn:latest bash -lc 'python3 -c "import pwn,z3,Crypto,gmpy2,sympy,requests,httpx; print(\"python-modules-ok\")"; gdb --version | head -1; pwninit --version; one_gadget --version; seccomp-tools --version; r2 -v | head -1'
```

Pwn/GDB runtime smoke validation은 local toy crash binary만 대상으로 Docker 안의 실제 `gdb` 흐름을 확인합니다.

```bash
python3 scripts/gdb_docker_smoke.py --json
CTF_RUN_DOCKER_GDB_TESTS=1 python3 -m pytest tests/test_gdb_docker_smoke.py -q
```

`ctf-pwn:latest`는 의도적으로 무거운 이미지입니다. `docker system prune -a`는 필요한 이미지까지 지울 수 있으므로 신중히 사용하고, 빌드 캐시 정리에는 `docker builder prune`이 더 안전합니다.

#### 7. 설정 파일 생성/동기화

```bash
bash ~/ctf-solver/config/deploy.sh mac      # macOS
bash ~/ctf-solver/config/deploy.sh windows  # Windows WSL2
```

이 단계가 `~/CTF/CLAUDE.md`를 실제 파일로 생성하고, `~/CTF/AGENTS.md`를 Codex용으로 동기화하며, `ctf-personal` skill 심볼릭 링크를 갱신합니다.

#### 8. 환경 설정

`~/CTF/CLAUDE.md`에서 환경에 맞게 경로 수정:
- `~/wordlists/rockyou.txt` — rockyou 워드리스트
- `~/RsaCtfTool/` — RSActfTool (또는 `pip install rsactftool`)
- SageMath 경로: `SAGE_PATH` 환경변수로 덮어쓰기 가능

## 환경 변수

| 변수 | 설명 | 기본값 |
|---|---|---|
| `SAGE_PATH` | SageMath 실행 파일 경로 | macOS 앱 번들 경로 |
| `CTF_WORK_ROOT` | 문제 작업 루트 | `~/CTF/work` |
| `CTF_LOCAL_RUN_ROOT` | private run log 루트 | `~/.ctf-solver/runs` |
| `CTF_LOCK_ROOT` | lifecycle/git/metrics lock 루트 | `~/.ctf-solver/locks` |
| `CTF_LEASE_ROOT` | remote resource lease 루트 | `~/.ctf-solver/leases` |
| `CTF_LEASE_HEARTBEAT_INTERVAL_SEC` | lease heartbeat 권장 주기 | `30` |
| `CTF_LEASE_STALE_AFTER_SEC` | heartbeat 중단 후 stale 판정 시간 | `180` |
| `CTF_QUEUE_ROOT` | challenge queue 루트 | `~/.ctf-solver/queue` |
| `CTF_WORKER_ROOT` | worker claim 루트 | `~/.ctf-solver/workers` |
| `CTF_SESSION_ROOT` | persistent session metadata 루트 | `~/.ctf-solver/sessions` |
| `CTF_SESSIOND_ROOT` | session daemon state 루트 | `~/.ctf-solver/sessiond` |
| `CTF_SESSIOND_HOST` | session daemon bind host | `127.0.0.1` |
| `CTF_SESSIOND_PORT` | session daemon bind port | `0` 자동 할당 |
| `CTF_GDB_ROOT` | GDB debug session metadata/log 루트 | `~/.ctf-solver/gdb` |
| `CTF_GDB_ARTIFACT_ROOT` | GDB core/memory artifact 루트 | `~/.ctf-solver/gdb-artifacts` |
| `CTF_BROWSER_ROOT` | browser action session/daemon metadata 루트 | `~/.ctf-solver/browser` |
| `CTF_BROWSER_ARTIFACT_ROOT` | browser action screenshot/artifact 루트 | `~/.ctf-solver/browser-artifacts` |
| `CTF_BROWSER_STATE_ROOT` | browser/session profile metadata 루트 | `~/.ctf-solver/browser-states` |
| `CTF_CALLBACK_ROOT` | callback listener metadata/hit log 루트 | `~/.ctf-solver/callbacks` |
| `CTF_CALLBACKD_ROOT` | callback daemon state 루트 | `~/.ctf-solver/callbackd` |
| `CTF_WEB_WORKFLOW_ROOT` | web exploit workflow metadata/evidence 루트 | `~/.ctf-solver/web-workflows` |
| `CTF_LIVE_SMOKE_ROOT` | manual live platform smoke 결과 루트 | `~/.ctf-solver/live-smoke` |
| `CTF_BENCHMARK_ROOT` | private benchmark pack 루트 | `~/.ctf-solver/benchmarks` |
| `CTF_BENCHMARK_RUN_ROOT` | private benchmark raw result 루트 | `~/.ctf-solver/benchmark-runs` |
| `CTF_PLATFORM_AUTOMATION_ROOT` | platform server/session scaffold state 루트 | `~/.ctf-solver/platforms` |
| `CTF_DOWNLOAD_ROOT` | downloaded private challenge file 루트 | `~/CTF/downloads` |
| `CTF_PLATFORM_CONFIG` | repo 밖 platform policy YAML | unset (`config/platforms.example.yaml` for schema/example) |
| `CTF_CTFD_COOKIE_FILE` | CTFd live discovery/download용 repo-external cookie file | unset |
| `CTF_CTFD_COOKIE_HEADER` | CTFd live discovery/download용 local-only cookie header | unset |
| `CTF_DREAMHACK_FIXTURE_ROOT` | Dreamhack private fixture root | `~/.ctf-solver/fixtures/dreamhack` |
| `CTF_DREAMHACK_SESSION_ID` | Dreamhack VM action용 local-only session value | unset |
| `CTF_DREAMHACK_CSRF_TOKEN` | Dreamhack VM action용 local-only CSRF value | unset |
| `CTF_SOLVED_WRITEUP_ROOT` | local-only writeup 루트 | `~/SolvedWriteUp` |
| `CTF_METRICS_MODE` | public metrics 업데이트 모드 | `public` |
| `CTF_AUTO_PUSH` | `1`이면 git sync에서 push 허용 | unset |
| `CTF_SOLVER_REPO_ROOT` | repo root override | script parent repo |

## Challenge lifecycle (P1-0.5)

Codex와 Claude를 동시에 쓰는 dual-agent setup에서도 문제 단위 lifecycle은 `challenge_id`와 `run_id`로 분리됩니다. 여러 터미널에서 동시에 finalize해도 challenge lock, metrics lock, git lock으로 직렬화합니다.

기본 흐름:

```bash
python3 scripts/challenge_init.py --platform dreamhack --event dreamhackWargame --challenge-name "Example" --category web
python3 scripts/challenge_finalize.py --run-dir <run-dir> --status solved --generate-writeup --cleanup --update-metrics --git-sync --no-push
CTF_AUTO_PUSH=1 python3 scripts/git_sync_metrics.py --push
```

문제 시작 시 `challenge_init.py`가 반환한 `run_dir`를 보존하고, 같은 터미널의 모든 후속 작업은 그 `run_id`에 묶습니다. 전역 current challenge는 사용하지 않습니다. 기존 workspace나 `run_dir`를 받은 경우에는 새 run을 만들지 않고 그 경로를 이어서 사용합니다.

다음 상태는 모두 finalize 대상입니다: `solved`, `abandoned`, `skipped`, `already_solved`, `timeout`, `budget_exhausted`, `manual_stop`. 다음 문제로 넘어가기 전 현재 run finalization이 성공해야 합니다.

Writeup은 `~/SolvedWriteUp` 또는 `CTF_SOLVED_WRITEUP_ROOT` 아래에만 생성됩니다. Exploit 파일을 넘기면 writeup directory에 복사하고 `writeup.md` 안에 전체 코드를 삽입합니다. Writeup, exploit code, flag, raw transcript, private run log는 GitHub 자동 push 대상이 아닙니다.

GitHub에 올릴 수 있는 것은 `metrics/summary.jsonl`과 `metrics/dashboard.md` 같은 public-safe aggregate metrics입니다. 기본 public metrics에는 challenge name도 넣지 않습니다. `challenge_finalize.py`는 같은 status로 재실행하면 no-op이고, 다른 status는 `--force` 없이는 거부합니다. `update_metrics.py`는 `run_id` 기준으로 duplicate append를 막고 `--replace`/`--force`에서만 기존 entry를 교체합니다. 자세한 정책은 [docs/lifecycle.md](docs/lifecycle.md)와 [docs/metrics.md](docs/metrics.md)를 봅니다.

Codex는 `~/CTF/AGENTS.md`, Claude는 `~/CTF/CLAUDE.md`를 읽으며 두 파일은 `config/deploy.sh`가 같은 lifecycle enforcement content로 동기화합니다.

## Solve verifier (P1-2)

Solved claim 전에는 가능한 경우 verifier를 먼저 실행합니다. 결과는 private run directory의 `verifier.json`에 저장되고, raw evidence를 보존해야 할 때만 `--save`로 `<run_dir>/logs/verifier-output.txt`에 둡니다.

```bash
python3 scripts/verify_run.py --run-dir <run-dir> --mode command --command "python3 exploit.py" --cwd <workspace> --flag-regex 'DH\{[^}]+\}' --local
python3 scripts/challenge_finalize.py --run-dir <run-dir> --status solved --require-verifier --generate-writeup --update-metrics
```

MCP tool `verify_run`도 command/session/manual mode를 지원합니다. Public metrics에는 verifier success/flag_found/target/attempts/duration summary만 들어가며, flag 원문, exploit code, raw output, private evidence path는 들어가지 않습니다. 자세한 내용은 [docs/verifier.md](docs/verifier.md)를 봅니다.

## Platform resource automation (P1-0.6)

여러 터미널/worker가 같은 대회 리소스를 공유할 때는 platform policy, queue, lease helper를 사용합니다. THCON처럼 한 세션에서 VM/server 1개만 가능한 플랫폼은 `max_active_leases: 1`로 표현하고, remote lease를 못 받은 worker는 idle하지 않고 local-capable 문제의 triage/analysis/exploit planning을 먼저 진행합니다. `local_exploit_ready=true` 문제는 remote capacity가 풀릴 때 우선순위를 받습니다.

P1-4 browser/platform scaffold는 로그인 세션 metadata 등록, mock/local discovery, download, server acquire/release/status, submission policy gate를 제공합니다. P1-6 browser action scaffold는 optional Playwright 기반 DOM 조작, local-only screenshot, console/network/cookie redaction, run_id 기반 session cleanup을 제공합니다. P1-10 live smoke framework는 실제 adapter 구현 전 수동 opt-in 검증을 제공하고, P1-12는 CTFd read-only live discovery 운영 runbook을 제공합니다. P1-13 CTFd live attachment download는 기본 no-download이며 `--live`와 `--allow-download`가 모두 있을 때만 동작합니다. P1-14 Dreamhack adapter scaffold는 fixture discovery/download와 명시적 `dreamhack_vm_control.py --live` VM action을 resource lease에 연결합니다. P1-15 offline E2E smoke는 fixture 기반으로 discovery부터 finalize/writeup/metrics/cleanup까지 전체 lifecycle을 검증합니다. 기본은 dry-run/no-network이고, `--live` 없이는 외부 CTF 사이트에 접속하지 않으며, smoke mode에서는 flag submit을 수행하지 않습니다. 자세한 내용은 [docs/browser-platform-automation.md](docs/browser-platform-automation.md), [docs/browser-actions.md](docs/browser-actions.md), [docs/live-smoke.md](docs/live-smoke.md), [docs/ctfd-live-smoke-runbook.md](docs/ctfd-live-smoke-runbook.md), [docs/dreamhack-adapter.md](docs/dreamhack-adapter.md), [docs/offline-e2e-smoke.md](docs/offline-e2e-smoke.md)를 봅니다.

P1-7 web callback listener는 XSS/admin bot/SSRF/CSP leak/CSS exfil 같은 Web CTF에서 loopback-only callback hit를 수집합니다. 기본 bind는 `127.0.0.1`이고, 외부 tunnel은 자동 실행하지 않습니다. 수동 tunnel base URL은 metadata로만 등록할 수 있습니다. Hit header/query/body preview는 bounded/redacted 처리되고, finalize/verifier/writeup/metrics에는 public-safe summary만 연결됩니다. 자세한 내용은 [docs/callback-listener.md](docs/callback-listener.md)를 봅니다.

### Browser Runtime Validation

Playwright is optional. On macOS Homebrew Python, direct
`python3 -m pip install playwright` can hit PEP 668
`externally-managed-environment`, so use uv first or a venv outside the repo.
Do not use `--break-system-packages` as the default path.

```bash
uv run --with playwright python -c "import playwright; print('ok')"
uv run --with playwright python -m playwright install chromium
uv run --with pytest --with playwright python -m pytest tests/test_browser_actions.py -q
python3 scripts/browser_playwright_check.py --use-uv --json
python3 scripts/doctor.py
```

Claude MCP browser tools need Playwright in the registered `ctf_solver` runtime.
If browser tools are required, add `--with playwright` to the uv MCP command.
Browser regression tests are local-only: data URLs, local HTML, or mock loopback
servers only. No live external CTF site tests are part of this scaffold.

Long-running remote 작업은 lease heartbeat를 남기고, worker crash나 터미널 종료로 stale lease가 생기면 dry-run 확인 후 reclaim합니다. Queue history는 여러 터미널에서 scheduler decision과 lease lifecycle을 추적하는 기준입니다.

Remote sharing이 안전하고 policy에서 허용된 경우에만 helper worker가 active remote challenge에 합류할 수 있습니다. Primary worker만 destructive action, submit, restart/release 권한을 가집니다. 자세한 운영 규칙은 [docs/platform-automation.md](docs/platform-automation.md)를 봅니다.

```bash
python3 scripts/platform_config_init.py --print-template
python3 scripts/queue_update.py --platform thcon --event THCON --challenge-id A --category web --state downloaded --local-capable true --remote-required true --local-exploit-ready false --confidence 0.4 --destructive-risk 0.1
python3 scripts/queue_next.py --platform thcon --event THCON --policy ~/.ctf-solver/platforms/thcon.yaml
python3 scripts/resource_acquire.py --platform thcon --event THCON --challenge-id A --run-id RUN_A --resource remote_server --mode primary --policy ~/.ctf-solver/platforms/thcon.yaml
python3 scripts/resource_heartbeat.py --lease-id <lease-id> --once
python3 scripts/resource_reclaim_stale.py --dry-run
python3 scripts/resource_reclaim_stale.py --apply
python3 scripts/queue_history.py --tail 20
python3 scripts/resource_release.py --run-id RUN_A --platform thcon --event THCON --all-for-run
python3 scripts/browser_state_init.py --platform thcon --event THCON --profile main --print-login-instructions
python3 scripts/platform_discover.py --platform thcon --event THCON --adapter mock --source fixtures/challenges.json --queue --json
python3 scripts/ctfd_live_smoke_runbook.py --platform ctfd --event local-fixture --base-url https://ctfd.example.invalid
python3 scripts/platform_live_smoke.py --platform ctfd --event local-fixture --adapter ctfd --mode discovery --base-url https://ctfd.example.invalid --json
python3 scripts/platform_discover.py --platform ctfd --event local-fixture --adapter ctfd --base-url https://ctfd.example.invalid --live --queue --json
python3 scripts/platform_live_smoke.py --platform ctfd --event local-fixture --adapter ctfd --mode download --base-url https://ctfd.example.invalid --challenge-id 1 --allow-download --json
python3 scripts/platform_download.py --platform ctfd --event local-fixture --adapter ctfd --base-url https://ctfd.example.invalid --external-id 1 --live --allow-download --json
python3 scripts/dreamhack_vm_control.py --challenge-id 1001 --run-id RUN_A --action start --confirm --live --session-id-file ~/.ctf-solver/auth/dreamhack-session.txt --csrf-token-file ~/.ctf-solver/auth/dreamhack-csrf.txt --json
python3 scripts/offline_e2e_smoke.py --platform ctfd --json
python3 scripts/offline_e2e_smoke.py --platform dreamhack --json
```

CTFd live discovery is read-only and opt-in: run the live smoke dry-run first,
then use `--live` only after approval. Use `--queue` only when queue
registration is explicitly intended. Cookie/header auth must come from a
local-only env source or browser profile metadata; raw cookies, tokens, storage
state, descriptions, API responses, and raw attachment URL queries are not
stored in repo metrics. CTFd live download also requires `--allow-download` and
stores files under `CTF_DOWNLOAD_ROOT` outside the repo. Queue state changes
only when `platform_download.py --queue` is explicit. The public-safe result
check is limited to counters such as `ctfd_live_discovered_count`,
`ctfd_live_downloaded_count`, and `ctfd_live_downloaded_bytes`.

Dreamhack VM actions are explicit live operations and use the `dreamhack`
platform adapter, not a separate MCP server name. `start`/`restart` acquire a
remote-server lease first, and the example policy limits Dreamhack to one active
VM per `platform_event` scope. Auth values can come from repo-external files or
local-only env vars, but they are never printed or stored. Metrics keep only
`dreamhack_vm_action_attempted`, `dreamhack_vm_action_success`, and
`dreamhack_vm_active_count`. Private Dreamhack fixtures default to
`~/.ctf-solver/fixtures/dreamhack` or `CTF_DREAMHACK_FIXTURE_ROOT`; only
synthetic dummy parser fixtures belong in `tests/fixtures/dreamhack/`.

Offline E2E smoke is fixture-only and creates temp roots for `HOME`, run
storage, writeups, queue, locks, downloads, and the public metrics repo. It
does not require live CTF URLs or Dreamhack auth/session/CSRF values. The JSON
summary is public-safe and reports only lifecycle booleans and counters.

## Queue worker runner (P1-3)

여러 터미널에서 자동화 scaffold를 돌릴 때는 worker가 queue item을 먼저 claim합니다. Active claim이 있는 문제는 다른 worker가 중복 작업하지 않고, helper mode가 가능한 경우에만 active remote challenge에 read-only helper로 합류합니다. Worker claim은 `CTF_WORKER_ROOT` 또는 `~/.ctf-solver/workers` 아래 local-only JSON으로 저장되고 heartbeat가 끊기면 stale reclaim 대상이 됩니다.

```bash
python3 scripts/worker_next.py --platform thcon --event THCON --worker-id w1 --require-verifier true
python3 scripts/worker_run_once.py --platform thcon --event THCON --worker-id w1 --auto-acquire-remote --auto-finalize --require-verifier --json
python3 scripts/worker_loop.py --platform thcon --event THCON --worker-id w1 --interval-sec 10
python3 scripts/worker_status.py --platform thcon --event THCON --show-claims --json
```

Worker는 Codex/Claude, browser automation, GDB session, exploit 실행을 직접 호출하지 않습니다. `worker_next.py`는 다음 action과 suggested command를 고르고, `worker_run_once.py`는 lease acquire/finalize처럼 public-safe한 orchestration step만 옵션으로 수행합니다. Solved candidate는 `--require-verifier`가 켜진 경우 successful verifier 없이는 finalize action으로 넘어가지 않습니다.

## Persistent sessions (P1-1)

Interactive nc menus, Python/Sage REPLs, shell state, Docker shell state, and long-running local helper processes can be kept alive through a loopback-only session daemon. The daemon stores local state under `~/.ctf-solver/sessiond`, session metadata under `~/.ctf-solver/sessions`, and does not write raw transcripts by default.

```bash
sid=$(python3 scripts/session_start.py shell --run-id "$RUN_ID")
python3 scripts/session_write.py "$sid" "echo hello"
python3 scripts/session_expect.py "$sid" hello --timeout-ms 1000
python3 scripts/session_close.py "$sid"
```

MCP tools mirror the CLI: `session_start`, `session_write`, `session_read`, `session_expect`, `session_close`, and `session_list`. `challenge_finalize.py` closes sessions for the run unless `--keep-sessions` is supplied. Details are in [docs/sessions.md](docs/sessions.md).

## 점검 및 공유 전 redaction

```bash
python3 -m pytest tests
python3 scripts/secret_scan.py --strict
python3 scripts/doctor.py
python3 scripts/redact_sensitive.py --self-test
python3 scripts/redact_sensitive.py audit-pack.txt > audit-pack.redacted.txt
```

Regression tests는 temp env roots를 사용하며 실제 HOME의 `~/.ctf-solver`, `~/SolvedWriteUp`, `~/.agents`, `~/.claude`, `~/.codex`를 건드리지 않습니다. lifecycle/resource/session 변경 후에는 `python3 -m pytest tests`와 `python3 scripts/secret_scan.py --strict`를 실행합니다.

audit pack이나 설정을 공유하기 전에는 API key뿐 아니라 email, account UUID, organization UUID, referral code, billing/subscription metadata도 redaction 대상입니다. `~/.claude.json`, `~/.codex/config.toml`, browser storage state, cookies, tokens 원문은 paste하거나 commit하지 않습니다.

## Benchmark and AI usage metrics (P2-0)

Benchmark/performance scaffolds measure whether automation changes actually
improve outcomes without running live CTFs or invoking AI providers.

```bash
python3 scripts/benchmark_init.py --benchmark-id demo-web-001 --platform dreamhack --event dreamhackWargame --category web --local-capable true --remote-required true --timeout-sec 1800
python3 scripts/benchmark_record_result.py --benchmark-id demo-web-001 --run-id RUN-DEMO-1 --status solved --attempt-index 1 --duration-sec 420 --time-to-flag-sec 390 --verifier-success true --verifier-flag-found true
python3 scripts/ai_usage_record.py --run-id RUN-DEMO-1 --provider codex --model gpt-example --input-tokens 12000 --output-tokens 2400 --cost-usd 0.42
python3 scripts/benchmark_report.py
python3 scripts/ai_usage_report.py
python3 scripts/performance_report.py
```

Public outputs stay under `metrics/` and contain only aggregate status,
timing, verifier, tool/session/browser/callback, cleanup, remote wait, token,
and cost counters. Private detailed AI usage stays under `CTF_AI_USAGE_ROOT`
or `~/.ctf-solver/ai-usage`.

Private benchmark packs for real solver evaluation live outside the repo under
`CTF_BENCHMARK_ROOT`; raw private run details live under
`CTF_BENCHMARK_RUN_ROOT`. Use `benchmark_pack_init.py` and
`benchmark_pack_validate.py` to manage the pack skeleton, then export
public-safe result JSONL with `benchmark_export_public.py` and compare
before/after snapshots with `benchmark_compare.py` into `metrics/comparisons`.
See [docs/benchmarking.md](docs/benchmarking.md),
[docs/private-benchmarks.md](docs/private-benchmarks.md), and
[docs/ai-usage-metrics.md](docs/ai-usage-metrics.md).

## Credits

- [ljagiello/ctf-skills](https://github.com/ljagiello/ctf-skills) (MIT) — CTF 카테고리별 플레이북 구조 참고
