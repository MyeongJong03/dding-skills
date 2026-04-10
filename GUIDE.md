# CTF AI 풀이 환경

---

## 목차

1. 환경 개요
2. 파일 구조 이해
3. 시작 전 체크리스트
4. 기본 사용법 (Claude Code / Codex)
5. 카테고리별 어느 기기에서 풀어야 하는가
6. MCP 툴 목록 및 사용법
7. Skills 구조 및 로드 규칙
8. 풀이 후 업데이트 및 동기화
9. 상황별 대처법
10. 주의사항 및 제한사항
11. 효율적으로 사용하는 방법
12. 자주 묻는 질문
13. 동시 실행 주의사항
14. 저장공간 관리 (윈도우)

---

## 1. 환경 개요

### 전체 구조 한눈에 보기

```
사용자
  ├── 맥북 (Apple Silicon M5, macOS)
  │     ├── Claude Code (ctf 명령어)
  │     └── Codex CLI (codex 명령어)
  │           └── 둘 다 MCP 서버에 연결
  │                 ├── dreamhack_solver (15개 툴)
  │                 └── ReVa (Ghidra MCP, 60개 툴)
  │
  └── 윈도우 (WSL2 Ubuntu 24.04)
        ├── Claude Code (ctf 명령어)
        └── Codex CLI (codex 명령어)
              └── 둘 다 MCP 서버에 연결
                    ├── dreamhack_solver (15개 툴)
                    └── ReVa (Ghidra MCP, Windows 네이티브)
```

### 맥북 특징

- Docker: Rosetta x86 에뮬레이션 (GDB 느림)
- SageMath 10.8
- Ghidra 로컬 설치 (`ghidra` 명령어로 실행)
- one_gadget, seccomp-tools 없음 (Docker 안에 있음)
- 주력: WEB, CRYPTO, FORENSICS, MISC, OSINT

### 윈도우 특징

- Docker: x86 네이티브 (GDB 빠름)
- SageMath 10.7 (conda 환경)
- Ghidra Windows 네이티브 (`ghidra` 명령어로 실행)
- one_gadget, seccomp-tools 로컬 설치됨
- 32GB RAM, RTX 5060 GPU (hashcat 빠름)
- 주력: PWN, REV, MALWARE, 무거운 FORENSICS

---

## 2. 파일 구조 이해

### 레포 (dding-skills = ~/ctf-solver)

```
~/ctf-solver/
├── server.py              # MCP 서버 진입점
├── tools/                 # MCP 툴 15개
│   ├── binary_info.py
│   ├── docker_exec.py
│   ├── docker_pwn.py
│   ├── dreamhack_vm.py
│   └── ... (총 15개)
├── Dockerfile.ctf         # Docker 이미지 (pwntools, pwndbg, r2, seccomp-tools 등)
├── requirements.txt
├── skills/
│   └── ctf-personal/
│       └── SKILL.md       # 개인 풀이 패턴 (풀이마다 자동 학습)
└── config/
    ├── mac/
    │   └── CLAUDE.md      # 맥북용 Claude Code/Codex 설정
    └── windows/
        └── CLAUDE.md      # 윈도우용 Claude Code/Codex 설정
```

### 맥북 심링크 구조

```
~/CTF/CLAUDE.md            → ~/ctf-solver/config/mac/CLAUDE.md
~/CTF/AGENTS.md            → ~/CTF/CLAUDE.md
~/.codex/AGENTS.md         → ~/CTF/CLAUDE.md
~/.agents/skills/ctf-personal → ~/ctf-solver/skills/ctf-personal
~/.claude/skills/          → ~/.agents/skills/ 하위 심링크들
~/.codex/skills/           → ~/.agents/skills/ 하위 심링크들
```

### 윈도우 심링크 구조

```
~/CTF/CLAUDE.md            → ~/ctf-solver/config/windows/CLAUDE.md
~/CTF/AGENTS.md            → ~/CTF/CLAUDE.md
~/.codex/AGENTS.md         → ~/CTF/CLAUDE.md
~/.agents/skills/ctf-personal → ~/ctf-solver/skills/ctf-personal
~/.codex/skills/           → ~/.agents/skills/ 하위 심링크들
```

