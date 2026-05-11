# dding-skills

CTF 문제 풀이를 위한 Codex-first, Claude-compatible AI 에이전트 세팅 모음입니다.
현재 주력 실행 환경은 Codex이며, Claude Code 설정은 optional/legacy compatibility로 유지합니다.

## 구성

```
dding-skills/
├── server.py              # MCP 서버 진입점
├── tools/                 # MCP 툴 15개
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
- Global config files are not modified by this repo patch.

Legacy Claude Code users only:

    claude mcp remove dreamhack_solver
    claude mcp add ctf_solver -- <path-to-uv> run --with "mcp[cli]" --with requests --with httpx mcp run <path-to-repo>/server.py

## 외부 의존성

별도로 설치 필요한 것들입니다.

- **CTF Skills**: [ljagiello/ctf-skills](https://github.com/ljagiello/ctf-skills) — 카테고리별 풀이 플레이북
- **ReVa**: [cyberkaida/reverse-engineering-assistant](https://github.com/cyberkaida/reverse-engineering-assistant) — Ghidra MCP 연동 스킬
- **Ghidra**: 리버싱 프레임워크 (ReVa 사용 시)

## 설치

### 자동 설치 (권장)

```bash
git clone https://github.com/MyeongJong03/dding-skills.git ~/ctf-solver
cd ~/ctf-solver
bash install.sh mac      # macOS
bash install.sh windows  # Windows WSL2
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

#### 4. CTF Skills 설치

```bash
npx skills install ljagiello/ctf-skills
```

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

## 점검 및 공유 전 redaction

```bash
python3 scripts/doctor.py
python3 scripts/redact_sensitive.py --self-test
python3 scripts/redact_sensitive.py audit-pack.txt > audit-pack.redacted.txt
```

audit pack이나 설정을 공유하기 전에는 API key뿐 아니라 email, account UUID, organization UUID, referral code, billing/subscription metadata도 redaction 대상입니다.

## Credits

- [ljagiello/ctf-skills](https://github.com/ljagiello/ctf-skills) (MIT) — CTF 카테고리별 플레이북 구조 참고
