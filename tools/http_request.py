import httpx
import json

def register(mcp):
    @mcp.tool()
    def http_request(
        url: str,
        method: str = "GET",
        headers: dict = None,
        cookies: dict = None,
        body: str = None,
        follow_redirects: bool = True,
        timeout: int = 30
    ) -> str:
        """
        커스텀 HTTP 요청을 보냅니다.
        CTF 웹 챌린지에서 커스텀 헤더, 쿠키, 바디를 자유롭게 설정할 때 사용합니다.
        """
        try:
            with httpx.Client(
                follow_redirects=follow_redirects,
                timeout=timeout,
                verify=False  # CTF 환경에서 self-signed cert 대응
            ) as client:
                resp = client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers or {},
                    cookies=cookies or {},
                    content=body.encode() if body else None
                )
            return json.dumps({
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.text[:5000],
                "url": str(resp.url)
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
