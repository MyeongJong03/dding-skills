import subprocess
import json
import tempfile
import os

SAGE_PATH = "/Applications/SageMath-10-8.app/Contents/Frameworks/Sage.framework/Versions/10.8/local/bin/sage"

def register(mcp):
    @mcp.tool()
    def sage_exec(code: str, timeout_seconds: int = 60) -> str:
        """
        SageMath 코드를 실행합니다.
        CTF crypto 문제에서 고급 수학 연산(ECC, 격자, 다항식, 소인수분해 등)에 사용합니다.
        """
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sage", delete=False
            ) as f:
                f.write(code)
                tmp_path = f.name

            result = subprocess.run(
                [SAGE_PATH, tmp_path],
                capture_output=True, text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL
            )
            os.unlink(tmp_path)

            return json.dumps({
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "return_code": result.returncode
            }, ensure_ascii=False, indent=2)

        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"타임아웃 ({timeout_seconds}초 초과)"})
        except FileNotFoundError:
            return json.dumps({"error": f"SageMath를 찾을 수 없습니다: {SAGE_PATH}"})
        except Exception as e:
            return json.dumps({"error": str(e)})
