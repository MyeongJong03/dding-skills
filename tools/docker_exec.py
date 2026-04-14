import subprocess
import json
import os
import shutil

CTF_IMAGE = "ctf-pwn:latest"
# 호스트 작업 디렉토리: 모든 docker 호출이 이 디렉토리를 공유
CTF_WORKSPACE = os.environ.get("CTF_WORKSPACE", os.path.expanduser("~/CTF/workspace"))

def register(mcp):
    @mcp.tool()
    def docker_exec(
        code: str,
        binary_path: str = None,
        timeout_seconds: int = 60
    ) -> str:
        """
        Linux CTF 환경(Docker)에서 코드를 실행합니다.
        PWN/REV 문제에서 Linux ELF 바이너리 실행, GDB 디버깅, pwntools 익스플로잇에 사용합니다.
        /workspace 디렉토리는 호출 간 파일이 유지됩니다.
        binary_path: 로컬 바이너리 경로 (지정 시 /workspace/로 복사됨)
        code: 실행할 bash 또는 python3 코드
        """
        try:
            os.makedirs(CTF_WORKSPACE, exist_ok=True)

            # binary_path가 주어지면 workspace로 복사
            if binary_path and os.path.exists(binary_path):
                binary_name = os.path.basename(binary_path)
                dest = os.path.join(CTF_WORKSPACE, binary_name)
                if not os.path.exists(dest):
                    shutil.copy2(binary_path, dest)

            cmd = [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "--cap-add=SYS_PTRACE",
                "--security-opt", "seccomp=unconfined",
                "-v", f"{CTF_WORKSPACE}:/workspace",
                CTF_IMAGE,
                "bash", "-c", code
            ]

            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL
            )

            stdout = result.stdout
            stderr = result.stderr

            return json.dumps({
                "stdout": stdout[-8000:] if len(stdout) > 8000 else stdout,
                "stderr": stderr[-3000:] if len(stderr) > 3000 else stderr,
                "return_code": result.returncode
            }, ensure_ascii=False, indent=2)

        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"타임아웃 ({timeout_seconds}초 초과)"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def docker_pwn(
        pwntools_script: str,
        binary_path: str = None,
        timeout_seconds: int = 60
    ) -> str:
        """
        Docker Linux 환경에서 pwntools 익스플로잇을 실행합니다.
        PWN 챌린지 전용. 바이너리를 실제 Linux에서 실행하고 익스플로잇합니다.
        완전한 pwntools 스크립트를 작성해 주세요 (from pwn import * 포함).
        /workspace 디렉토리는 호출 간 파일이 유지됩니다.
        """
        try:
            os.makedirs(CTF_WORKSPACE, exist_ok=True)

            # binary_path가 주어지면 workspace로 복사
            if binary_path and os.path.exists(binary_path):
                binary_name = os.path.basename(binary_path)
                dest = os.path.join(CTF_WORKSPACE, binary_name)
                if not os.path.exists(dest):
                    shutil.copy2(binary_path, dest)

            # 스크립트를 workspace에 저장 (컨테이너 내부에서도 접근 가능)
            script_path = os.path.join(CTF_WORKSPACE, "_exploit.py")
            with open(script_path, "w") as f:
                f.write(pwntools_script)

            cmd = [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "--cap-add=SYS_PTRACE",
                "--security-opt", "seccomp=unconfined",
                "-v", f"{CTF_WORKSPACE}:/workspace",
                CTF_IMAGE,
                "python3", "/workspace/_exploit.py"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL
            )

            stdout = result.stdout
            stderr = result.stderr

            return json.dumps({
                "stdout": stdout[-8000:] if len(stdout) > 8000 else stdout,
                "stderr": stderr[-3000:] if len(stderr) > 3000 else stderr,
                "return_code": result.returncode
            }, ensure_ascii=False, indent=2)

        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"타임아웃 ({timeout_seconds}초 초과)"})
        except Exception as e:
            return json.dumps({"error": str(e)})
