<div align="center">

# ✍️ autoblog

**사진과 가게·상품 정보만 넣으면, 경험 중심의 네이버 블로그 글을 자동으로 써서 게시까지.**

수집 → 초안 → 서식 → 네이버 게시를 한 흐름으로 잇는 데스크톱 프로그램

<br>

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD33?logo=playwright&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Claude·GPT·Gemini-8A63D2)
![Platform](https://img.shields.io/badge/소스_실행-macOS·Windows-informational)
![Status](https://img.shields.io/badge/파이프라인-라이브_검증됨-1f9d57)

</div>

<br>

> [!NOTE]
> **핵심 원칙 — 사용자 경험이 주연, 수집한 사실 정보는 조연.**
> 스펙 나열이 아니라 "내가 겪은 이야기"가 중심인 글을 만든다.

글쓰기·수집·초안 생성은 **클라우드 LLM API**(Claude / GPT / Gemini)로, 네이버 게시는 **내 PC의 실제 브라우저**로 돈다.

---

## 🔄 전체 흐름

```
입력  ·  사진 + 경험 메모 + 가게/상품 URL + 선택(톤·문체·가이드라인)
  │
  ├─ 1️⃣  정보 수집      네이버 검색 API + 플레이스/쇼핑 스크래핑 + 사진 자동분류(Vision)
  │                      → 사실 카드(JSON)
  │
  ├─ 2️⃣  초안 작성      텍스트 LLM이 경험 중심 글 생성
  │                      → 강조·구분선·인용구·스티커·사진 배치 마커 자동 삽입
  │
  ├─ 3️⃣  포맷 & 스타일   모바일 최적화 후처리(줄바꿈 균형, ! → .ᐟ 등)
  │
  └─ 4️⃣  네이버 게시     Smart Editor 자동화(Playwright) → 임시저장 / 발행
```

---

## 🖥️ 화면

일반 유저는 터미널을 쓰지 않는다. `autoblog ui` 한 줄(또는 패키징된 더블클릭 앱)이 로컬 웹 서버를 띄우고 브라우저에 글쓰기 화면을 연다. **npm·node 없이** 파이썬 표준 라이브러리만 쓴다.

| 탭 | 하는 일 |
|:--|:--|
| 📝 **글쓰기** | 가게URL/상품 수집 · 경험 메모 · 사진 다중선택 · 톤/서식 토글 → **초안 생성** → 미리보기(강조·구분선·인용구·스티커 실제 렌더) → 카테고리 선택 → **임시저장** |
| 🩷 **스티커** | 보유 스티커 둘러보기 · ★즐겨찾기 지정 · 비전 자동 태그 · 인앱 태그 편집 |
| 🎨 **서식** | 강조색 프리셋(실제 색·글씨체) · 구분선/인용구 종류 다중선택 |
| ✏️ **프롬프트** | 기본 글쓰기 프롬프트 직접 편집·저장 |
| 🗣️ **문체** | 과거 글을 학습한 문체 프로파일 관리 |
| 🧠 **모델** | 텍스트/비전 모델 선택(프리셋) + API 키 상태 |
| ⚙️ **설정** | 글쓰기 규칙 토글 · API 키 입력 |

> [!TIP]
> **멀티 탭 워크스페이스** — 상단 작업 탭바로 여러 글을 동시에 준비한다. 네이버 접속(불러오기·게시)은 하나의 세션이라 서버 락으로 한 번에 하나씩 직렬 처리한다. 임시저장된 여러 글을 한 번에 선택해 각각 새 탭으로 배치 불러오기도 가능.

---

## 🚀 시작하기

> [!IMPORTANT]
> **소스 실행은 macOS · Windows 공통.** 클라우드 API를 쓰므로 OS 의존성이 없다.
> 더블클릭 배포 앱(PyInstaller)은 **현재 macOS만** 제공 — Windows 패키징은 로드맵.

**1. 설치** (Python 3.12+, [uv](https://docs.astral.sh/uv/))

```bash
uv sync                      # 의존성 설치 (.venv 생성)
uv run playwright install    # 스크래핑/게시용 브라우저 (chromium)
cp .env.example .env         # 아래 키 채우기
```

**2. `.env` 채우기**

```bash
# 네이버 지역검색 API — 가게 식별·주소·좌표 (developers.naver.com, 사실상 무료)
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
NAVER_BLOG_ID=...            # 게시 대상 블로그 ID (첫 실행 시 받아 저장돼도 됨)

# 텍스트/비전 LLM — 쓰는 것만 채우면 됨 (모델은 '모델' 탭에서 선택)
ANTHROPIC_API_KEY=...        # Claude
OPENAI_API_KEY=...           # GPT
GEMINI_API_KEY=...           # Gemini (사진 분석·자동 캡션 기본)
```

> 발급 안내: [docs/naver-search-api.md](docs/naver-search-api.md)

**3. 실행**

```bash
uv run autoblog ui           # 👈 유저 화면(로컬 웹) — 메인 진입점
uv run autoblog doctor       # 환경 점검(API 키 + 검색 API 라이브 호출)
uv run pytest                # 테스트
```

<details>
<summary><b>🧠 모델 설정</b></summary>

<br>

모델명은 코드에 박지 않고 [config/models.yaml](config/models.yaml)에서 읽는다. 프리셋(`claude` / `claude_sonnet` / `gpt` / `gemini`)을 고르거나 텍스트·비전을 독립 선택한다. 비전(사진 분류·상품 상세 전사)은 저렴한 **Gemini Flash**를 기본으로 쓴다.

```bash
uv run autoblog models       # 현재 적용 중인 텍스트/비전 모델 확인
```

</details>

<details>
<summary><b>⌨️ CLI — 파워 유저 / 단계별 실행</b></summary>

<br>

UI가 내부적으로 쓰는 엔진을 명령으로 직접 부를 수 있다.

```bash
# ── 정보 수집 ─────────────────────────────────────────────
uv run autoblog place-url "<플레이스 URL>"                  # 맛집 상세(메뉴/영업시간/평점/리뷰)
uv run autoblog product "상품명"                            # 상품 기본정보(쇼핑 API)
uv run autoblog product "상품명" -i 상세1.png -i 상세2.png    # 상세설명 이미지 Vision 전사
uv run autoblog product "상품명" --text "상세설명 텍스트"     # 텍스트 직접 입력
uv run autoblog classify 사진1.jpg 사진2.jpg               # 사진 자동 분류

# ── 초안 작성 ─────────────────────────────────────────────
uv run autoblog draft "경험 메모" --place-url "<URL>" -p 사진1.jpg       # 초안 + 사진 배치
uv run autoblog draft "경험 메모" --product "상품명" --tone "친근한 반말로"
uv run autoblog style 과거글1.txt 과거글2.txt -o 내문체.txt             # 과거 글로 문체 추출
uv run autoblog draft "메모" --place-url "<URL>" --style-file 내문체.txt --emphasis

# ── 수집 → 초안 → 게시까지 한 번에 (기본 임시저장, --submit이면 발행) ──
uv run autoblog post "경험 메모" --place-url "<URL>" -p 사진1.jpg
uv run autoblog post "경험 메모" --place-url "<URL>" --dry-run          # 브라우저 없이 초안·플랜만

# ── 스티커 카탈로그 (한 번 세팅하면 초안이 자동으로 골라 씀) ──────────
uv run autoblog stickers pull      # 보유 스티커 전부 이미지로 저장 + 증분 병합
uv run autoblog stickers review    # 로컬 웹에서 ★즐겨찾기 지정·태그 검수
uv run autoblog stickers label     # 즐겨찾기한 것만 비전 자동 태그
```

글쓰기 스타일은 [config/prompts/default.md](config/prompts/default.md)를 편집(또는 `--prompt-file`)한다.

</details>

---

## 📁 프로젝트 구조

```
config/
  models.yaml            # 텍스트/비전 모델 프리셋 (모델명은 코드에 박지 않음)
  prompts/default.md     # 기본 글쓰기 프롬프트 (사용자 편집)
  emphasis.yaml          # 강조 배정 설정 (순환 풀·고정 매핑)
  stickers.yaml          # 스티커 검수 카탈로그(태그·즐겨찾기)
  fonts/                 # 미리보기용 웹폰트(에디터와 같은 se-* 패밀리)

src/autoblog/
  config.py              # 설정·환경변수·모델 프리셋 로딩 (자산/유저데이터 경로 분리)
  cli.py                 # CLI 엔트리 (ui/doctor/place-url/product/draft/post/stickers)
  webui.py               # 유저 화면 — 로컬 웹(멀티 탭 워크스페이스)
  llm.py                 # 텍스트 LLM 공통 (Claude/GPT/Gemini 라우팅)
  vision.py              # Vision LLM (Gemini 멀티모달 — 사진 분류·상품 상세)
  pipeline.py            # 수집→초안→게시 플랜 조립

  collect/               # 1️⃣ 정보 수집
    selectors.py         #   스크래핑 셀렉터 집결지 (구조 변경 시 여기만)
    link.py              #   URL 타입 감지 → 전략 분기
    place.py             #   맛집: 검색 API + 플레이스 상세(apollo state)
    place_detail.py      #   플레이스 URL → 메뉴/영업시간/리뷰/정보 추출
    product.py           #   상품: 쇼핑 검색 API + 이미지/텍스트 상세
    photos.py            #   입력 사진 Vision 자동 분류
    blog_posts.py        #   임시저장 글 목록/불러오기

  draft/                 # 2️⃣ 초안 작성
    prompts.py / prompt.py       #   베이스 프롬프트 로딩 + 계층 조립
    rules.py / style.py / persona.py / guideline.py   #   규칙·문체·페르소나·체크리스트
    postprocess.py       #   결정적 포맷 규칙(! → .ᐟ, 줄바꿈 균형)
    generate.py          #   텍스트 LLM 호출 → 초안(+마커 자동)

  publish/               # 4️⃣ 네이버 게시
    editor.py            #   Smart Editor 자동화(로그인·제목·본문·이미지·임시저장·발행)
    plan.py              #   마커 → 게시 플랜(블록) 변환
    emphasis.py          #   서식/강조(파워 단축키, 순환 풀/고정 매핑)
    stickers.py / sticker_review.py   #   스티커 카탈로그·검수 UI

packaging/               # 데스크톱 앱 패키징 (PyInstaller + 번들 Chromium)
  app_entry.py / autoblog.spec / build_macos.sh
docs/                    # 검색 API 발급, SaaS 아키텍처, 에이전트 프로토콜
tests/
```

---

## ✅ 지금까지 (완성된 것)

전 파이프라인이 **라이브 검증** 완료 — 실제 네이버 블로그에 자동 게시까지 동작한다.

- **정보 수집** — 맛집(메뉴/영업시간/평점/리뷰/소개/편의시설), 상품(쇼핑 API + 이미지·텍스트 상세), 사진 자동 분류
- **초안 작성** — 편집 가능한 베이스 프롬프트, 문체 학습, 페르소나, 가이드라인+체크리스트, 후처리. 초안 LLM이 강조·구분선·인용구·스티커·사진 배치 **마커를 자동 생성**
- **게시** — Smart Editor 자동화: 자동 로그인, 제목/본문, 강조 색상(커스텀 hex·저장 유지), 카테고리(유저별 동적), 이미지·영상·콜라주, 구분선/인용구, 스티커, 임시저장/발행
- **불러오기 & in-place 재배치** — 임시저장된 글을 다시 불러와 사진 사이에 텍스트를 끼워넣고, 영상·콜라주는 고정한 채 사진만 플랜 순서대로 재배치
- **유저 화면** — 7탭 로컬 웹 UI + 멀티 탭 워크스페이스(여러 글 동시 준비, 네이버 접속은 락으로 직렬화)
- **패키징** — macOS PyInstaller 골격 완료(자산/유저데이터 경로 분리, 번들 Chromium E2E 게시 검증)

## 🗺️ 로드맵

- [ ] `.app` / `.dmg` 포장 + 코드서명·공증
- [ ] Windows 빌드
- [ ] 첫 실행 온보딩(네이버 로그인, API 키 입력)
- [ ] SaaS 배포 검토 — 웹은 클라우드, 네이버 게시만 로컬 도우미 ([docs/saas-architecture.md](docs/saas-architecture.md))

---

<div align="center">
<sub>네이버 게시는 공식 API가 없어 실제 브라우저 자동화로 동작한다. 개인 블로그 운영 보조 용도로 사용하세요.</sub>
</div>
</content>
