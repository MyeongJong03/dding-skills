# Platform Notes — 플랫폼/환경별 특이사항

---

## CTF 플랫폼

### 일반 CTF
- 플래그 포맷: `FLAG{...}` 또는 `[대회명]{...}`
- CTFd 플랫폼: `/api/v1/challenges`로 문제 목록 조회 가능

### GZCTF 비동기 제출 응답
- challenge submit POST가 HTTP 200과 JSON/object 대신 정수 submission ID만 반환할 수 있다.
- 이 정수 응답을 즉시 Accepted/Error로 해석하지 않는다. 제출 ID를 저장하고 status endpoint를 bounded polling한다.
- 실제 상태가 `Accepted`가 된 뒤 flag store와 challenge solved 상태를 한 번만 갱신한다.
- generic adapter가 정수 응답을 `error`로 표시해도 같은 flag를 즉시 재제출하지 말고 먼저 ID 상태를 확인한다.
- Cookie/Authorization 원문과 raw response 전체는 public metrics나 writeup에 남기지 않는다.

### GZCTF 첨부파일 교체 감지
- 같은 challenge ID와 파일명이어도 운영 중 attachment 내용이 교체될 수 있다.
- platform sync 때 파일 존재 여부만 보지 말고 크기와 SHA-256을 다시 계산한다.
- digest가 달라지면 기존 추출물, offset, solver 결과를 stale로 표시하고 새 파일에서 다시 검증한다.
- 원격 동작과 attachment가 충돌하면 분석 실수로 단정하기 전에 현재 platform digest와 로컬 digest를 비교한다.
- writeup에는 사용한 attachment hash를 기록하되 인증 URL과 query string은 남기지 않는다.

### Dreamhack
- 플래그 포맷: DH{...}
- 봇: Puppeteer 기반 Chromium
- 서버 포트: 8000~9000번대
- 서버 크래시 시: dreamhack_vm MCP로 restart
- 워게임 상세 페이지 HTML에 실제 접속 정보가 그대로 들어 있다.
  `시스템해킹 문제: nc hostX.dreamhack.games PORT` 문자열을 정규식으로 뽑으면 현재 VM의 host/port를 바로 회수할 수 있다.
- `restart` 후에는 host와 port가 둘 다 바뀔 수 있다. 이전 `host:port`를 재사용하지 말고 페이지에서 다시 긁어야 한다.
- 외부 CTF 문제를 재호스팅한 워게임은 hidden secret이 원 대회 포맷(`INCOGNITO{...}` 등)으로 남아 있을 수 있다. 제출도 원 포맷 그대로 받는 경우가 있으니, `DH{...}` 가정이 안 맞으면 실제로 leak된 포맷을 먼저 제출해 본다.

---

## macOS / Apple Silicon

- 대형 HF 모델 추론은 `uv run` 임시 환경 + `torch` MPS 조합이 가장 빠름
  `device = 'mps' if torch.backends.mps.is_available() else 'cpu'`
- `transformers` 전역 설치 없이 로컬 `model.safetensors`를 바로 열 수 있음
  `uv run --with torch --with transformers --with safetensors --with accelerate python`

---

## Codex 환경

- Codex 첨부 이미지가 워크스페이스에 안 보이면 `~/.codex/sessions/...jsonl`에서 `data:image/...;base64,...`를 추출해 원본 복구 후 블러/축소 분석

---

## MCP 도구 특이사항

### cloudflared 콜백
- 터널 URL 획득 후 바로 exploit 제출하면 0 hits (라우팅 미안정)
- 반드시 ~8초 대기: `time.sleep(8)`
- `cloudflared`는 `..` 경로를 400으로 막을 수 있음 → bore.pub 같은 raw TCP 터널 대안 사용

### bore.pub 콜백
- VPS 불필요한 TCP 터널링
- SSRF, XSS 콜백 수신에 적합
- DNS rebinding과 조합 가능
