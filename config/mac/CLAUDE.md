# CTF 풀이 환경

## Role
CTF 문제 풀이 보조. 불필요한 설명 최소화, 익스플로잇 코드와 플래그 획득에 집중.

## 환경 정보 (macOS, Apple Silicon)
- Python: /opt/homebrew/bin/python3
- SageMath: /usr/local/bin/sage
- Docker image: ctf-pwn:latest (pwntools 4.15.0, pwninit 3.3.1, linux/amd64)
- rockyou: ~/wordlists/rockyou.txt
- RSActfTool: ~/RsaCtfTool/src/RsaCtfTool/main.py
- Ghidra: /opt/homebrew/Cellar/ghidra/12.0.4/bin/ghidraRun (ReVa MCP로 연결)

## MCP 서버
- **ReVa (Ghidra MCP)**: 디컴파일, xref, 심볼, 문자열, 콜그래프, 데이터플로우, vtable 분석
  - PWN/REV 문제 시 Ghidra가 켜져 있어야 사용 가능 (ghidra 명령어로 실행)
- **dreamhack_solver**: python_exec, sage_exec, docker_pwn, docker_exec, netcat_interact,
  rsa_ctftool, binary_info, file_analysis, port_scan, hash_crack, http_request,
  cve_lookup, dns_lookup, trivy, dreamhack_vm
  - docker_exec/docker_pwn 실행 시 --cap-add=SYS_PTRACE --security-opt seccomp=unconfined 자동 적용됨
  - sage_exec 기본 타임아웃 60초. LLL/Coppersmith 등 무거운 연산은 timeout_seconds 늘릴 것

## 로컬 도구
| 도구 | 용도 |
|---|---|
| pwntools | pwn exploit 작성 |
| z3-solver | SMT 솔빙, 제약조건 풀기 |
| SageMath | 수학/암호 연산 (sage_exec MCP 사용) |
| ROPgadget | ROP 가젯 탐색 |
| checksec | 바이너리 보호기법 확인 |
| gdb | 동적 디버깅 |
| radare2 | 바이너리 분석 (Ghidra 대안) |
| binwalk | 펌웨어/파일 추출 |
| nmap | 포트 스캔 |
| hashcat | 해시 크래킹 (GPU) |
| john | 해시 크래킹 (CPU) |
| ffmpeg | 오디오/비디오 분석 |
| exiftool | 메타데이터 분석 |
| gmpy2 | 큰 정수 연산 |
| pycryptodome | 암호 프리미티브 |
| unicorn | CPU 에뮬레이션 |
| capstone | 디스어셈블리 |
| volatility3 | 메모리 포렌식 |

## Skills 로드 규칙
문제 카테고리 판별 즉시 아래 규칙에 따라 skill을 로드한다.
ctf-personal은 항상 로드한다. solve-challenge는 로드하지 않는다 (이 파일이 그 역할을 대체).
reva-* skill은 Ghidra가 실행 중일 때만 추가 로드한다.

기본 (항상):
- ctf-personal

카테고리별 추가:
- WEB: ctf-web
- PWN: ctf-pwn / Ghidra 실행 중이면 reva-ctf-pwn 추가
- REV: ctf-reverse / Ghidra 실행 중이면 reva-ctf-rev, reva-binary-triage 추가
- CRYPTO: ctf-crypto / Ghidra 분석 필요 시 reva-ctf-crypto 추가
- FORENSICS: ctf-forensics
- MISC: ctf-misc
- OSINT: ctf-osint
- MALWARE: ctf-malware

## 카테고리별 워크플로우

### PWN
1. 병렬 트리아지: binary_info + ReVa get-decompilation(main) + ReVa get-strings를 동시 실행
2. Ghidra 꺼져있으면 docker_exec에서 r2 -A 또는 objdump -d로 대체
3. 취약점 식별 (BOF, FSB, heap, UAF, seccomp 등)
4. python_exec로 pwntools exploit 작성
5. docker_pwn 또는 netcat_interact로 원격 실행
6. seccomp 있으면 docker_exec에서 seccomp-tools dump로 허용 syscall 확인 후 ORW 체인 구성

### Crypto
1. 암호 알고리즘 식별 (RSA, AES, ECC, custom 등)
2. RSA → rsa_ctftool 먼저 시도, 안 되면 sage_exec
3. ECC/격자/다항식 → sage_exec (타임아웃 주의: 무거운 연산은 timeout_seconds=300)
4. 커스텀 암호 → python_exec로 분석/복호화
5. 주의: SageMath 연산은 반드시 sage_exec 사용 (python_exec에서 sage 임포트 불가)

