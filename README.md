# autoblog — 로컬 LLM 기반 블로그 자동 작성 서비스

사진과 가게/상품 정보를 입력하면, **사용자 경험을 중심**으로 한 네이버 블로그 글을
로컬 LLM(Ollama)으로 자동 생성하고 게시하는 데스크톱 프로그램.
모든 처리는 사용자 PC에서 로컬로 수행한다.

> 현재 저장소 상태: **1단계 · 정보 수집 모듈** 백엔드 스캐폴드.
> Electron 데스크톱 셸은 이후 단계(§7)에서 이 백엔드를 자식 프로세스로 감싼다.

## 전체 흐름

```
입력(사진 + 경험 메모 + 정보 소스 + 선택: 가이드라인)
  → 1단계 정보 수집(Vision) → 사실 카드(JSON)
  → [모델 스왑] 2단계 초안 작성(텍스트 LLM)
  → 3단계 포맷 & 스타일(모바일 최적화)
  → 4단계 네이버 블로그 자동 게시(Playwright)
```

핵심 원칙: **사용자 경험이 주연, 수집된 사실 정보는 조연.**

## 프로젝트 구조

```
config/
  models.yaml          # GPU 티어별 모델 프리셋 (모델명은 코드에 박지 않음)
src/autoblog/
  config.py            # 설정·환경변수 로딩
  cli.py               # 백엔드 CLI 엔트리 (Electron이 호출)
  collect/             # 1단계 · 정보 수집
    fact_card.py       #   사실 카드 표준 스키마
    selectors.py       #   스크래핑 셀렉터 집결지 (구조 변경 시 여기만 수정)
    link.py            #   URL 타입 감지 → 전략 분기
    place.py           #   맛집: 검색 API + 플레이스 상세(apollo)
    place_detail.py    #   플레이스 URL → 메뉴/영업시간/리뷰/정보 추출
    product.py         #   상품: 쇼핑 검색 API + 이미지 Vision 상세
  vision.py            # Vision LLM 연동 지점 (Ollama, 구현 예정)
tests/
```

## 개발 환경 세팅 (mac)

```bash
uv sync                      # 의존성 설치 (.venv 생성)
uv run playwright install    # 스크래핑/게시용 브라우저 (chromium)
cp .env.example .env         # 네이버 검색 API 키 입력 (발급: docs/naver-search-api.md)

# Vision LLM (상품 이미지 분석·사진 분류)
brew install ollama          # macOS. Windows는 ollama.com 설치 파일
ollama serve &               # 로컬 서버 기동
ollama pull qwen2.5vl:7b     # 비전 모델 (~6GB, config/models.yaml의 vision 모델)
```

### 사용

```bash
uv run autoblog doctor              # 환경 점검
uv run autoblog models --tier 8gb   # 선택 프리셋의 vision/text 모델 확인
uv run autoblog place-url "<플레이스 URL>"  # 맛집 상세(메뉴/영업시간/리뷰)
uv run autoblog product "상품명"                  # 상품 기본정보(쇼핑 API)
uv run autoblog product "상품명" --image 상세1.png --image 상세2.png  # 이미지 Vision 전사
uv run autoblog product "상품명" --text "상세설명 텍스트"  # 텍스트 직접 입력
# --image 와 --text 는 둘 다/각각 선택적, 본문이 합쳐짐
uv run pytest                       # 테스트
```

## 다음 단계

- [ ] 플레이스 스크래핑 셀렉터 확정 → `place.scrape_place` 구현
- [ ] 상품 수집(`product.py`) + 이미지형 상세설명 Vision 처리
- [ ] 2단계 초안 작성 프롬프트 엔진
- [ ] 4단계 Smart Editor 자동 게시
- [ ] Electron 셸 + 첫 실행 온보딩(Ollama/모델 자동 설치)
