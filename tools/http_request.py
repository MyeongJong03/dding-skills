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
        body_hex: str = None,
        follow_redirects: bool = True,
        timeout: int = 30
    ) -> str:
        """
        커스텀 HTTP 요청을 보냅니다.
        CTF 웹 챌린지에서 커스텀 헤더, 쿠키, 바디를 자유롭게 설정할 때 사용합니다.
        body: UTF-8 텍스트 바디
        body_hex: hex 인코딩된 바이너리 바디 (예: "4141420a"). body보다 우선.
        follow_redirects: False로 설정하면 리다이렉트를 따라가지 않음 (SSRF 등에 유용)
        """
        try:
            # body 결정: body_hex 우선
            if body_hex:
                content = bytes.fromhex(body_hex)
            elif body:
                content = body.encode()
            else:
                content = None

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
                    content=content
                )
            return json.dumps({
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.text[:8000],
                "url": str(resp.url)
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
