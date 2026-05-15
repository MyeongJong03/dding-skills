# CTF Solver Guide

이 문서는 `~/ctf-solver`를 나중에 다시 봐도 바로 운용할 수 있게 정리한
상세 사용 가이드입니다.

빠른 시작만 필요하면 [README.md](README.md)를 먼저 보고, 실제 문제 풀이
중에는 [docs/operator-mode.md](docs/operator-mode.md)를 runbook으로 봅니다.

## 1. 현재 기준

현재 주력 환경은 MacBook + Codex입니다.

- 작업 디렉터리: `~/CTF`
- repo: `~/ctf-solver`
- primary agent: Codex
- optional/legacy compatibility: Claude Code
- canonical MCP server name: `ctf_solver`
- ReVa: Ghidra가 실행 중일 때만 연결
- shortcuts: `ctf-status`, `ctf-check`, `ctf-regression`

Windows/WSL2는 future phase입니다. 문서와 config skeleton은 유지하지만, 현재
실전 기준은 MacBook에서 검증된 흐름입니다.

## 2. 문서 역할

문서마다 담당하는 깊이가 다릅니다.

- `README.md`: 처음 보는 사람을 위한 짧은 landing page
- `GUIDE.md`: 설치, 구조, 운영, 플랫폼, metrics까지 담는 상세 매뉴얼
- `docs/operator-mode.md`: 실제 문제 풀이 중 보는 단계형 runbook
- `docs/regression.md`: `ctf-status`, `ctf-check`, `ctf-regression` 설명서

빠른 시작 명령은 README에만 짧게 두고, 이 문서는 각 기능의 배경과 세부
운영 기준을 설명합니다.

## 3. 레포 구조

```text
~/ctf-solver/
├── server.py
├── tools/
├── ctf_solver_core/
├── scripts/
├── docs/
├── metrics/
├── skills/ctf-personal/
├── config/
├── README.md
└── GUIDE.md
```

주요 디렉터리 역할:

- `server.py`: MCP server entrypoint
- `tools/`: MCP tool 구현
- `ctf_solver_core/`: lifecycle, path, lock, session, browser, callback, platform 공통 코드
- `scripts/`: operator CLI, lifecycle, verifier, queue, regression, doctor
- `docs/`: 기능별 runbook과 정책 문서
- `metrics/`: public-safe aggregate metrics
- `skills/ctf-personal/`: 개인 풀이 패턴과 platform notes
- `config/`: generated instructions와 platform policy example

중요 문서:

- `README.md`: 짧은 시작 문서
- `GUIDE.md`: 이 상세 문서
- `docs/operator-mode.md`: 실제 풀이 중 보는 one-runbook
- `docs/regression.md`: 상태 공유와 검증 명령
- `docs/lifecycle.md`: `challenge_init.py` / `challenge_finalize.py` 정책
- `docs/platform-automation.md`: queue, worker, lease 정책
- `docs/dreamhack-adapter.md`: Dreamhack adapter
- `docs/ctfd-adapter.md`: CTFd adapter
- `docs/ctfd-live-smoke-runbook.md`: CTFd live smoke checklist
- `docs/tools.md`: MCP tool signature 기준 문서

## 4. generated instructions

Codex와 Claude Code compatibility는 같은 생성물을 공유합니다.

```text
config/{mac|windows}/env.md
      +
config/CLAUDE.base.md
      ↓
~/CTF/CLAUDE.md
      ↓
~/CTF/AGENTS.md
```

MacBook에서 다시 배포:

```bash
cd ~/ctf-solver
bash config/deploy.sh mac
```

중요한 점:

- `~/CTF/CLAUDE.md`는 generated file입니다.
- `~/CTF/AGENTS.md`는 Codex가 읽는 파일입니다.
- `config/CLAUDE.base.md`나 `config/mac/env.md`를 바꾸면 deploy를 다시 실행합니다.
- `ctf-personal`은 symlink라 repo pull만으로 내용이 반영됩니다.

## 5. 처음 설치와 매일 사용

### 처음 설치

```bash
git clone https://github.com/MyeongJong03/dding-skills.git ~/ctf-solver
cd ~/ctf-solver
bash install.sh
bash config/deploy.sh mac
python3 scripts/install_shortcuts.py --dry-run
python3 scripts/install_shortcuts.py
ctf-status
```