**핵심 개념**: 심링크 덕분에 레포에서 `git pull` 하나면 양쪽 모두 자동 반영됩니다.

---

## 3. 시작 전 체크리스트

### 맥북 체크리스트

```
□ 1. Docker Desktop 실행 (PWN/REV Docker 사용 시 필요)
□ 2. Ghidra 실행 (PWN/REV Ghidra 분석 필요 시)
     → 터미널에서: ghidra
□ 3. ctf 또는 codex 실행
```

### 윈도우 체크리스트

```
□ 1. Docker Desktop 실행 (항상 필요)
□ 2. update-reva 실행 (재부팅 후 필수! WSL2 IP가 바뀜)
     → 안 하면 ReVa MCP 연결 안 됨
□ 3. Ghidra 실행 (PWN/REV 시, Windows에서 실행됨)
     → 터미널에서: ghidra
□ 4. ctf 또는 codex 실행
```

### MCP 연결 상태 확인 방법

```bash
claude mcp list
# dreamhack_solver: ✓ Connected  → 정상
# ReVa: ✓ Connected              → Ghidra 켜져있을 때 정상
# ReVa: ✗ Failed                 → Ghidra 꺼져있으면 정상 (문제 없음)
```

---

## 4. 기본 사용법

### Claude Code로 문제 풀기

```bash
# 어디서든 실행 가능 (자동으로 ~/CTF로 이동)
ctf
```

실행하면:

1. 자동으로 `~/CTF` 디렉토리로 이동
2. Claude Code 실행
3. `CLAUDE.md` 자동 로드 (환경, MCP 툴, 워크플로우, 규칙)
4. `ctf-personal` skill 자동 로드

Claude Code 안에서 문제 주기:

```
PWN 문제 풀어줘. 바이너리: ~/CTF/문제폴더/binary
호스트: host.dreamhack.games, 포트: 12345
```

### Codex CLI로 문제 풀기

```bash
# 어디서든 실행 가능 (자동으로 ~/CTF로 이동)
codex
```

실행하면:

1. 자동으로 `~/CTF` 디렉토리로 이동
2. Codex 실행
3. `AGENTS.md` 자동 로드 (= CLAUDE.md와 동일 내용)
4. Skills 자동 로드

Codex 안에서 문제 주기:

```
PWN 문제 풀어줘. 바이너리: ~/CTF/문제폴더/binary
호스트: host.dreamhack.games, 포트: 12345
```

### Claude Code vs Codex 차이

| 항목 | Claude Code | Codex |
| --- | --- | --- |
| 모델 | Claude Sonnet | GPT-5.4 |
| 장기 실행 | 세션 끝까지 연속 실행 | 중간에 보고하며 멈출 수 있음 |
| MCP | dreamhack_solver + ReVa | 동일 |
| Skills | 동일 | 동일 |
| 권장 용도 | 복잡한 문제, 장시간 풀이 | 빠른 분석, 보조 |

---

## 5. 카테고리별 기기 선택

### 맥북 권장

| 카테고리 | 이유 |
| --- | --- |
| WEB | Docker 불필요, SageMath 10.8, 어디서나 OK |
| CRYPTO | SageMath 10.8, RSActfTool, 수학 연산 빠름 |
| FORENSICS (가벼운) | exiftool, binwalk, vol 로컬 있음 |
| MISC | 어디서나 OK |
| OSINT | 어디서나 OK |

### 윈도우 권장

| 카테고리 | 이유 |
| --- | --- |
| PWN | x86 네이티브 GDB (빠름), seccomp-tools/one_gadget 로컬 |
| REV | Ghidra+ReVa 연동 최적, 빠른 분석 |
| MALWARE | Docker 격리 + 32GB RAM |
| FORENSICS (큰 덤프) | 32GB RAM 유리 |
| hashcat | RTX 5060 GPU 가속 (맥 대비 10~100배) |

### 어느 기기든 OK

- WEB, CRYPTO, MISC, OSINT → 맥북 권장 (더 빠르고 편함)
- PWN, REV → 윈도우 강력 권장

