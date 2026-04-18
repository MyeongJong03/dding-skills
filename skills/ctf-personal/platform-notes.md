# Platform Notes — 플랫폼/환경별 특이사항

---

## CTF 플랫폼

### 일반 CTF
- 플래그 포맷: `FLAG{...}` 또는 `[대회명]{...}`
- CTFd 플랫폼: `/api/v1/challenges`로 문제 목록 조회 가능

### Dreamhack
- 플래그 포맷: DH{...}
- 봇: Puppeteer 기반 Chromium
- 서버 포트: 8000~9000번대
- 서버 크래시 시: dreamhack_vm MCP로 restart
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
