import subprocess
import json
import os

def register(mcp):
    @mcp.tool()
    def binary_info(file_path: str) -> str:
        """
        바이너리 파일 기본 정보를 분석합니다.
        file, strings, checksec 결과를 한 번에 반환합니다.
        """
        if not os.path.exists(file_path):
            return json.dumps({"error": f"파일을 찾을 수 없음: {file_path}"})

        result = {}

        # file 명령어
        try:
            r = subprocess.run(
                ["file", file_path],
                capture_output=True, text=True, timeout=10,
                stdin=subprocess.DEVNULL
            )
            result["file"] = r.stdout.strip()
        except Exception as e:
            result["file"] = f"error: {e}"

        # strings (길이 4 이상, 상위 100개)
        try:
            r = subprocess.run(
                ["strings", "-n", "4", file_path],
                capture_output=True, text=True, timeout=15,
                stdin=subprocess.DEVNULL
            )
            lines = r.stdout.strip().splitlines()
            result["strings_count"] = len(lines)
            result["strings_sample"] = lines[:100]
        except Exception as e:
            result["strings"] = f"error: {e}"

        # checksec (pwntools 설치된 경우)
        try:
            r = subprocess.run(
                ["python3", "-c",
                 f"from pwn import *; e=ELF('{file_path}', checksec=False); "
                 f"print(json.dumps({{'arch':e.arch,'bits':e.bits,'os':e.os,"
                 f"'nx':e.nx,'pie':e.pie,'canary':e.canary,'relro':e.relro}}))"],
                capture_output=True, text=True, timeout=15,
                stdin=subprocess.DEVNULL
            )
            if r.returncode == 0:
                result["checksec"] = json.loads(r.stdout.strip())
            else:
                # checksec 단독 명령어 시도
                r2 = subprocess.run(
                    ["checksec", "--file", file_path],
                    capture_output=True, text=True, timeout=10,
                    stdin=subprocess.DEVNULL
                )
                result["checksec"] = r2.stdout.strip() or r2.stderr.strip()
        except Exception as e:
            result["checksec"] = f"error: {e}"

        return json.dumps(result, ensure_ascii=False, indent=2)