---

## 6. MCP 툴 목록 및 사용법

Claude Code와 Codex 모두 동일한 MCP 툴을 사용합니다.

### dreamhack_solver 툴

| 툴 | 용도 | 주요 파라미터 |
| --- | --- | --- |
| `file_analysis` | 소스코드/디렉토리 구조 분석 | path |
| `binary_info` | file+strings+checksec 한번에 | binary_path |
| `docker_exec` | Docker에서 bash/코드 실행 | code, binary_path, timeout_seconds |
| `docker_pwn` | Docker에서 pwntools 익스플로잇 | pwntools_script, binary_path, host, port |
| `python_exec` | Python 스크립트 실행 | code |
| `sage_exec` | SageMath 연산 | code, timeout_seconds(기본 60초) |
| `netcat_interact` | nc 서버 연결 | host, port, input_data |
| `http_request` | 커스텀 HTTP 요청 | url, method, headers, data |
| `port_scan` | nmap 포트 스캔 | target, ports |
| `dns_lookup` | DNS 조회 | domain |
| `hash_crack` | 해시 자동식별+hashcat | hash_value |
| `cve_lookup` | CVE 정보+PoC | cve_id |
| `rsa_ctftool` | RSA 자동 공격 | publickey, cipherfile |
| `trivy` | 의존성 CVE 스캔 | path |
| `dreamhack_vm` | Dreamhack 서버 제어 | challenge_id, action, session_id, csrf_token |

### docker_exec/docker_pwn 주의사항

- `--cap-add=SYS_PTRACE --security-opt seccomp=unconfined` 자동 적용
- Linux x86-64 네이티브 환경 (Ubuntu 22.04)
- 맥북에서는 Rosetta 에뮬레이션으로 느릴 수 있음

### sage_exec 주의사항

- 기본 타임아웃 **60초**
- LLL, Coppersmith 등 무거운 연산은 반드시 `timeout_seconds=300` 이상으로 설정
- **python_exec에서 sage 임포트 불가** → 반드시 sage_exec 사용

### ReVa 툴 (Ghidra MCP)

Ghidra가 켜져있어야 사용 가능합니다.

주요 툴:

- `get-decompilation`: 함수 디컴파일
- `get-strings`: 바이너리 문자열
- `list-imports`: 임포트 함수 목록
- `get-xrefs`: 크로스 레퍼런스
- `get-call-graph`: 콜 그래프
- `get-data-flow`: 데이터 플로우 분석

---

## 7. Skills 구조 및 로드 규칙

### 자동 로드 규칙 (CLAUDE.md 기준)

```
항상 로드:
  - ctf-personal (개인 경험 패턴)

카테고리 판별 후 추가 로드:
  WEB:      ctf-web
  PWN:      ctf-pwn
            + Ghidra 켜져있으면 reva-ctf-pwn 추가
  REV:      ctf-reverse
            + Ghidra 켜져있으면 reva-ctf-rev, reva-binary-triage 추가
  CRYPTO:   ctf-crypto
            + Ghidra 필요 시 reva-ctf-crypto 추가
  FORENSICS: ctf-forensics
  MISC:     ctf-misc
  OSINT:    ctf-osint
  MALWARE:  ctf-malware

로드하지 않음:
  - solve-challenge (CLAUDE.md가 대체, user-invocable: false로 설정됨)
```

### Skills 종류

| Skill | 출처 | 역할 |
| --- | --- | --- |
| ctf-personal | dding-skills 레포 | 개인 경험 패턴, 자동 학습 |
| ctf-web/pwn/crypto 등 | ljagiello/ctf-skills | 카테고리별 기법 레퍼런스 |
| ctf-ai-ml | ljagiello/ctf-skills | AI/ML 공격 기법 |
| ctf-writeup | ljagiello/ctf-skills | 풀이 후 writeup 생성 |
| reva-* | ReVa (Ghidra) | Ghidra MCP 활용 패턴 |

---

## 8. 풀이 후 업데이트 및 동기화

### 자동 업데이트 (Claude Code)

플래그 획득 즉시 Claude Code가 자동으로:

1. 새 기법/패턴/CVE → 해당 skill 파일에 추가
2. ctf-personal → MCP 패턴, 플랫폼 특이사항 추가
3. 업데이트 내용 보고 (무엇을 어느 파일에 추가했는지)
4. 업데이트 없으면 "업데이트 없음" 명시

### 레포 동기화 (풀이 후 반드시)

**풀이한 기기에서:**

```bash
cd ~/ctf-solver
git add skills/ctf-personal/SKILL.md
git commit -m "Update ctf-personal: [추가 내용 요약]"
git push
# 토큰 필요 시: git remote set-url origin https://MyeongJong03:토큰@github.com/MyeongJong03/dding-skills.git
# push 후: git remote set-url origin https://github.com/MyeongJong03/dding-skills.git
```

**반대쪽 기기에서:**

```bash
cd ~/ctf-solver && git pull
# 심링크라 자동 반영됨
```

### CLAUDE.md 수정 시

맥북에서 수정:

```bash
cd ~/ctf-solver
git add config/mac/CLAUDE.md
git commit -m "Update mac CLAUDE.md: ..."
git push
```

윈도우에서 수정:

```bash
cd ~/ctf-solver
git add config/windows/CLAUDE.md
git commit -m "Update windows CLAUDE.md: ..."
git push
```

반대쪽에서 반영:

```bash
cd ~/ctf-solver && git pull
```

---

## 9. 상황별 대처법

### Ghidra 프로젝트 잠김 오류

```bash
# 맥북
rm -rf ~/Desktop/Security/CTF.rep
rm -f ~/Desktop/Security/CTF.gpr
ghidra
# → New Project → Non-Shared → ~/Desktop/Security → CTF
```

### ReVa 연결 안 될 때 (윈도우)

```bash
update-reva
# WSL2 재부팅 후 IP가 바뀌므로 반드시 실행
```

### Dreamhack 서버 크래시 시

```
dreamhack_vm 툴 사용:
- challenge_id: 문제 번호 (URL에서 확인)
- action: restart
- session_id: 브라우저 쿠키 sessionid 값
- csrf_token: 브라우저 쿠키 csrf_token 값
※ 쿠키 만료 주기 약 7일
```

### Docker 안 될 때

```bash
# Docker Desktop 실행 확인
docker --version  # 안 나오면 Docker Desktop 먼저 실행
```

### git push 인증 오류

```bash
# GitHub에서 새 토큰 발급
# Settings → Developer settings → Personal access tokens → Tokens (classic)
# repo 권한 체크 후 발급

git remote set-url origin https://MyeongJong03:새토큰@github.com/MyeongJong03/dding-skills.git
git push
git remote set-url origin https://github.com/MyeongJong03/dding-skills.git
# ⚠️ 토큰 절대 채팅에 붙여넣기 금지
```

### sage_exec 타임아웃 오류

```python
# timeout_seconds 늘리기
sage_exec(code="...", timeout_seconds=300)
```

### Codex가 중간에 멈출 때

CLAUDE.md에 Codex 전용 규칙이 있지만 그래도 멈추면:

```
계속 진행해. 멈추지 마.
```

또는 비대화형 모드 사용:

```bash
codex exec "PWN 문제 풀어줘. 바이너리: ~/CTF/문제폴더/binary"
```

### ctf-personal 업데이트가 반영 안 될 때

```bash
# claude로 실행했으면 CLAUDE.md를 안 읽은 것
# 반드시 ctf 명령어로 ~/CTF에서 실행해야 함
ctf
```

### WSL 저장공간 부족 시

**원인: WSL vhdx가 비대해지는 이유**

CTF 풀이 환경 특성상 vhdx가 빠르게 커집니다:

- Docker 컨테이너 실행 및 이미지 누적 (ctf-pwn:latest 등)
- Docker 빌드 캐시 누적 (`docker build` 반복 시)
- `/tmp` 임시 파일 쌓임 (exploit 스크립트, 바이너리 등)
- pip/apt 캐시 누적

**증상**

