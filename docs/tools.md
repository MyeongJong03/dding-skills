# MCP Tools

Generated from `tools/*.py` by `scripts/dump_mcp_tools.py`.

MCP server name: `ctf_solver`

## Summary

| Tool | Module | Signature | Description |
| --- | --- | --- | --- |
| `binary_info` | `tools/binary_info.py` | `binary_info(file_path: str) -> str` | 바이너리 파일 기본 정보를 분석합니다. file, strings, checksec 결과를 한 번에 반환합니다. |
| `browser_click` | `tools/browser_actions.py` | `browser_click(browser_session_id: str, selector: str, timeout_ms: int = 10000) -> str` | Click a selector in an active browser session. |
| `browser_close` | `tools/browser_actions.py` | `browser_close(browser_session_id: str, reason: str = 'closed') -> str` | Close one browser session and persist local-only closed metadata. |
| `browser_console` | `tools/browser_actions.py` | `browser_console(browser_session_id: str, limit: int = 50) -> str` | Return bounded, redacted console events for a browser session. |
| `browser_cookies` | `tools/browser_actions.py` | `browser_cookies(browser_session_id: str) -> str` | Return redacted cookie summaries. Raw cookie values are never returned. |
| `browser_eval` | `tools/browser_actions.py` | `browser_eval(browser_session_id: str, expression: str, timeout_ms: int = 10000, max_bytes: int = 4000) -> str` | Evaluate JavaScript and return a bounded, redacted result preview. |
| `browser_fill` | `tools/browser_actions.py` | `browser_fill(browser_session_id: str, selector: str, value: str, timeout_ms: int = 10000) -> str` | Fill a selector in an active browser session. Filled values are not echoed. |
| `browser_goto` | `tools/browser_actions.py` | `browser_goto(browser_session_id: str, url: str, timeout_ms: int = 10000, wait_until: str = 'load') -> str` | Navigate an active browser session to a URL. URLs in output are redacted. Regression tests must use local file, data URL, or mock server targets. |
| `browser_list` | `tools/browser_actions.py` | `browser_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str` | List browser sessions, optionally filtered by run_id or challenge_id. Closed sessions are hidden unless include_closed is true. |
| `browser_network` | `tools/browser_actions.py` | `browser_network(browser_session_id: str, limit: int = 50) -> str` | Return bounded, redacted request/response summaries without bodies or raw cookies. |
| `browser_screenshot` | `tools/browser_actions.py` | `browser_screenshot(browser_session_id: str, name: str = None, full_page: bool = False) -> str` | Save a screenshot under the local-only browser artifact root, never in the repo by default. |
| `browser_start` | `tools/browser_actions.py` | `browser_start(run_id: str = None, challenge_id: str = None, worker_id: str = None, platform: str = None, event: str = None, profile: str = None, storage_state: str = None, browser_type: str = 'chromium', headless: bool = True) -> str` | Start a local-only Playwright browser session via the loopback browser daemon. Use run_id/challenge_id to isolate concurrent CTF work. Playwright is optional; missing installs return reason=playwright_not_installed. |
| `browser_upload` | `tools/browser_actions.py` | `browser_upload(browser_session_id: str, selector: str, files: list[str], timeout_ms: int = 10000) -> str` | Upload one or more local files through a file input. Output includes only file counts. |
| `callback_close` | `tools/callbacks.py` | `callback_close(listener_id: str, reason: str = 'closed') -> str` | Close one callback listener and persist local-only closed metadata. |
| `callback_hits` | `tools/callbacks.py` | `callback_hits(listener_id: str, since_hit_id: str = None, limit: int = 20) -> str` | Return bounded, redacted callback hits. Cookies, auth headers, token-like query/body fields, and flag-like values are redacted. |
| `callback_list` | `tools/callbacks.py` | `callback_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str` | List callback listeners, optionally filtered by run_id or challenge_id. Closed listeners are hidden unless include_closed is true. |
| `callback_start` | `tools/callbacks.py` | `callback_start(run_id: str = None, challenge_id: str = None, worker_id: str = None, host: str = '127.0.0.1', port: str = None, external_base_url: str = None, token_path: str = None, allow_public_bind: bool = False) -> str` | Start a local-only web callback listener through the loopback callback daemon. Default bind is 127.0.0.1. Public binds require allow_public_bind. External URLs are metadata only and must be supplied manually. |
| `callback_url` | `tools/callbacks.py` | `callback_url(listener_id: str, external: bool = False, path: str = None) -> str` | Return a local or manually configured external callback URL for a listener. No tunnel provider is started. |
| `callback_wait` | `tools/callbacks.py` | `callback_wait(listener_id: str, timeout_sec: float = 30, pattern: str = None, min_hits: int = 1) -> str` | Wait for callback hits without busy looping. Pattern matching is performed over redacted hit summaries. |
| `cve_lookup` | `tools/cve_lookup.py` | `cve_lookup(cve_id: str) -> str` | CVE ID로 상세 정보, 공격 벡터, PoC 정보를 조회합니다. NVD API와 GitHub Advisory를 활용합니다. |
| `dns_lookup` | `tools/dns_lookup.py` | `dns_lookup(domain: str, record_type: str = 'A', subdomain_wordlist: list = None) -> str` | DNS 레코드 조회 및 서브도메인 열거를 수행합니다. record_type: A, AAAA, MX, TXT, CNAME, NS 등 subdomain_wordlist: 서브도메인 열거 시 시도할 단어 목록 |
| `docker_exec` | `tools/docker_exec.py` | `docker_exec(code: str, binary_path: str = None, timeout_seconds: int = 60) -> str` | Linux CTF 환경(Docker)에서 코드를 실행합니다. PWN/REV 문제에서 Linux ELF 바이너리 실행, GDB 디버깅, pwntools 익스플로잇에 사용합니다. /workspace 디렉토리는 호출 간 파일이 유지됩니다. binary_path: 로컬 바이너리 경로 (지정 시 /workspace/로 복사됨) code: 실행할 bash 또는 python3 코드 |
| `docker_pwn` | `tools/docker_exec.py` | `docker_pwn(pwntools_script: str, binary_path: str = None, timeout_seconds: int = 60) -> str` | Docker Linux 환경에서 pwntools 익스플로잇을 실행합니다. PWN 챌린지 전용. 바이너리를 실제 Linux에서 실행하고 익스플로잇합니다. 완전한 pwntools 스크립트를 작성해 주세요 (from pwn import * 포함). /workspace 디렉토리는 호출 간 파일이 유지됩니다. |
| `dreamhack_vm` | `tools/dreamhack_vm.py` | `dreamhack_vm(challenge_id: int, action: str = 'start', session_id: str = '', csrf_token: str = '') -> str` | Dreamhack 워게임 서버를 제어합니다. action: start(서버 생성), stop(서버 종료), restart(재시작), status(상태 확인) session_id: 브라우저 쿠키의 sessionid 값 csrf_token: 브라우저 쿠키의 csrf_token 값 |
| `file_analysis` | `tools/file_analysis.py` | `file_analysis(file_path: str) -> str` | CTF 문제의 소스코드/설정 파일을 분석합니다. 디렉토리를 지정하면 내부의 텍스트 파일을 읽어 반환합니다. (venv, __pycache__, node_modules 등 불필요한 디렉토리 자동 제외) |
| `hash_crack` | `tools/hash_crack.py` | `hash_crack(hash_value: str, wordlist_path: str = os.path.expanduser('~/wordlists/rockyou.txt'), hashcat_mode: str = None, extra_flags: str = '') -> str` | 해시를 식별하고 hashcat으로 크랙을 시도합니다. hash_value: 크랙할 해시값 wordlist_path: 워드리스트 경로 (기본: rockyou.txt) hashcat_mode: hashcat 모드 번호 (미입력 시 자동 감지) |
| `http_request` | `tools/http_request.py` | `http_request(url: str, method: str = 'GET', headers: dict = None, cookies: dict = None, body: str = None, body_hex: str = None, follow_redirects: bool = True, timeout: int = 30) -> str` | 커스텀 HTTP 요청을 보냅니다. CTF 웹 챌린지에서 커스텀 헤더, 쿠키, 바디를 자유롭게 설정할 때 사용합니다. body: UTF-8 텍스트 바디 body_hex: hex 인코딩된 바이너리 바디 (예: "4141420a"). body보다 우선. follow_redirects: False로 설정하면 리다이렉트를 따라가지 않음 (SSRF 등에 유용) |
| `netcat_interact` | `tools/netcat_interact.py` | `netcat_interact(host: str, port: int, payload: str, timeout: int = 30) -> str` | CTF nc 서버에 단순 payload를 전송하고 응답을 받습니다. 복잡한 pwntools 상호작용은 docker_pwn을 사용하세요. payload: 전송할 문자열 (\n으로 줄바꿈) timeout: 응답 대기 시간 (초) |
| `port_scan` | `tools/port_scan.py` | `port_scan(target: str, ports: str = '1-1000', flags: str = '-T4') -> str` | nmap으로 대상 호스트의 포트/서비스를 스캔합니다. target: IP 또는 도메인 ports: 포트 범위 (기본: 1-1000) flags: nmap 추가 옵션 (기본: -T4) |
| `python_exec` | `tools/python_exec.py` | `python_exec(code: str, timeout_seconds: int = 60) -> str` | Python 코드를 실행하고 결과를 반환합니다. requests, urllib 등 네트워크 라이브러리 사용 가능. CTF 공격 페이로드 실행에 활용합니다. |
| `rsa_ctftool` | `tools/rsa_ctftool.py` | `rsa_ctftool(n: str = None, e: str = None, ciphertext: str = None, publickey_path: str = None, attack: str = 'all', extra_flags: str = '') -> str` | RSActfTool로 RSA 취약점을 자동 공격합니다. n, e: 모듈러스와 공개지수 (직접 입력) ciphertext: 복호화할 암호문 (hex 또는 정수) publickey_path: PEM 공개키 파일 경로 attack: 사용할 공격 (기본: all - 모든 공격 시도) |
| `sage_exec` | `tools/sage_exec.py` | `sage_exec(code: str, timeout_seconds: int = 60) -> str` | SageMath 코드를 실행합니다. CTF crypto 문제에서 고급 수학 연산(ECC, 격자, 다항식, 소인수분해 등)에 사용합니다. |
| `session_close` | `tools/session_tools.py` | `session_close(session_id: str, reason: str = 'closed') -> str` | Close one persistent session and terminate its child process safely. |
| `session_expect` | `tools/session_tools.py` | `session_expect(session_id: str, patterns: list[str], timeout_ms: int = 1000, max_bytes: int = 8000) -> str` | Read until one literal pattern appears or timeout expires. Returns the matched pattern index, timeout status, and bounded output. |
| `session_list` | `tools/session_tools.py` | `session_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str` | List persistent sessions, optionally filtered by run_id or challenge_id. Closed sessions are hidden unless include_closed is true. |
| `session_read` | `tools/session_tools.py` | `session_read(session_id: str, timeout_ms: int = 1000, max_bytes: int = 8000) -> str` | Read bounded output from a persistent session without closing it. Use timeout_ms and max_bytes to avoid blocking or large transcripts. |
| `session_start` | `tools/session_tools.py` | `session_start(kind: str, command: str = None, cwd: str = None, run_id: str = None, challenge_id: str = None, worker_id: str = None, host: str = None, port: str = None, image: str = None, workspace: str = None, timeout_ms: int = 1000, env_json: str = None) -> str` | Start a persistent local session via the loopback-only session daemon. kind: shell, python, sage, nc, or docker-shell. Associate run_id/challenge_id when solving a tracked challenge. |
| `session_write` | `tools/session_tools.py` | `session_write(session_id: str, data: str, newline: bool = True, encoding: str = 'text') -> str` | Write text or base64 data to a persistent session. newline defaults to true for menu prompts and REPL commands. |
| `trivy` | `tools/trivy_scan.py` | `trivy(file_path: str) -> str` | Trivy를 사용하여 의존성 파일(package.json, requirements.txt 등)의 알려진 취약점(CVE)을 스캔합니다. |
| `verify_run` | `tools/verify_run.py` | `verify_run(mode: str, run_dir: str = None, command: str = None, cwd: str = None, timeout_sec: int = 30, retries: int = 0, flag_regex: str = None, success_regex: str = None, fail_regex: str = None, session_id: str = None, session_input: str = None, expect: list[str] = None, evidence_text: str = None, callback_listener_id: str = None, callback_pattern: str = None, callback_min_hits: int = 1, target: str = 'unknown', local: bool = False, remote: bool = False, label: str = '', save: bool = True, save_evidence: bool = False, max_output_bytes: int = 8000) -> str` | Verify solve evidence for a tracked challenge run. Supports command, session, and manual modes. Output is bounded and redacted; raw flag values and raw transcripts are not returned by default. |
| `web_payload_helper` | `tools/callbacks.py` | `web_payload_helper(callback_url: str) -> str` | Generate simple XSS/SSRF/CSS callback payload snippets for a supplied URL. This is a helper scaffold only and does not run an exploit or tunnel. |

