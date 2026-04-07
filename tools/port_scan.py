import subprocess
import json

def register(mcp):
    @mcp.tool()
    def port_scan(target: str, ports: str = "1-1000", flags: str = "-T4") -> str:
        """
        nmap으로 대상 호스트의 포트/서비스를 스캔합니다.
        target: IP 또는 도메인
        ports: 포트 범위 (기본: 1-10000)
        flags: nmap 추가 옵션 (기본: -sV 서비스 버전 탐지)
        """
        try:
            cmd = ["nmap", flags, "-p", ports, "--open", "-oX", "-", target]
            # flags를 공백 분리해서 처리
            cmd = ["nmap"] + flags.split() + ["-p", ports, "--open", target]
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120,
                stdin=subprocess.DEVNULL
            )
            if result.returncode != 0 and not result.stdout:
                return json.dumps({"error": result.stderr[:500]})
            return json.dumps({
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:500],
                "return_code": result.returncode
            }, ensure_ascii=False, indent=2)
        except FileNotFoundError:
            return json.dumps({"error": "nmap이 설치되어 있지 않습니다. brew install nmap"})
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "스캔 타임아웃 (120초 초과)"})
        except Exception as e:
            return json.dumps({"error": str(e)})
