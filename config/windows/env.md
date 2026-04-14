# CTF 풀이 환경

## Role
CTF 문제 풀이 보조. 불필요한 설명 최소화, 익스플로잇 코드와 플래그 획득에 집중.

## 환경 정보 (WSL2 Ubuntu 24.04)
- Python: /usr/bin/python3 (3.12)
- SageMath: /home/myeongjong00/miniforge3/envs/sage/bin/sage
- Docker image: ctf-pwn:latest (pwntools 4.15.0, pwninit 3.3.1)
- rockyou: /home/myeongjong00/wordlists/rockyou.txt
- RSActfTool: /home/myeongjong00/RsaCtfTool/src/RsaCtfTool/main.py
- Ghidra: Windows 네이티브 (ReVa MCP로 연결)
- 재부팅 후 반드시 update-reva 실행 필요 (WSL2 IP 변경)
- ~/Downloads, ~/Desktop, ~/Documents → Windows 폴더 심링크
- GDB 디버깅: docker_exec에서 실행 (WSL2 x86 네이티브라 빠름)

