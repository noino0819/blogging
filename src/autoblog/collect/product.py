"""상품 — 네이버 쇼핑 검색 API 기본정보 + 사용자 이미지 Vision 상세 (기획서 §3.2).

스마트스토어/brand.naver 상품 페이지는 네이버 WTM 봇 챌린지로 직접 스크래핑이
사실상 불가하다. 그래서:
- 기본정보(상품명/가격/브랜드/이미지/카테고리)는 쇼핑 검색 API(공식·무료)로 수집.
- 이미지형 상세설명(재질/크기/사용법/주의사항)은 사용자가 제공한 상세 이미지를
  Vision LLM으로 추출(autoblog.vision). 즉 우리가 상품 페이지를 긁지 않으므로
  WTM 우회가 필요 없다.
"""

from __future__ import annotations

import html
import re

import requests

from autoblog.collect.fact_card import CardType, FactCard, ProductFacts, Source
from autoblog.config import load_env

_SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text)).strip()


def _won(lprice: str | None) -> str | None:
    if not lprice:
        return None
    try:
        return f"{int(lprice):,}원"
    except ValueError:
        return lprice


def parse_shop_item(item: dict) -> ProductFacts:
    """쇼핑 검색 API item → ProductFacts."""
    cats = [item.get(f"category{i}") for i in range(1, 5)]
    category = ">".join(c for c in cats if c) or None
    return ProductFacts(
        name=_strip(item.get("title", "")),
        price=_won(item.get("lprice")),
        brand=item.get("brand") or None,
        maker=item.get("maker") or None,
        category=category,
        mall_name=item.get("mallName") or None,
        image=item.get("image") or None,
        product_url=item.get("link") or None,
    )


def search_product(query: str, display: int = 5) -> list[ProductFacts]:
    """쇼핑 검색 API로 상품 기본정보 목록 조회."""
    env = load_env()
    if not env.has_naver_api:
        return []
    resp = requests.get(
        _SHOP_URL,
        params={"query": query, "display": display},
        headers={
            "X-Naver-Client-Id": env.naver_client_id or "",
            "X-Naver-Client-Secret": env.naver_client_secret or "",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return [parse_shop_item(it) for it in resp.json().get("items", [])]


def collect_product(query: str, detail_images: list[str] | None = None) -> FactCard:
    """상품 사실 카드 조립.

    query로 쇼핑 API 기본정보(최상위 결과)를 잡고, detail_images가 주어지면
    Vision으로 상세 스펙을 추출해 병합. 이미지가 없으면 기본정보만으로 구성.
    """
    results = search_product(query, display=5)
    if not results:
        return FactCard(
            type=CardType.product,
            sources=[Source.fallback],
            is_fallback=True,
            warnings=["네이버 검색 API 키 미설정 또는 검색 결과 없음"],
        )

    facts = results[0]
    card = FactCard(type=CardType.product, sources=[Source.search_api], product=facts)

    if detail_images:
        facts.detail_images = list(detail_images)
        from autoblog.vision import VisionUnavailable, extract_product_specs

        try:
            facts.specs = extract_product_specs(detail_images)
            card.sources.append(Source.vision)
        except VisionUnavailable as exc:
            card.warnings.append(f"Vision 미연동 — 상세 스펙 생략: {exc}")

    return card
