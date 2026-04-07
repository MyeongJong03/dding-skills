import httpx
import json

def register(mcp):
    @mcp.tool()
    def cve_lookup(cve_id: str) -> str:
        """
        CVE ID로 상세 정보, 공격 벡터, PoC 정보를 조회합니다.
        NVD API와 GitHub Advisory를 활용합니다.
        """
        result = {
            "cve_id": cve_id,
            "nvd": None,
            "github_advisory": None,
            "poc_references": []
        }

        # 1) NVD API 조회
        try:
            resp = httpx.get(
                f"https://services.nvd.nist.gov/rest/json/cves/2.0",
                params={"cveId": cve_id},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                vulns = data.get("vulnerabilities", [])
                if vulns:
                    cve_data = vulns[0].get("cve", {})
                    descriptions = cve_data.get("descriptions", [])
                    desc_en = next(
                        (d["value"] for d in descriptions if d["lang"] == "en"),
                        "설명 없음"
                    )
                    # CVSS 점수 추출
                    metrics = cve_data.get("metrics", {})
                    cvss_score = None
                    for version_key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                        if version_key in metrics:
                            cvss_score = metrics[version_key][0].get(
                                "cvssData", {}
                            ).get("baseScore")
                            break

                    # 참조 링크에서 PoC 힌트 추출
                    references = cve_data.get("references", [])
                    for ref in references:
                        url = ref.get("url", "")
                        tags = ref.get("tags", [])
                        if any(t in tags for t in ["Exploit", "Third Party Advisory"]):
                            result["poc_references"].append(url)
                        elif "github.com" in url and ("poc" in url.lower() or "exploit" in url.lower()):
                            result["poc_references"].append(url)

                    result["nvd"] = {
                        "description": desc_en,
                        "cvss_score": cvss_score,
                        "references_count": len(references),
                        "all_references": [r["url"] for r in references[:10]]
                    }
        except Exception as e:
            result["nvd"] = {"error": str(e)}

        # 2) GitHub Advisory 조회
        try:
            resp = httpx.get(
                f"https://api.github.com/advisories",
                params={"cve_id": cve_id},
                headers={"Accept": "application/vnd.github+json"},
                timeout=15
            )
            if resp.status_code == 200:
                advisories = resp.json()
                if advisories:
                    adv = advisories[0]
                    result["github_advisory"] = {
                        "summary": adv.get("summary"),
                        "severity": adv.get("severity"),
                        "vulnerable_packages": [
                            {
                                "ecosystem": v.get("package", {}).get("ecosystem"),
                                "name": v.get("package", {}).get("name"),
                                "vulnerable_range": v.get("vulnerable_version_range"),
                                "patched_version": v.get("patched_versions")
                            }
                            for v in adv.get("vulnerabilities", [])
                        ]
                    }
        except Exception as e:
            result["github_advisory"] = {"error": str(e)}

        return json.dumps(result, ensure_ascii=False, indent=2)