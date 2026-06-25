"""사실 카드(FactCard) — 정보 수집 결과의 표준 형식.

맛집/상품 두 유형이 공통으로 채워 넣는 구조화 데이터.
- 초안 작성 시 '조연'으로 투입 (없는 사실을 지어내지 않기 위한 근거).
- 출처(source)와 신뢰도(confidence)를 함께 들고 다녀 fallback 여부를 추적한다.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CardType(str, Enum):
    place = "place"  # 맛집 후기
    product = "product"  # 상품 리뷰


class Source(str, Enum):
    search_api = "search_api"  # 네이버 검색 API
    scrape = "scrape"  # Playwright 스크래핑
    vision = "vision"  # 이미지형 상세설명 Vision 추출
    web = "web"  # 일반 웹페이지 크롤링
    fallback = "fallback"  # 스크래핑 실패 → 최소 정보


class MenuItem(BaseModel):
    name: str
    price: str | None = None
    description: str | None = None  # 메뉴 설명글 (메뉴 탭에만 실림)
    recommend: bool = False  # 대표/추천 메뉴 여부
    image: str | None = None  # 대표 이미지 URL


class ReviewKeyword(BaseModel):
    """방문자가 많이 고른 감상 키워드 (예: '음식이 맛있어요')."""

    name: str
    count: int


class ReviewSnippet(BaseModel):
    """방문자 리뷰 한 건 — 초안의 '경험' 보조 재료."""

    body: str
    keywords: list[str] = Field(default_factory=list)
    visited: str | None = None
    visit_count: int | None = None


class PlaceFacts(BaseModel):
    """맛집 — 네이버 플레이스 사실 정보."""

    name: str
    category: str | None = None
    address: str | None = None
    road_address: str | None = None
    phone: str | None = None
    lat: float | None = None
    lng: float | None = None
    business_hours: str | None = None
    rating: float | None = None
    menus: list[MenuItem] = Field(default_factory=list)
    # 정보 탭 (홈 탭 state에 함께 실림)
    description: str | None = None  # 사장님 소개글
    micro_reviews: list[str] = Field(default_factory=list)  # 대표 한줄평
    conveniences: list[str] = Field(default_factory=list)  # 편의시설
    payment_info: list[str] = Field(default_factory=list)  # 결제수단
    # 방문자 리뷰(경험 재료) — 리뷰 탭에서 수집
    review_keywords: list[ReviewKeyword] = Field(default_factory=list)
    reviews: list[ReviewSnippet] = Field(default_factory=list)
    place_url: str | None = None


class ProductSpec(BaseModel):
    key: str  # 예: 재질, 크기, 사용법, 주의사항
    value: str


class ProductFacts(BaseModel):
    """상품 사실 정보.

    스마트스토어 상품 페이지는 WTM 봇 차단으로 직접 스크래핑 불가 →
    기본정보는 네이버 쇼핑 검색 API, 상세 스펙은 사용자 제공 이미지의 Vision 추출.
    """

    name: str
    price: str | None = None  # 최저가(lprice)
    brand: str | None = None
    maker: str | None = None
    category: str | None = None  # category1>2>3>4 결합
    mall_name: str | None = None
    image: str | None = None  # 대표 이미지 URL
    product_url: str | None = None
    # 상세설명 — 사용자 제공 이미지(Vision 전사) 또는 텍스트 입력
    detail_text: str | None = None  # 상세설명 본문(이미지 전사 또는 직접 입력)
    selling_points: list[str] = Field(default_factory=list)  # 핵심 셀링포인트/특징
    specs: list[ProductSpec] = Field(default_factory=list)  # 스펙(재질/크기 등, 있을 때)
    detail_images: list[str] = Field(default_factory=list)  # 사용자 제공 상세 이미지 경로


class FactCard(BaseModel):
    """수집 결과 표준 컨테이너."""

    type: CardType
    sources: list[Source] = Field(default_factory=list)
    is_fallback: bool = False
    place: PlaceFacts | None = None
    product: ProductFacts | None = None
    # 분류된 사진 경로 (분류 결과는 Vision 단계에서 채움)
    photos: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
