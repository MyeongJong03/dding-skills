import subprocess
import json
import os

def register(mcp):
    @mcp.tool()
    def rsa_ctftool(
        n: str = None,
        e: str = None,
        ciphertext: str = None,
        publickey_path: str = None,
        attack: str = "all",
        extra_flags: str = ""
    ) -> str:
        """
        RSActfTool로 RSA 취약점을 자동 공격합니다.
        n, e: 모듈러스와 공개지수 (직접 입력)
        ciphertext: 복호화할 암호문 (hex 또는 정수)
        publickey_path: PEM 공개키 파일 경로
        attack: 사용할 공격 (기본: all - 모든 공격 시도)
        """
        cmd = ["rsactftool"]

        if publickey_path:
            cmd += ["--publickey", publickey_path]
        elif n and e:
            cmd += ["-n", str(n), "-e", str(e)]
        else:
            return json.dumps({"error": "n+e 또는 publickey_path 중 하나 필요"})

        if ciphertext:
            cmd += ["--decrypt", str(ciphertext)]

        cmd += ["--attack", attack, "--private"]

        if extra_flags:
            cmd += extra_flags.split()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120,
                stdin=subprocess.DEVNULL
            )
            return json.dumps({
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "return_code": result.returncode
            }, ensure_ascii=False, indent=2)
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "타임아웃 (120초 초과)"})
        except Exception as e:
            return json.dumps({"error": str(e)})