Optional:

```bash
bash install.sh --with-external-skills
bash install.sh --with-claude-mcp
bash install.sh --all
```

### 이미 설치된 환경

평소에는 설치 명령을 다시 돌리지 않습니다.

```bash
cd ~/CTF
ctf-status
codex
```

repo가 이동했거나 shortcut wrapper가 stale해졌다면 다시 설치합니다.

```bash
cd ~/ctf-solver
python3 scripts/install_shortcuts.py --dry-run
python3 scripts/install_shortcuts.py
```

## 6. 매일 쓰는 명령

### `ctf-status`

빠른 setup/status 확인:

```bash
ctf-status
```

fallback:

```bash
cd ~/ctf-solver
python3 scripts/status_summary.py
```

확인하는 것:

- git 상태
- Docker optional 상태
- MCP registered name summary
- `mcp_raw_consistency`
- docs/tools drift
- redaction check
- repo raw grep
- doctor 요약

### `ctf-check`

빠른 local regression:

```bash
ctf-check
```

fallback:

```bash
cd ~/ctf-solver
python3 scripts/regression_check.py --quick
```

### `ctf-regression`

handoff, release-like change, commit 전 full regression:

```bash
ctf-regression
```

fallback:

```bash
cd ~/ctf-solver
python3 scripts/regression_check.py
```

자세한 marker 설명은 [docs/regression.md](docs/regression.md)를 봅니다.

## 7. 실제 운영 순서

새 문제 하나를 처리하는 표준 순서입니다.

### 1. `ctf-status`

```bash
cd ~/CTF
ctf-status
```

상태가 깨끗하면 Codex를 실행합니다.

```bash
codex
```

### 2. 문제 선택

문제 이름, 카테고리, 파일 경로, 원격 endpoint를 한 번에 전달합니다.

예시:

```text
WEB 문제야.
workspace: ~/CTF/example-web
server: https://example.invalid
flag format: DH{...}
```

### 3. `challenge_init`

새 run을 만듭니다.

```bash
cd ~/ctf-solver
python3 scripts/challenge_init.py \
  --platform <platform> \
  --event <event> \
  --challenge-name "<name>" \
  --category <category>
```

반환되는 `challenge_id`, `run_id`, `run_dir`를 보존합니다. 기존 `run_dir`를
받은 경우에는 새 run을 만들지 않고 이어서 사용합니다.

### 4. 분석과 보조 세션

풀이 중 생성되는 session, browser, callback, GDB 작업은 같은 `run_id`에 묶습니다.

Persistent session:

```bash
python3 scripts/session_start.py \
  shell \
  --run-id <run-id> \
  --cwd <workspace>
```

Browser action:

```bash
uv run --with playwright python scripts/browser_start.py \
  --run-id <run-id>
```

Callback listener:

```bash
python3 scripts/callback_start.py \
  --run-id <run-id> \
  --json
```

Local GDB session:

```bash
python3 scripts/gdb_start.py \
  --run-id <run-id> \
  --challenge-id <challenge-id> \
  --binary <local-binary> \
  --mode docker \
  --json
```

GDB는 local challenge binary만 대상으로 사용합니다. live remote service에
attach하지 않습니다.

### 5. `verify_run`

solved라고 주장하기 전에 가능한 경우 verifier를 실행합니다.

```bash
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode command \
  --command "<solve-command>" \
  --cwd <workspace> \
  --flag-regex '<flag-regex>' \
  --local
```

다른 terminal evidence만 있는 경우 manual mode를 씁니다.

```bash
python3 scripts/verify_run.py \
  --run-dir <run-dir> \
  --mode manual \
  --evidence-text "<redacted-evidence-summary>" \
  --success-regex "<success-marker>" \
  --remote
```

Verifier raw output은 private `run_dir` 아래에만 둡니다.

### 6. `challenge_finalize`

Solved path:

```bash
python3 scripts/challenge_finalize.py \
  --run-dir <run-dir> \
  --status solved \
  --require-verifier \
  --generate-writeup \
  --cleanup \
  --update-metrics
```

Manual stop path:

```bash
python3 scripts/challenge_finalize.py \
  --run-dir <run-dir> \
  --status manual_stop \
  --generate-writeup \
  --cleanup \
  --update-metrics
```

finalize 대상 상태:

- `solved`
- `abandoned`
- `skipped`
- `already_solved`
- `timeout`
- `budget_exhausted`
- `manual_stop`

### 7. `ctf-check`

문서, metrics, cleanup 상태를 빠르게 확인합니다.

```bash
ctf-check
```

## 8. 여러 터미널 운용 예시

여러 terminal/agent가 동시에 움직일 때는 queue claim과 resource lease를 기준으로
충돌을 막습니다.

### Queue 등록

```bash
python3 scripts/queue_update.py \
  --platform <platform> \
  --event <event> \
  --challenge-id <challenge-id> \
  --category <category> \
  --state downloaded \
  --local-capable true \
  --remote-required false \
  --local-exploit-ready false \
  --confidence 0.2 \
  --destructive-risk 0.0
```

### Worker claim

```bash
python3 scripts/worker_next.py \
  --platform <platform> \
  --event <event> \
  --worker-id <worker-id> \
  --require-verifier true
```

`worker_next.py`는 다음 action을 제안합니다. Codex, exploit, browser, GDB를
자동 실행하지 않습니다.

### Resource lease

remote server나 VM이 한 번에 하나만 가능한 플랫폼에서는 lease를 잡습니다.

```bash
python3 scripts/resource_acquire.py \
  --platform <platform> \
  --event <event> \
  --challenge-id <challenge-id> \
  --run-id <run-id> \
  --resource remote_server \
  --mode primary \
  --policy <policy.yaml>
```

긴 remote 작업은 heartbeat를 남깁니다.

```bash
python3 scripts/resource_heartbeat.py \
  --lease-id <lease-id> \
  --once
```

stale reclaim은 dry-run부터 확인합니다.

```bash
python3 scripts/resource_reclaim_stale.py --dry-run
```

### finalize-before-next

다음 문제로 넘어가기 전 반드시 현재 `run_dir` finalization이 성공해야 합니다.
이 규칙은 solved뿐 아니라 skipped, abandoned, timeout, manual_stop에도 적용됩니다.

## 9. Dreamhack 사용법

Dreamhack은 platform adapter입니다. canonical MCP 이름은 계속 `ctf_solver`입니다.
`dreamhack_solver`를 active MCP 이름으로 등록하지 않습니다.

Dreamhack VM action은 explicit live operation입니다.

```bash
python3 scripts/dreamhack_vm_control.py \
  --challenge-id <dreamhack-id> \
  --run-id <run-id> \
  --action status \
  --live \
  --session-id-file <repo-external-session-file> \
  --csrf-token-file <repo-external-csrf-file> \
  --json
```

start/restart처럼 상태를 바꾸는 action은 confirm이 필요합니다.

```bash
python3 scripts/dreamhack_vm_control.py \
  --challenge-id <dreamhack-id> \
  --run-id <run-id> \
  --action start \
  --confirm \
  --live \
  --session-id-file <repo-external-session-file> \
  --csrf-token-file <repo-external-csrf-file> \
  --json
```

규칙:

- auth 값은 repo 밖 file/env에서만 읽습니다.
- session, CSRF, cookie 원문을 출력하지 않습니다.
- private VM URL, raw platform response를 repo에 저장하지 않습니다.
- Dreamhack fixture는 local-only root를 사용합니다.
- repo fixture는 synthetic dummy parser fixture만 허용합니다.

MCP `dreamhack_vm` tool은 fallback입니다. 기본 운영은 policy/lease-aware
`scripts/dreamhack_vm_control.py`를 우선합니다.

## 10. CTFd 사용법

CTFd live discovery/download는 실제 CTFd URL이 있을 때만 실행합니다. 기본
regression과 dry-run은 no-network입니다.

No-network command generator:

```bash
python3 scripts/ctfd_live_smoke_runbook.py \
  --platform ctfd \
  --event <event> \
  --base-url https://ctfd.example.invalid
```

Read-only discovery smoke:

```bash
python3 scripts/platform_live_smoke.py \
  --platform ctfd \
  --event <event> \
  --adapter ctfd \
  --mode discovery \
  --base-url https://ctfd.example.invalid \
  --json
```