## Details

### `binary_info`

- Module: `tools/binary_info.py`
- Signature: `binary_info(file_path: str) -> str`
- Docstring:

```text
바이너리 파일 기본 정보를 분석합니다.
file, strings, checksec 결과를 한 번에 반환합니다.
```

### `browser_click`

- Module: `tools/browser_actions.py`
- Signature: `browser_click(browser_session_id: str, selector: str, timeout_ms: int = 10000) -> str`
- Docstring:

```text
Click a selector in an active browser session.
```

### `browser_close`

- Module: `tools/browser_actions.py`
- Signature: `browser_close(browser_session_id: str, reason: str = 'closed') -> str`
- Docstring:

```text
Close one browser session and persist local-only closed metadata.
```

### `browser_console`

- Module: `tools/browser_actions.py`
- Signature: `browser_console(browser_session_id: str, limit: int = 50) -> str`
- Docstring:

```text
Return bounded, redacted console events for a browser session.
```

### `browser_cookies`

- Module: `tools/browser_actions.py`
- Signature: `browser_cookies(browser_session_id: str) -> str`
- Docstring:

```text
Return redacted cookie summaries. Raw cookie values are never returned.
```

### `browser_eval`

- Module: `tools/browser_actions.py`
- Signature: `browser_eval(browser_session_id: str, expression: str, timeout_ms: int = 10000, max_bytes: int = 4000) -> str`
- Docstring:

```text
Evaluate JavaScript and return a bounded, redacted result preview.
```

### `browser_fill`

- Module: `tools/browser_actions.py`
- Signature: `browser_fill(browser_session_id: str, selector: str, value: str, timeout_ms: int = 10000) -> str`
- Docstring:

```text
Fill a selector in an active browser session. Filled values are not echoed.
```

### `browser_goto`

- Module: `tools/browser_actions.py`
- Signature: `browser_goto(browser_session_id: str, url: str, timeout_ms: int = 10000, wait_until: str = 'load') -> str`
- Docstring:

```text
Navigate an active browser session to a URL. URLs in output are redacted.
Regression tests must use local file, data URL, or mock server targets.
```

### `browser_list`

- Module: `tools/browser_actions.py`
- Signature: `browser_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str`
- Docstring:

```text
List browser sessions, optionally filtered by run_id or challenge_id.
Closed sessions are hidden unless include_closed is true.
```

### `browser_network`

- Module: `tools/browser_actions.py`
- Signature: `browser_network(browser_session_id: str, limit: int = 50) -> str`
- Docstring:

```text
Return bounded, redacted request/response summaries without bodies or raw cookies.
```

### `browser_screenshot`

- Module: `tools/browser_actions.py`
- Signature: `browser_screenshot(browser_session_id: str, name: str = None, full_page: bool = False) -> str`
- Docstring:

```text
Save a screenshot under the local-only browser artifact root, never in the repo by default.
```

### `browser_start`

- Module: `tools/browser_actions.py`
- Signature: `browser_start(run_id: str = None, challenge_id: str = None, worker_id: str = None, platform: str = None, event: str = None, profile: str = None, storage_state: str = None, browser_type: str = 'chromium', headless: bool = True) -> str`
- Docstring:

```text
Start a local-only Playwright browser session via the loopback browser daemon.
Use run_id/challenge_id to isolate concurrent CTF work. Playwright is optional;
missing installs return reason=playwright_not_installed.
```

### `browser_upload`

- Module: `tools/browser_actions.py`
- Signature: `browser_upload(browser_session_id: str, selector: str, files: list[str], timeout_ms: int = 10000) -> str`
- Docstring:

```text
Upload one or more local files through a file input. Output includes only file counts.
```

### `callback_close`

- Module: `tools/callbacks.py`
- Signature: `callback_close(listener_id: str, reason: str = 'closed') -> str`
- Docstring:

```text
Close one callback listener and persist local-only closed metadata.
```

### `callback_hits`

- Module: `tools/callbacks.py`
- Signature: `callback_hits(listener_id: str, since_hit_id: str = None, limit: int = 20) -> str`
- Docstring:

```text
Return bounded, redacted callback hits. Cookies, auth headers, token-like
query/body fields, and flag-like values are redacted.
```

### `callback_list`

- Module: `tools/callbacks.py`
- Signature: `callback_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str`
- Docstring:

```text
List callback listeners, optionally filtered by run_id or challenge_id.
Closed listeners are hidden unless include_closed is true.
```

### `callback_start`

- Module: `tools/callbacks.py`
- Signature: `callback_start(run_id: str = None, challenge_id: str = None, worker_id: str = None, host: str = '127.0.0.1', port: str = None, external_base_url: str = None, token_path: str = None, allow_public_bind: bool = False) -> str`
- Docstring:

```text
Start a local-only web callback listener through the loopback callback daemon.
Default bind is 127.0.0.1. Public binds require allow_public_bind.
External URLs are metadata only and must be supplied manually.
```

### `callback_url`

- Module: `tools/callbacks.py`
- Signature: `callback_url(listener_id: str, external: bool = False, path: str = None) -> str`
- Docstring:

```text
Return a local or manually configured external callback URL for a listener.
No tunnel provider is started.
```

### `callback_wait`

- Module: `tools/callbacks.py`
- Signature: `callback_wait(listener_id: str, timeout_sec: float = 30, pattern: str = None, min_hits: int = 1) -> str`
- Docstring:

```text
Wait for callback hits without busy looping. Pattern matching is performed
over redacted hit summaries.
```

### `cve_lookup`

- Module: `tools/cve_lookup.py`
- Signature: `cve_lookup(cve_id: str) -> str`
- Docstring:

```text
CVE ID로 상세 정보, 공격 벡터, PoC 정보를 조회합니다.
NVD API와 GitHub Advisory를 활용합니다.
```

### `dns_lookup`

- Module: `tools/dns_lookup.py`
- Signature: `dns_lookup(domain: str, record_type: str = 'A', subdomain_wordlist: list = None) -> str`
- Docstring:

```text
DNS 레코드 조회 및 서브도메인 열거를 수행합니다.
record_type: A, AAAA, MX, TXT, CNAME, NS 등
subdomain_wordlist: 서브도메인 열거 시 시도할 단어 목록
```

### `docker_exec`

- Module: `tools/docker_exec.py`
- Signature: `docker_exec(code: str, binary_path: str = None, timeout_seconds: int = 60) -> str`
- Docstring:

```text
Linux CTF 환경(Docker)에서 코드를 실행합니다.
PWN/REV 문제에서 Linux ELF 바이너리 실행, GDB 디버깅, pwntools 익스플로잇에 사용합니다.
/workspace 디렉토리는 호출 간 파일이 유지됩니다.
binary_path: 로컬 바이너리 경로 (지정 시 /workspace/로 복사됨)
code: 실행할 bash 또는 python3 코드
```

### `docker_pwn`

- Module: `tools/docker_exec.py`
- Signature: `docker_pwn(pwntools_script: str, binary_path: str = None, timeout_seconds: int = 60) -> str`
- Docstring:

```text
Docker Linux 환경에서 pwntools 익스플로잇을 실행합니다.
PWN 챌린지 전용. 바이너리를 실제 Linux에서 실행하고 익스플로잇합니다.
완전한 pwntools 스크립트를 작성해 주세요 (from pwn import * 포함).
/workspace 디렉토리는 호출 간 파일이 유지됩니다.
```

### `dreamhack_vm`

- Module: `tools/dreamhack_vm.py`
- Signature: `dreamhack_vm(challenge_id: int, action: str = 'start', session_id: str = '', csrf_token: str = '') -> str`
- Docstring:

```text
Dreamhack 워게임 서버를 제어합니다.
action: start(서버 생성), stop(서버 종료), restart(재시작), status(상태 확인)
session_id: 브라우저 쿠키의 sessionid 값
csrf_token: 브라우저 쿠키의 csrf_token 값
```

### `file_analysis`

- Module: `tools/file_analysis.py`
- Signature: `file_analysis(file_path: str) -> str`
- Docstring:

```text
CTF 문제의 소스코드/설정 파일을 분석합니다.
디렉토리를 지정하면 내부의 텍스트 파일을 읽어 반환합니다.
(venv, __pycache__, node_modules 등 불필요한 디렉토리 자동 제외)
```

### `hash_crack`

- Module: `tools/hash_crack.py`
- Signature: `hash_crack(hash_value: str, wordlist_path: str = os.path.expanduser('~/wordlists/rockyou.txt'), hashcat_mode: str = None, extra_flags: str = '') -> str`
- Docstring:

```text
해시를 식별하고 hashcat으로 크랙을 시도합니다.
hash_value: 크랙할 해시값
wordlist_path: 워드리스트 경로 (기본: rockyou.txt)
hashcat_mode: hashcat 모드 번호 (미입력 시 자동 감지)
```

### `http_request`

- Module: `tools/http_request.py`
- Signature: `http_request(url: str, method: str = 'GET', headers: dict = None, cookies: dict = None, body: str = None, body_hex: str = None, follow_redirects: bool = True, timeout: int = 30) -> str`
- Docstring:

```text
커스텀 HTTP 요청을 보냅니다.
CTF 웹 챌린지에서 커스텀 헤더, 쿠키, 바디를 자유롭게 설정할 때 사용합니다.
body: UTF-8 텍스트 바디
body_hex: hex 인코딩된 바이너리 바디 (예: "4141420a"). body보다 우선.
follow_redirects: False로 설정하면 리다이렉트를 따라가지 않음 (SSRF 등에 유용)
```

### `netcat_interact`

- Module: `tools/netcat_interact.py`
- Signature: `netcat_interact(host: str, port: int, payload: str, timeout: int = 30) -> str`
- Docstring:

```text
CTF nc 서버에 단순 payload를 전송하고 응답을 받습니다.
복잡한 pwntools 상호작용은 docker_pwn을 사용하세요.
payload: 전송할 문자열 (\n으로 줄바꿈)
timeout: 응답 대기 시간 (초)
```

### `port_scan`

- Module: `tools/port_scan.py`
- Signature: `port_scan(target: str, ports: str = '1-1000', flags: str = '-T4') -> str`
- Docstring:

```text
nmap으로 대상 호스트의 포트/서비스를 스캔합니다.
target: IP 또는 도메인
ports: 포트 범위 (기본: 1-1000)
flags: nmap 추가 옵션 (기본: -T4)
```

### `python_exec`

- Module: `tools/python_exec.py`
- Signature: `python_exec(code: str, timeout_seconds: int = 60) -> str`
- Docstring:

```text
Python 코드를 실행하고 결과를 반환합니다.
requests, urllib 등 네트워크 라이브러리 사용 가능.
CTF 공격 페이로드 실행에 활용합니다.
```

### `rsa_ctftool`

- Module: `tools/rsa_ctftool.py`
- Signature: `rsa_ctftool(n: str = None, e: str = None, ciphertext: str = None, publickey_path: str = None, attack: str = 'all', extra_flags: str = '') -> str`
- Docstring:

```text
RSActfTool로 RSA 취약점을 자동 공격합니다.
n, e: 모듈러스와 공개지수 (직접 입력)
ciphertext: 복호화할 암호문 (hex 또는 정수)
publickey_path: PEM 공개키 파일 경로
attack: 사용할 공격 (기본: all - 모든 공격 시도)
```

### `sage_exec`

- Module: `tools/sage_exec.py`
- Signature: `sage_exec(code: str, timeout_seconds: int = 60) -> str`
- Docstring:

```text
SageMath 코드를 실행합니다.
CTF crypto 문제에서 고급 수학 연산(ECC, 격자, 다항식, 소인수분해 등)에 사용합니다.
```

### `session_close`

- Module: `tools/session_tools.py`
- Signature: `session_close(session_id: str, reason: str = 'closed') -> str`
- Docstring:

```text
Close one persistent session and terminate its child process safely.
```

### `session_expect`

- Module: `tools/session_tools.py`
- Signature: `session_expect(session_id: str, patterns: list[str], timeout_ms: int = 1000, max_bytes: int = 8000) -> str`
- Docstring:

```text
Read until one literal pattern appears or timeout expires.
Returns the matched pattern index, timeout status, and bounded output.
```

### `session_list`

- Module: `tools/session_tools.py`
- Signature: `session_list(run_id: str = None, challenge_id: str = None, include_closed: bool = False) -> str`
- Docstring:

```text
List persistent sessions, optionally filtered by run_id or challenge_id.
Closed sessions are hidden unless include_closed is true.
```

### `session_read`

- Module: `tools/session_tools.py`
- Signature: `session_read(session_id: str, timeout_ms: int = 1000, max_bytes: int = 8000) -> str`
- Docstring:

```text
Read bounded output from a persistent session without closing it.
Use timeout_ms and max_bytes to avoid blocking or large transcripts.
```

### `session_start`

- Module: `tools/session_tools.py`
- Signature: `session_start(kind: str, command: str = None, cwd: str = None, run_id: str = None, challenge_id: str = None, worker_id: str = None, host: str = None, port: str = None, image: str = None, workspace: str = None, timeout_ms: int = 1000, env_json: str = None) -> str`
- Docstring:

```text
Start a persistent local session via the loopback-only session daemon.
kind: shell, python, sage, nc, or docker-shell.
Associate run_id/challenge_id when solving a tracked challenge.
```

### `session_write`

- Module: `tools/session_tools.py`
- Signature: `session_write(session_id: str, data: str, newline: bool = True, encoding: str = 'text') -> str`
- Docstring:

```text
Write text or base64 data to a persistent session.
newline defaults to true for menu prompts and REPL commands.
```

### `trivy`

- Module: `tools/trivy_scan.py`
- Signature: `trivy(file_path: str) -> str`
- Docstring:

```text
Trivy를 사용하여 의존성 파일(package.json, requirements.txt 등)의
알려진 취약점(CVE)을 스캔합니다.
```

### `verify_run`

- Module: `tools/verify_run.py`
- Signature: `verify_run(mode: str, run_dir: str = None, command: str = None, cwd: str = None, timeout_sec: int = 30, retries: int = 0, flag_regex: str = None, success_regex: str = None, fail_regex: str = None, session_id: str = None, session_input: str = None, expect: list[str] = None, evidence_text: str = None, callback_listener_id: str = None, callback_pattern: str = None, callback_min_hits: int = 1, target: str = 'unknown', local: bool = False, remote: bool = False, label: str = '', save: bool = True, save_evidence: bool = False, max_output_bytes: int = 8000) -> str`
- Docstring:

```text
Verify solve evidence for a tracked challenge run.
Supports command, session, and manual modes. Output is bounded and redacted;
raw flag values and raw transcripts are not returned by default.
```

### `web_payload_helper`

- Module: `tools/callbacks.py`
- Signature: `web_payload_helper(callback_url: str) -> str`
- Docstring:

```text
Generate simple XSS/SSRF/CSS callback payload snippets for a supplied URL.
This is a helper scaffold only and does not run an exploit or tunnel.
```
