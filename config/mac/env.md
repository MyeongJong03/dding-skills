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
- GDB 디버깅은 docker_exec에서 실행 (macOS는 Rosetta 에뮬레이션으로 느림)

