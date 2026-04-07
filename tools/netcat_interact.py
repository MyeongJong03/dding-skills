import subprocess
import json
import tempfile
import os

def register(mcp):
    @mcp.tool()
    def netcat_interact(
        host: str,
        port: int,
        payload: str = None,
        pwntools_script: str = None,
        timeout: int = 30
    ) -> str:
        """
        CTF pwn/nc 서버와 상호작용합니다.
        payload: 단순 문자열 전송 (\\n으로 줄바꿈)
        pwntools_script: pwntools 코드 직접 실행 (더 복잡한 상호작용)
        """
        try:
            if pwntools_script:
                # pwntools 스크립트 실행
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False
                ) as f:
                    f.write(f"from pwn import *\n")
                    f.write(f"r = remote('{host}', {port})\n")
                    f.write(pwntools_script)
                    tmp_path = f.name

                result = subprocess.run(
                    ["python3", tmp_path],
                    capture_output=True, text=True, timeout=timeout,
                    stdin=subprocess.DEVNULL
                )
                os.unlink(tmp_path)
                return json.dumps({
                    "stdout": result.stdout[:5000],
                    "stderr": result.stderr[:1000],
                    "return_code": result.returncode
                }, ensure_ascii=False, indent=2)

            elif payload:
                # 단순 페이로드 전송
                payload_bytes = payload.replace("\\n", "\n").encode()
                result = subprocess.run(
                    ["nc", "-w", str(timeout), host, str(port)],
                    input=payload_bytes,
                    capture_output=True, timeout=timeout + 5,
                    stdin=subprocess.PIPE
                )
                return json.dumps({
                    "stdout": result.stdout.decode(errors="ignore")[:5000],
                    "return_code": result.returncode
                }, ensure_ascii=False, indent=2)

            else:
                return json.dumps({"error": "payload 또는 pwntools_script 중 하나를 제공해야 합니다."})

        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"타임아웃 ({timeout}초 초과)"})
        except Exception as e:
            return json.dumps({"error": str(e)})
