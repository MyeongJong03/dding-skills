import httpx
import json
import time

def register(mcp):
    @mcp.tool()
    def dreamhack_vm(
        challenge_id: int,
        action: str = "start",
        session_id: str = "",
        csrf_token: str = ""
    ) -> str:
        """
        Dreamhack 워게임 서버를 제어합니다.
        action: start(서버 생성), stop(서버 종료), restart(재시작), status(상태 확인)
        session_id: 브라우저 쿠키의 sessionid 값
        csrf_token: 브라우저 쿠키의 csrf_token 값
        """
        base_url = f"https://dreamhack.io/api/v1/wargame/challenges/{challenge_id}/live/"
        headers = {
            "accept": "application/json",
            "content-length": "0",
            "origin": "https://dreamhack.io",
            "referer": f"https://dreamhack.io/wargame/challenges/{challenge_id}",
            "x-csrftoken": csrf_token,
            "user-agent": "Mozilla/5.0"
        }
        cookies = {
            "sessionid": session_id,
            "csrf_token": csrf_token
        }
        try:
            with httpx.Client(timeout=30, verify=True) as client:
                if action == "status":
                    resp = client.get(base_url, headers=headers, cookies=cookies)
                elif action == "start":
                    resp = client.post(base_url, headers=headers, cookies=cookies)
                elif action == "stop":
                    resp = client.delete(base_url, headers=headers, cookies=cookies)
                elif action == "restart":
                    client.delete(base_url, headers=headers, cookies=cookies)
                    time.sleep(2)
                    resp = client.post(base_url, headers=headers, cookies=cookies)
                else:
                    return json.dumps({"error": "action은 start/stop/restart/status 중 하나"})
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return json.dumps({
                "status_code": resp.status_code,
                "response": data
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
