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
    place_url: str | None = None


class ProductSpec(BaseModel):
    key: str  # 예: 재질, 크기, 사용법, 주의사항
    value: str


class ProductFacts(BaseModel):
    """상품 — 상품 페이지 사실 정보."""

    name: str
    price: str | None = None
    brand: str | None = None
    specs: list[ProductSpec] = Field(default_factory=list)
    product_url: str | None = None


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