- C드라이브가 갑자기 꽉 참 (WSL vhdx는 한번 커지면 자동으로 줄지 않음)
- WSL I/O 에러 발생 (`No space left on device`)
- Codex/Claude Code가 툴 실행 중 갑자기 충돌 종료

**해결 방법**

1. Ubuntu 안에서 불필요한 파일 정리:

```bash
docker system prune -f
docker builder prune -f
sudo apt clean
rm -rf ~/.cache/pip
sudo fstrim -av   # 삭제된 블록을 WSL에 반환
```

2. WSL 완전 종료:

```bash
# Windows PowerShell에서
wsl --shutdown
```

3. PowerShell 관리자 권한에서 diskpart로 vhdx 압축:

```powershell
# PowerShell (관리자 권한으로 실행)
diskpart
```

```
DISKPART> select vdisk file="C:\Users\user\AppData\Local\wsl\{UUID}\ext4.vhdx"
DISKPART> attach vdisk readonly
DISKPART> compact vdisk
DISKPART> detach vdisk
DISKPART> exit
```

> vhdx 경로: `C:\Users\사용자명\AppData\Local\wsl\` 아래 UUID 폴더 안의 `ext4.vhdx`
> UUID는 `wsl --list --verbose` 또는 탐색기에서 직접 확인

**자동 관리: sparseVhd 설정**

`~/.wslconfig`에 다음을 추가하면 WSL이 vhdx를 sparse 모드로 관리해 자동 축소됩니다:

```ini
[wsl2]
sparseVhd=true
```

설정 후 `wsl --shutdown` 으로 재시작하면 적용됩니다.

**주기적 정리 (문제 5~10개마다 권장)**

```bash
docker system prune -f
docker builder prune -f
sudo fstrim -av
```

---

## 10. 주의사항 및 제한사항

### 절대 하면 안 되는 것

- **토큰을 채팅이나 터미널 결과에 붙여넣기 금지** → 노출 시 즉시 Revoke
- **MALWARE 문제에서 로컬 실행 금지** → 반드시 docker_exec으로 격리 실행
- **`claude` 명령어로 실행 금지** → CLAUDE.md가 로드 안 됨, 반드시 `ctf` 사용

### 맥북 제한사항

- one_gadget, seccomp-tools 로컬 없음 (Docker 안에 있음, docker_exec으로 사용)
- GDB가 x86 에뮬레이션이라 느림 → PWN은 윈도우에서
- hashcat GPU 가속 없음 (CPU만)
- SageMath는 `sage_exec` MCP로만 사용 가능 (python_exec에서 임포트 불가)

### 윈도우 제한사항

- 재부팅 후 반드시 `update-reva` 실행 (안 하면 ReVa 연결 안 됨)
- SageMath 10.7 (맥북은 10.8)
- Ghidra를 Windows에서 실행하므로 WSL2와 통신 필요

### Codex 제한사항

- 장시간 작업 시 중간에 보고하며 멈출 수 있음
- CLAUDE.md에 Codex 전용 규칙 추가했지만 완벽하지 않을 수 있음
- Claude Code보다 장기 연속 실행이 불안정

---

## 11. 효율적으로 사용하는 방법

### 문제 시작할 때

1. 문제 파일을 `~/CTF/문제이름/` 폴더에 넣기
2. `ctf` 실행
3. 문제 설명 + 파일 경로 + 서버 주소 한번에 주기

### 효율적인 프롬프트 작성

```
# 좋은 예시
PWN 문제야.
바이너리: ~/CTF/baby_pwn/binary
서버: host.dreamhack.games:12345
문제 설명: 간단한 BOF 문제입니다.
플래그 포맷: DH{...}

