# dding-skills

CTF 문제 풀이를 위한 AI 에이전트(Claude Code) 세팅 모음입니다.

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
    ├── mac/CLAUDE.md      # macOS 환경 Claude Code 설정
    └── windows/CLAUDE.md  # Windows WSL2 환경 Claude Code 설정
```

### 동작 구조

```
Claude Code
  │
  ├─ ~/CTF/CLAUDE.md  ──────────────────→  config/mac/CLAUDE.md  (심볼릭 링크)
  │      └─ 스킬 로드 지시
  │             ├─ ctf-personal  ─────→  skills/ctf-personal/  (심볼릭 링크)
  │             ├─ ctf-pwn 등    ─────→  외부: ljagiello/ctf-skills
  │             └─ reva-*        ─────→  외부: cyberkaida/reverse-engineering-assistant
  │
  └─ MCP 도구 호출
         └─ dreamhack_solver  ────────→  server.py → tools/*.py
```

`install.sh`가 `~/CTF/CLAUDE.md`와 `~/.agents/skills/ctf-personal/`을 저장소 파일로 심볼릭 링크하므로, 저장소를 업데이트하면 로컬에 즉시 반영됩니다.

## MCP 툴 목록

| 툴 | 설명 |
|---|---|
| file_analysis | 소스코드/디렉토리 구조 분석 |
| binary_info | ELF 바이너리 정보 (file + strings + checksec) |
| docker_exec | ctf-pwn Docker 환경에서 bash/코드 실행 |
| docker_pwn | ctf-pwn Docker 환경에서 pwntools 익스플로잇 실행 |
| python_exec | Python 스크립트 실행 |
| sage_exec | SageMath 수학 연산 |
| netcat_interact | nc 서버 연결 및 페이로드 전송 |
| http_request | 커스텀 HTTP 요청 |
| port_scan | nmap 포트/서비스 스캔 |
| dns_lookup | DNS 레코드 조회 및 서브도메인 열거 |
| hash_crack | 해시 자동 식별 + hashcat 크랙 |
| cve_lookup | CVE 상세 정보 + PoC 링크 조회 |
| rsa_ctftool | RSA 취약점 자동 공격 |
| trivy | 의존성 파일 CVE 스캔 |
| dreamhack_vm | Dreamhack 워게임 서버 제어 (start/stop/restart) |

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

#### 2. Claude Code MCP 등록

macOS:
```bash
claude mcp add --scope user ctf_solver \
  -- ~/.local/bin/uv run --with "mcp[cli]" --with requests --with httpx \
  mcp run ~/ctf-solver/server.py
```

Windows WSL2:
```bash
claude mcp add --scope user ctf_solver \
  -- uv run --with "mcp[cli]" --with requests --with httpx \
  mcp run ~/ctf-solver/server.py
```

#### 3. CTF Skills 설치

```bash
npx skills install ljagiello/ctf-skills
```

#### 4. ReVa 설치 (리버싱 필요 시)

```bash
claude plugin marketplace add cyberkaida/reverse-engineering-assistant
```

#### 5. Docker 이미지 빌드

```bash
docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest .
```

#### 6. 심볼릭 링크 설정

```bash
# CLAUDE.md
mkdir -p ~/CTF
ln -sf ~/ctf-solver/config/mac/CLAUDE.md ~/CTF/CLAUDE.md

# ctf-personal 스킬
mkdir -p ~/.agents/skills
ln -sf ~/ctf-solver/skills/ctf-personal ~/.agents/skills/ctf-personal
```

#### 7. 환경 설정

`~/CTF/CLAUDE.md`에서 환경에 맞게 경로 수정:
- `~/wordlists/rockyou.txt` — rockyou 워드리스트
- `~/RsaCtfTool/` — RSActfTool (또는 `pip install rsactftool`)
- SageMath 경로: `SAGE_PATH` 환경변수로 덮어쓰기 가능

## 환경 변수

| 변수 | 설명 | 기본값 |
|---|---|---|
| `SAGE_PATH` | SageMath 실행 파일 경로 | macOS 앱 번들 경로 |

## Credits

- [ljagiello/ctf-skills](https://github.com/ljagiello/ctf-skills) (MIT) — CTF 카테고리별 플레이북 구조 참고
