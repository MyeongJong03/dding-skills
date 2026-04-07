import subprocess
import json
import tempfile
import os

def register(mcp):
    @mcp.tool()
    def python_exec(code: str, timeout_seconds: int = 60) -> str:
        """
        Python 코드를 실행하고 결과를 반환합니다.
        requests, urllib 등 네트워크 라이브러리 사용 가능.
        CTF 공격 페이로드 실행에 활용합니다.
        """
        try:
            # 임시 파일에 코드 저장 후 실행
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as f:
                f.write(code)
                tmp_path = f.name

            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            os.unlink(tmp_path)  # 임시 파일 삭제

            output = {
                "stdout": result.stdout[:5000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
                "return_code": result.returncode
            }

            return json.dumps(output, ensure_ascii=False, indent=2)

        except subprocess.TimeoutExpired:
            os.unlink(tmp_path)
            return json.dumps({"error": f"실행 타임아웃 ({timeout_seconds}초 초과)"})
        except Exception as e:
            return json.dumps({"error": str(e)})