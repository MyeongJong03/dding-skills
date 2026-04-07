# dding-skills

CTF 문제 풀이를 위한 AI 에이전트(Claude Code, Codex CLI) 세팅 모음입니다.

## 구성

    dding-skills/
    ├── server.py              # MCP 서버 진입점
    ├── tools/                 # MCP 툴 15개
    ├── Dockerfile.ctf         # CTF PWN/REV용 Docker 이미지
    ├── skills/
    │   └── ctf-personal/      # 개인 CTF 풀이 패턴 (자동 학습으로 지속 업데이트)
    └── config/
        ├── mac/CLAUDE.md      # macOS 환경 Claude Code 설정
        └── windows/CLAUDE.md  # Windows WSL2 환경 Claude Code 설정

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
- **ReVa Skills**: [cyberkaida/reverse-engineering-assistant](https://github.com/cyberkaida/reverse-engineering-assistant) — Ghidra MCP 연동 스킬
- **Ghidra**: [NationalSecurityAgency/ghidra](https://github.com/NationalSecurityAgency/ghidra) — 리버싱 프레임워크

## 설치

### 1. 클론

    git clone https://github.com/MyeongJong03/dding-skills.git ~/ctf-solver

### 2. Claude Code MCP 등록

macOS:

    claude mcp add --scope user ctf_solver \
      -- /Users/username/.local/bin/uv run --with "mcp[cli]" --with requests --with httpx \
      mcp run /Users/username/ctf-solver/server.py

Windows WSL2:

    claude mcp add --scope user ctf_solver \
      -- uv run --with "mcp[cli]" --with requests --with httpx \
      mcp run /home/username/ctf-solver/server.py

### 3. CTF Skills 설치

    npx skills install ljagiello/ctf-skills

### 4. Docker 이미지 빌드

    docker build --platform linux/amd64 -f Dockerfile.ctf -t ctf-pwn:latest .

### 5. CLAUDE.md 배치

    mkdir -p ~/CTF
    # macOS
    cp config/mac/CLAUDE.md ~/CTF/CLAUDE.md
    # Windows WSL2
    cp config/windows/CLAUDE.md ~/CTF/CLAUDE.md

### 6. ctf-personal 스킬 배치

    mkdir -p ~/.agents/skills/ctf-personal
    cp skills/ctf-personal/SKILL.md ~/.agents/skills/ctf-personal/SKILL.md

## Credits

- [ljagiello/ctf-skills](https://github.com/ljagiello/ctf-skills) (MIT) — CTF 카테고리별 플레이북 구조 참고
