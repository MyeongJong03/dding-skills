import subprocess
import json
import httpx

def register(mcp):
    @mcp.tool()
    def dns_lookup(
        domain: str,
        record_type: str = "A",
        subdomain_wordlist: list = None
    ) -> str:
        """
        DNS 레코드 조회 및 서브도메인 열거를 수행합니다.
        record_type: A, AAAA, MX, TXT, CNAME, NS 등
        subdomain_wordlist: 서브도메인 열거 시 시도할 단어 목록
        """
        result = {}

        # DNS 조회
        try:
            r = subprocess.run(
                ["dig", "+short", record_type, domain],
                capture_output=True, text=True, timeout=15,
                stdin=subprocess.DEVNULL
            )
            result["dns_record"] = {
                "domain": domain,
                "type": record_type,
                "answer": r.stdout.strip().splitlines()
            }
        except Exception as e:
            result["dns_record"] = {"error": str(e)}

        # 서브도메인 열거
        if subdomain_wordlist:
            found = []
            for sub in subdomain_wordlist[:50]:  # 최대 50개
                fqdn = f"{sub}.{domain}"
                try:
                    r = subprocess.run(
                        ["dig", "+short", "A", fqdn],
                        capture_output=True, text=True, timeout=5,
                        stdin=subprocess.DEVNULL
                    )
                    if r.stdout.strip():
                        found.append({"subdomain": fqdn, "ip": r.stdout.strip()})
                except Exception:
                    continue
            result["subdomains_found"] = found

        return json.dumps(result, ensure_ascii=False, indent=2)