Live discovery:

```bash
python3 scripts/platform_discover.py \
  --platform ctfd \
  --event <event> \
  --adapter ctfd \
  --base-url https://ctfd.example.invalid \
  --live \
  --queue \
  --json
```

Live attachment download requires both `--live` and `--allow-download`.

```bash
python3 scripts/platform_download.py \
  --platform ctfd \
  --event <event> \
  --adapter ctfd \
  --base-url https://ctfd.example.invalid \
  --external-id <external-id> \
  --live \
  --allow-download \
  --queue \
  --json
```

규칙:

- discovery는 `/api/v1/challenges` 계열 read-only만 사용합니다.
- download는 `--allow-download`가 없으면 수행하지 않습니다.
- queue 등록은 `--queue`가 있을 때만 합니다.
- auth는 local-only env/file 또는 browser profile metadata에서만 가져옵니다.
- raw cookies, bearer headers, platform responses, attachment URL query를 출력하지 않습니다.

## 11. MCP와 tool 문서

현재 canonical MCP server name:

```text
ctf_solver
```

Legacy name:

```text
dreamhack_solver
```

legacy 이름은 active config/live MCP에 없어야 합니다. repo 안에서는 detector,
migration guide, test fixture 때문에 문자열이 남을 수 있습니다.

Tool signature 기준 문서:

```bash
python3 scripts/dump_mcp_tools.py --check
```

필요할 때만 재생성:

```bash
python3 scripts/dump_mcp_tools.py --write docs/tools.md
```

README/GUIDE에는 긴 schema를 중복하지 않습니다.

## 12. 상태 공유 방식

사용자는 명령 전체와 결과 전체를 붙여도 됩니다. 받는 쪽은 marker 기준으로
상태를 판단합니다.

Status marker:

```text
===== CTF_SOLVER_STATUS_BEGIN =====
...
===== CTF_SOLVER_STATUS_END =====
```

Regression marker:

```text
===== CTF_SOLVER_REGRESSION_BEGIN =====
...
===== CTF_SOLVER_REGRESSION_END =====
```

권장 공유:

```bash
ctf-status
```

또는:

```bash
ctf-check
```

붙이면 안 되는 것:

- raw `~/.claude.json`
- raw `~/.codex/config.toml`
- cookies, tokens, bearer headers
- browser storage state contents
- platform raw responses
- flags
- exploit code
- private run logs

## 13. Secret과 redaction

safe command pack은 raw secret을 출력하지 않도록 만들어져 있습니다. 그래도 repo
변경 전에는 strict scan을 돌립니다.

```bash
python3 scripts/secret_scan.py \
  --strict \
  --include-untracked
```

Redaction self-test:

```bash
python3 scripts/redact_sensitive.py --self-test
```

Audit pack을 직접 만들었다면 redaction 후 공유합니다.

```bash
python3 scripts/redact_sensitive.py \
  audit-pack.txt \
  > audit-pack.redacted.txt
```

## 14. Skills

기본 personal skill:

```text
skills/ctf-personal/
├── SKILL.md
├── war-stories.md
└── platform-notes.md
```

사용 기준:

- `SKILL.md`: 여러 문제에 재사용되는 범용 패턴
- `war-stories.md`: 특정 문제에서 얻은 특수 사례
- `platform-notes.md`: Dreamhack, CTFd 등 플랫폼 특이사항

External category skills는 optional입니다.

```bash
cd ~/ctf-solver
bash install.sh --with-external-skills
```

Codex를 `~/CTF`에서 실행하므로 external skills는 global 위치인
`~/.agents/skills`가 기본입니다.

## 15. Docker, PWN, GDB

Docker image:

```bash
cd ~/ctf-solver
docker build \
  --platform linux/amd64 \
  -f Dockerfile.ctf \
  -t ctf-pwn:latest \
  .
```

GDB smoke:

```bash
python3 scripts/gdb_docker_smoke.py --json
```

MacBook 주의:

- Docker GDB는 linux/amd64 emulation이라 느릴 수 있습니다.
- pwn/GDB task가 아니면 Docker image missing은 status에서 info로만 봅니다.
- live remote service에 GDB attach하지 않습니다.

## 16. Browser와 callback

