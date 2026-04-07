import subprocess
import json

def register(mcp):
    @mcp.tool()
    def trivy(file_path: str) -> str:
        """
        Trivy를 사용하여 의존성 파일(package.json, requirements.txt 등)의
        알려진 취약점(CVE)을 스캔합니다.
        """
        try:
            # 1차 시도: DB 업데이트 스킵 (캐시 있을 때 빠름)
            result = subprocess.run(
                [
                    "trivy", "filesystem",
                    "--format", "json",
                    "--severity", "CRITICAL,HIGH,MEDIUM",
                    "--skip-db-update",
                    "--timeout", "60s",
                    file_path
                ],
                capture_output=True, text=True, timeout=120
            )

            # DB 캐시 없음 → --skip-db-update 없이 재시도 (자동 DB 다운로드)
            if result.returncode != 0 and "skip-db-update" in result.stderr:
                result = subprocess.run(
                    [
                        "trivy", "filesystem",
                        "--format", "json",
                        "--severity", "CRITICAL,HIGH,MEDIUM",
                        "--timeout", "120s",
                        file_path
                    ],
                    capture_output=True, text=True, timeout=180
                )

            # trivy JSON 출력 파싱
            try:
                scan_result = json.loads(result.stdout)
            except json.JSONDecodeError:
                return json.dumps({
                    "error": "trivy 출력 파싱 실패",
                    "raw_output": result.stdout[:1000]
                })

            # 취약점 요약 추출
            vulnerabilities = []
            for target in scan_result.get("Results", []):
                for vuln in target.get("Vulnerabilities", []):
                    vulnerabilities.append({
                        "id": vuln.get("VulnerabilityID"),
                        "package": vuln.get("PkgName"),
                        "installed_version": vuln.get("InstalledVersion"),
                        "fixed_version": vuln.get("FixedVersion"),
                        "severity": vuln.get("Severity"),
                        "title": vuln.get("Title", ""),
                        "description": vuln.get("Description", "")[:200]
                    })

            return json.dumps({
                "total_vulnerabilities": len(vulnerabilities),
                "vulnerabilities": vulnerabilities
            }, ensure_ascii=False, indent=2)

        except subprocess.TimeoutExpired:
            return json.dumps({"error": "trivy 실행 타임아웃 (120초 초과)"})
        except FileNotFoundError:
            return json.dumps({"error": "trivy가 설치되어 있지 않습니다"})
        except Exception as e:
            return json.dumps({"error": str(e)})