# 나쁜 예시 (정보 부족)
문제 풀어줘
```

### 병렬 실행 활용

Claude Code는 초기 분석 시 병렬로 툴을 실행합니다:

- binary_info + ReVa get-decompilation + ReVa get-strings 동시 실행
- 대기 시간 단축

### 맥북 + 윈도우 동시 활용

- 맥북: WEB/CRYPTO 문제 풀기
- 윈도우: PWN/REV 문제 풀기
- 동시에 다른 문제를 병렬로 진행 가능

### Claude Code 모델 전환

복잡도에 따라 모델을 전환해 토큰을 효율적으로 사용합니다:

```
/model opus    # 복잡한 문제 (PWN, 난해한 CRYPTO, 멀티스텝 REV)
/model sonnet  # 일반 문제 (기본값, WEB, MISC, FORENSICS)
```

- **Max 플랜**: Opus 4.6 1M 컨텍스트 자동 지원 (긴 소스코드, 큰 바이너리 분석 시 유리)
- Sonnet으로 시작해 막히면 Opus로 전환하는 것이 토큰 절약에 효과적

### 토큰 절약 팁

- **방향 확인 먼저**: 바로 익스플로잇 시도 전 "이 바이너리의 취약점이 뭔지 분석해줘"로 방향 확인
- **Codex 병행**: Claude Code 토큰 소진 중일 때 같은 문제를 Codex로 병행 분석
- **토큰 리셋 주기 활용**: Claude Code 토큰은 약 5시간 주기로 리셋 → 어렵다면 잠시 기다렸다가 새 세션에서 재시도
- 컨텍스트가 길어지면 `/clear`로 초기화 후 핵심만 다시 주기

### writeup 생성

풀이 완료 후:

```
이번 풀이 writeup 작성해줘
```

ctf-writeup skill이 자동으로 표준 형식의 writeup을 생성합니다.

---

## 12. 자주 묻는 질문

**Q: claude와 ctf 명령어의 차이가 뭔가요?**
A: `ctf`는 `cd ~/CTF && claude --dangerously-skip-permissions`의 alias입니다. `~/CTF`에서 실행해야 CLAUDE.md가 자동 로드되고 권한 요청 없이 동작합니다. 반드시 `ctf`를 사용하세요.

**Q: codex와 ctf 명령어의 차이가 뭔가요?**
A: `codex`는 `cd ~/CTF && command codex -a never -s danger-full-access`의 alias입니다. 마찬가지로 `~/CTF`에서 실행해 AGENTS.md를 로드하고 승인 없이 동작합니다.

**Q: Ghidra 없어도 PWN 풀 수 있나요?**
A: 가능합니다. CLAUDE.md에 폴백이 있어서 Ghidra 없으면 자동으로 `r2 -A` 또는 `objdump -d`로 분석합니다.

**Q: ctf-personal이 자동으로 업데이트 안 되면요?**
A: `ctf` 명령어로 실행했는지 확인하세요. `claude`로 실행하면 CLAUDE.md를 못 읽어 자동 업데이트 규칙을 모릅니다. 또는 풀이 후 직접 "이번 풀이에서 새로 얻은 것 최신화해줘"라고 물어보세요.

**Q: 양쪽 기기 동기화는 어떻게 하나요?**
A: 풀이한 기기에서 `git push`, 반대쪽에서 `git pull`. 심링크 구조라 자동 반영됩니다.

**Q: sage_exec와 python_exec 언제 쓰나요?**
A: SageMath 연산은 반드시 `sage_exec`. 일반 Python은 `python_exec`. python_exec에서 sage 임포트하면 에러납니다.

**Q: Docker 안에 없는 도구가 필요하면요?**
A: `python_exec`로 pip install 후 사용하거나, `docker_exec`에서 apt install 후 사용합니다.

**Q: 문제 풀다가 서버가 죽으면요?**
A: `dreamhack_vm` 툴로 restart. session_id와 csrf_token은 브라우저 쿠키에서 확인 (약 7일 유효).

---

## 13. 동시 실행 주의사항

Claude Code 또는 Codex 세션을 여러 개 열어 문제를 동시에 풀 수 있습니다. 단, 조합에 주의가 필요합니다.

### 최대 동시 실행 수

- **4문제 동시** 실행 가능 (Claude Code Max 플랜 기준)
- 단, 카테고리 조합을 잘못 선택하면 MCP 툴 경합이 발생합니다

### 절대 피해야 할 조합

| 조합 | 이유 |
| --- | --- |
| **PWN + REV** | 두 세션이 동시에 ReVa(Ghidra MCP) 사용 시 응답 지연/충돌 발생 |
| **CRYPTO + CRYPTO** | `sage_exec` 동시 요청 시 경합 발생, 타임아웃 급증 |
| **PWN + PWN** | Docker GDB 세션이 동시에 열리면 포트/ptrace 충돌 가능 |

### 권장 조합

```
WEB + MISC + CRYPTO + FORENSICS   ← 가장 안전한 조합
WEB + OSINT + MISC + CRYPTO
WEB + FORENSICS + MISC + OSINT
```

- ReVa를 쓰는 문제(PWN/REV)는 한 번에 하나만
- sage_exec를 무겁게 쓰는 CRYPTO는 한 세션만
- Docker GDB를 쓰는 PWN은 한 세션만

### 폴더 분리 필수

각 문제는 반드시 별도 폴더에 넣어야 합니다:

```bash
~/CTF/문제이름1/   # 세션 1
~/CTF/문제이름2/   # 세션 2
~/CTF/문제이름3/   # 세션 3
~/CTF/문제이름4/   # 세션 4
```

파일이 섞이면 Claude Code가 엉뚱한 바이너리를 분석할 수 있습니다.

### ctf-personal/SKILL.md 동시 수정 금지

여러 세션이 동시에 `ctf-personal/SKILL.md`를 수정하면 git 충돌이 발생합니다:

- 동시 풀이 중에는 각 세션이 **메모만** 해두고
- 모든 세션 종료 후 **한 번에** ctf-personal 업데이트
- 또는 한 세션씩 순서대로 업데이트 후 `git push/pull`

---

## 14. 저장공간 관리 (윈도우)

### WSL vhdx 자동 관리

`~/.wslconfig`에 `sparseVhd=true`를 설정하면 WSL이 vhdx를 sparse 파일로 관리해 삭제된 공간을 Windows에 자동으로 반환합니다.

**현재 적용된 `.wslconfig` 내용** (`C:\Users\사용자명\.wslconfig`):

```ini
[wsl2]
sparseVhd=true
memory=16GB        # WSL2 최대 메모리 (전체의 절반 권장)
processors=8       # 논리 코어 수
```

설정 변경 후 반드시 `wsl --shutdown` 으로 재시작해야 적용됩니다.

### 주기적 정리 명령어 (문제 5~10개마다)

```bash
# Docker 관련 정리 (가장 효과적)
docker system prune -f        # 중지된 컨테이너, 미사용 이미지, 네트워크 삭제
docker builder prune -f       # 빌드 캐시 삭제

