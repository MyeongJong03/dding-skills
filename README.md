# dding-skills

CTF 문제 풀이를 위한 Codex-first, Claude-compatible AI 에이전트 세팅 모음입니다.
현재 주력 실행 환경은 Codex이며, Claude Code 설정은 optional/legacy compatibility로 유지합니다.

## 구성

```
dding-skills/
├── server.py              # MCP 서버 진입점
├── tools/                 # MCP 툴 15개
├── ctf_solver_core/       # lifecycle path/lock/schema helpers
├── scripts/               # doctor + lifecycle/finalization CLIs
├── metrics/               # public-safe metrics and dashboard
├── docs/                  # tools/lifecycle/metrics docs
├── Dockerfile.ctf         # CTF PWN/REV용 Docker 이미지
├── install.sh             # 자동 설치 스크립트
├── skills/
│   └── ctf-personal/      # 개인 CTF 풀이 패턴 (자동 학습으로 지속 업데이트)
└── config/
    ├── CLAUDE.base.md     # 공통 CTF workflow / rules
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
```

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

## 점검 및 공유 전 redaction

```bash
python3 scripts/doctor.py
python3 scripts/redact_sensitive.py --self-test
python3 scripts/redact_sensitive.py audit-pack.txt > audit-pack.redacted.txt
```

audit pack이나 설정을 공유하기 전에는 API key뿐 아니라 email, account UUID, organization UUID, referral code, billing/subscription metadata도 redaction 대상입니다.

## Credits

- [ljagiello/ctf-skills](https://github.com/ljagiello/ctf-skills) (MIT) — CTF 카테고리별 플레이북 구조 참고