Playwright는 optional입니다. macOS Homebrew Python에서 global pip install이 막힐
수 있으므로 uv 또는 repo 밖 venv를 우선합니다.

```bash
uv run --with playwright python -c "import playwright; print('ok')"
uv run --with playwright python -m playwright install chromium
python3 scripts/browser_playwright_check.py --use-uv --json
```

Browser session은 `run_id`에 묶고, artifact는 repo 밖 local-only root에 둡니다.

Callback listener는 XSS, admin bot, SSRF, CSP leak, blind hit 확인에 사용합니다.
기본 bind는 `127.0.0.1`입니다. 외부 tunnel은 자동 시작하지 않습니다.

```bash
python3 scripts/callback_start.py \
  --run-id <run-id> \
  --json

python3 scripts/callback_wait.py \
  --listener-id <listener-id> \
  --timeout-sec 30 \
  --json
```

callback hit는 bounded/redacted summary로만 확인합니다.

## 17. Metrics와 writeup

Writeup:

- `~/SolvedWriteUp` 또는 `CTF_SOLVED_WRITEUP_ROOT` 아래 local-only
- exploit file을 넘기면 writeup directory에 복사하고 본문에 포함
- GitHub 자동 push 대상 아님

Metrics:

- `metrics/` 아래 public-safe aggregate만 commit 가능
- 기본 public metrics에는 flag, exploit code, raw transcript, private path,
  private URL이 들어가지 않음
- `run_id` 기준 duplicate append를 방지

## 18. Windows/WSL2 future phase

Windows/WSL2 문서는 유지하지만 현재 실전 기준은 MacBook입니다.

future phase로 남아 있는 것:

- WSL2 shortcut 운영 안정화
- Windows native Ghidra/ReVa 연결 runbook 최신화
- GPU hashcat 중심 workflow 정리
- Windows live platform smoke 검증

Windows에서 repo를 쓴다면 Python fallback command를 직접 사용하고, shortcut은
WSL shell PATH를 검토한 뒤 설치합니다.

```bash
python3 scripts/status_summary.py
python3 scripts/regression_check.py --quick
```

## 19. 문제 해결

### shortcut이 없거나 repo를 옮긴 경우

```bash
cd ~/ctf-solver
python3 scripts/install_shortcuts.py --dry-run
python3 scripts/install_shortcuts.py
```

### ReVa가 연결되지 않는 경우

Ghidra가 켜져 있을 때만 ReVa가 연결됩니다. PWN/REV에서 ReVa가 필요하면 Ghidra를
먼저 실행합니다. ReVa가 꺼져 있어도 Web/Crypto/Misc 운영 실패는 아닙니다.

### Docker image가 없는 경우

`ctf-pwn:latest` missing은 pwn/GDB task가 아니면 optional info입니다.

```bash
docker build \
  --platform linux/amd64 \
  -f Dockerfile.ctf \
  -t ctf-pwn:latest \
  .
```

### `mcp_raw_consistency`가 실패하는 경우

`ctf_solver`가 raw config와 parsed JSON 양쪽에서 같은 상태인지 확인합니다.
`dreamhack_solver`가 active config에 남아 있으면 migration cleanup이 필요합니다.
raw config 본문은 붙여넣지 말고 marker summary만 공유합니다.

### Dreamhack VM이 꼬인 경우

status부터 확인합니다.

```bash
python3 scripts/dreamhack_vm_control.py \
  --challenge-id <dreamhack-id> \
  --run-id <run-id> \
  --action status \
  --live \
  --session-id-file <repo-external-session-file> \
  --csrf-token-file <repo-external-csrf-file> \
  --json
```

restart는 confirm과 lease 정책을 확인한 뒤 실행합니다.

## 20. 변경 후 검증

문서나 operator workflow를 바꾼 뒤 권장 순서:

```bash
ctf-status
ctf-check
python3 -m pytest tests
python3 scripts/secret_scan.py --strict --include-untracked
python3 scripts/doctor.py
python3 scripts/dump_mcp_tools.py --check
python3 scripts/redact_sensitive.py --self-test
python3 scripts/update_metrics.py --check
python3 -m compileall tools server.py scripts ctf_solver_core
git diff --check
```

큰 handoff나 commit 직전에는 `ctf-regression`도 실행합니다.