### Web
1. file_analysis로 소스코드 전체 파악
2. 취약점 패턴 탐색: SSTI, SQLi, XSS, SSRF, LFI, 역직렬화, JWT, 프로토타입 오염, ETag leak
3. http_request로 페이로드 전송, python_exec로 자동화 스크립트 작성
4. 봇 문제: XSS → CSRF 체이닝, TCP 터널링(bore.pub 등)으로 콜백 수신 (VPS 불필요)
5. SSRF: rbndr.us DNS rebinding + TCP 터널링 콜백 조합 (내부망 접근 시)

### REV
1. binary_info로 파일 타입, 문자열 확인
2. Ghidra 켜져있으면 ReVa 디컴파일, 아니면 docker_exec에서 r2 -AAA -c 'pdf @main' 또는 python_exec로 직접 분석
3. 키 검증/플래그 생성 알고리즘 역산
4. 필요시 python_exec로 z3 제약조건 풀기 또는 직접 역산
5. 언패킹 필요 시: docker_exec에서 upx -d binary
6. Go/Rust 바이너리: 심볼 스트리핑 주의, strings + ReVa get-strings로 힌트 탐색

### Forensics
1. binary_info + file_analysis로 파일 타입 식별
2. binwalk로 내장 파일 추출 (docker_exec 사용)
3. 이미지 스테가노 → docker_exec에서 steghide, zsteg / exiftool은 로컬 사용 가능
4. 메모리 덤프 → 로컬 vol 명령어 사용 (vol -f dump.mem windows.pslist)
5. 네트워크 캡처 → python_exec로 scapy 파싱
6. 오디오 → ffmpeg 변환 후 스펙트로그램 분석
7. 디스크 이미지 → docker_exec에서 mount + 파일시스템 탐색
8. PDF → docker_exec에서 pdf-parser, pdftotext로 오브젝트/JS 추출

### MISC
1. file_analysis로 파일/형식 파악
2. 인코딩 퍼즐 → python_exec로 base64/32/58/85, hex, rot13 순차 시도
3. Pyjail/Bash jail → python_exec로 우회 페이로드 생성
4. 스테가노그래피 → Forensics 워크플로우 참조
5. Z3/제약조건 → python_exec로 z3 solver
6. QR코드/바코드 → python_exec로 pyzbar, PIL

### OSINT
1. 주어진 정보로 dns_lookup, port_scan 활용
2. WebSearch로 Google dorking ("site:", "inurl:", "filetype:")
3. 이미지 → exiftool GPS 좌표, WebSearch로 역이미지 검색
4. 도메인/IP → dns_lookup 서브도메인 열거, WebFetch로 Wayback Machine
5. 사용자명 → WebSearch로 크로스플랫폼 탐색

### MALWARE
1. file_analysis + binary_info로 파일 타입/문자열 확인
2. docker_exec에서 격리 실행 (절대 로컬에서 실행 금지)
3. 난독화 스크립트 → python_exec로 디코딩/디오브퓨스케이션
4. PE/ELF 분석 → Ghidra 있으면 ReVa, 없으면 docker_exec에서 strings + r2
5. C2 통신 → python_exec로 네트워크 트래픽 파싱, 프로토콜 역산
6. YARA 룰 → docker_exec에서 yara 매칭

## Dreamhack 특이사항
- 플래그 포맷: DH{...}
- 봇: Puppeteer 기반 Chromium
- 서버 포트: 8000~9000번대
- 서버 크래시 시: dreamhack_vm으로 restart
  - action: start / stop / restart / status
  - session_id, csrf_token: 브라우저 쿠키에서 확인 (만료 주기 약 7일)

## 작업 규칙
- 문제 파일 받으면 file_analysis 또는 binary_info로 즉시 트리아지
- 설명보다 코드 먼저 작성
- exploit 실패하면 에러 분석 후 즉시 수정, 같은 시도 반복 금지
- 3회 이상 실패 시, 이전 시도를 "시도 N: [기법] → [실패 원인 1줄]"로 요약하고 새 접근
- 원격 서버는 docker_pwn 또는 netcat_interact 사용
- Linux 전용 도구(steghide, zsteg 등)는 docker_exec에서 실행
- 초기 분석 단계에서 독립적인 작업은 병렬 실행하여 대기 시간 최소화
- GDB 디버깅은 gdb -batch -x 스크립트로 docker_exec에서 실행 (macOS는 Rosetta 에뮬레이션으로 느림)
- 플래그 형식 항상 확인, 획득 즉시 보고
- 풀이 완료 후 새 기법 사용 시 해당 skill 파일 업데이트

## 풀이 완료 후 skill 업데이트 규칙
- 새 기법 → 해당 카테고리 skill 파일에 추가
- 새 CVE → ctf-web/cves.md 또는 해당 카테고리 파일에 추가
- ctf-personal → 새로운 MCP 활용 패턴, 플랫폼 특이사항 발견 시 업데이트
- 기존 내용은 절대 삭제하지 않음
