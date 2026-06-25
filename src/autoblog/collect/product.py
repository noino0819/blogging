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


def download_image(url: str) -> str:
    """이미지 URL을 임시 파일로 내려받아 경로 반환. 쇼핑 CDN은 WTM 없이 접근 가능."""
    import tempfile

    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()
    suffix = ".png" if "png" in resp.headers.get("content-type", "") else ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(resp.content)
    tmp.close()
    return tmp.name


def collect_product(
    query: str,
    detail_images: list[str] | None = None,
    vision_on_main: bool = False,
) -> FactCard:
    """상품 사실 카드 조립.

    query로 쇼핑 API 기본정보(최상위 결과)를 잡고, 이미지가 있으면 Vision으로
    상세 스펙을 추출해 병합한다.
    - detail_images: 사용자가 제공한 상세설명 이미지(스펙 텍스트가 풍부, 권장).
    - vision_on_main=True: 쇼핑 API의 메인 이미지도 내려받아 Vision에 포함
      (시각적 묘사 위주, 스펙 텍스트는 제한적).
    상세 이미지 URL은 쇼핑 API가 주지 않으므로(상품 페이지는 WTM 차단) 별도 입력해야 한다.
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

    images = list(detail_images or [])
    if vision_on_main and facts.image:
        try:
            images.insert(0, download_image(facts.image))
        except Exception as exc:  # noqa: BLE001 - 메인 이미지 다운로드 실패는 비치명적
            card.warnings.append(f"메인 이미지 다운로드 실패: {exc}")

    if images:
        facts.detail_images = list(detail_images or [])
        from autoblog.vision import VisionUnavailable, extract_product_specs

        context = " / ".join(c for c in (facts.name, facts.category) if c)
        try:
            facts.specs = extract_product_specs(images, context=context)
            card.sources.append(Source.vision)
        except VisionUnavailable as exc:
            card.warnings.append(f"Vision 미연동 — 상세 스펙 생략: {exc}")
        except Exception as exc:  # noqa: BLE001 - 상세는 보조라 실패해도 기본정보 유지
            card.warnings.append(f"Vision 상세 추출 실패: {exc}")

    return card