# apt/pip 캐시 정리
sudo apt clean
sudo apt autoremove -y
rm -rf ~/.cache/pip

# /tmp 임시 파일 정리
rm -f /tmp/tmp* /tmp/exploit* /tmp/rop*

# 삭제된 블록 WSL에 반환 (sparseVhd 없을 때 필수)
sudo fstrim -av
```

### 저장공간 모니터링

```bash
# WSL 내부 디스크 사용량
df -h /

# Docker 사용량 상세
docker system df

# 큰 파일/폴더 찾기
du -sh ~/CTF/* | sort -rh | head -20
du -sh /var/lib/docker/
```

### C드라이브 여유공간 권장

- **50GB 이상** 여유공간 유지 권장
- C드라이브 10GB 미만 시 WSL I/O 에러 발생 가능
- Docker 이미지 하나당 약 2~5GB 차지 (ctf-pwn:latest 포함)

### 충돌 후 복구

Claude Code 또는 Codex가 저장공간 부족으로 갑자기 종료된 후:

```bash
# 1. 정리 먼저
docker system prune -f
docker builder prune -f
sudo fstrim -av

# 2. WSL 재시작
# Windows PowerShell에서:
# wsl --shutdown

# 3. 재진입 후 확인
df -h /   # 여유공간 확인
docker ps  # Docker 정상 동작 확인

# 4. 풀이 재시작
ctf
```

> **주의**: 충돌 후 Docker 컨테이너가 zombie 상태로 남아있을 수 있습니다.
> `docker ps -a`로 확인 후 `docker rm -f $(docker ps -aq)`로 정리하세요.
