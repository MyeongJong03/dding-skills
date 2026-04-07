import subprocess
import json
import os
import tempfile

CTF_IMAGE = "ctf-pwn:latest"

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
        binary_path: 로컬 바이너리 경로 (지정 시 컨테이너로 복사됨)
        code: 실행할 bash 또는 python3 코드
        """
        try:
            cmd = [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "--cap-add=SYS_PTRACE",
                "--security-opt", "seccomp=unconfined",
            ]

            if binary_path and os.path.exists(binary_path):
                binary_name = os.path.basename(binary_path)
                cmd += ["-v", f"{binary_path}:/workspace/{binary_name}"]

            cmd += [
                CTF_IMAGE,
                "bash", "-c", code
            ]

            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL
            )

            return json.dumps({
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
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
        host: str = None,
        port: int = None,
        timeout_seconds: int = 60
    ) -> str:
        """
        Docker Linux 환경에서 pwntools 익스플로잇을 실행합니다.
        PWN 챌린지 전용. 바이너리를 실제 Linux에서 실행하고 익스플로잇합니다.
        """
        try:
            script_lines = ["from pwn import *"]
            if binary_path:
                binary_name = os.path.basename(binary_path)
                script_lines.append(f"binary = ELF('/workspace/{binary_name}')")
            if host and port:
                script_lines.append(f"r = remote('{host}', {port})")
            elif binary_path:
                binary_name = os.path.basename(binary_path)
                script_lines.append(f"r = process('/workspace/{binary_name}')")

            script_lines.append(pwntools_script)
            full_script = "\n".join(script_lines)

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as f:
                f.write(full_script)
                tmp_path = f.name

            cmd = [
                "docker", "run", "--rm",
                "--platform", "linux/amd64",
                "--cap-add=SYS_PTRACE",
                "--security-opt", "seccomp=unconfined",
                "-v", f"{tmp_path}:/workspace/exploit.py",
            ]

            if binary_path and os.path.exists(binary_path):
                binary_name = os.path.basename(binary_path)
                cmd += ["-v", f"{binary_path}:/workspace/{binary_name}"]

            cmd += [CTF_IMAGE, "python3", "/workspace/exploit.py"]

            result = subprocess.run(
                cmd,
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
        except Exception as e:
            return json.dumps({"error": str(e)})
