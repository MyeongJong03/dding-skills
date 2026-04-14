import subprocess
import json

def register(mcp):
    @mcp.tool()
    def netcat_interact(
        host: str,
        port: int,
        payload: str,
        timeout: int = 30
    ) -> str:
        """
        CTF nc 서버에 단순 payload를 전송하고 응답을 받습니다.
        복잡한 pwntools 상호작용은 docker_pwn을 사용하세요.
        payload: 전송할 문자열 (\\n으로 줄바꿈)
        timeout: 응답 대기 시간 (초)
        """
        try:
            payload_bytes = payload.replace("\\n", "\n").encode()
            result = subprocess.run(
                ["nc", "-w", str(timeout), host, str(port)],
                input=payload_bytes,
                capture_output=True, timeout=timeout + 5,
                stdin=subprocess.PIPE
            )
            return json.dumps({
                "stdout": result.stdout.decode(errors="ignore")[:8000],
                "return_code": result.returncode
            }, ensure_ascii=False, indent=2)

        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"타임아웃 ({timeout}초 초과)"})
        except Exception as e:
            return json.dumps({"error": str(e)})
