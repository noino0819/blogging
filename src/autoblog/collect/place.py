"""맛집 — 네이버 플레이스 하이브리드 수집 (기획서 §3.1).

흐름: 검색 API로 가게 식별(이름/주소/좌표/전화) → 플레이스 URL을
Playwright로 스크래핑(영업시간/메뉴/가격/평점) → FactCard 병합.
스크래핑 실패 시 검색 API 정보만으로 최소 사실 카드(fallback).

이 파일에서 '검색 API' 부분은 실제 동작 구현, '스크래핑' 부분은 셀렉터
확정 전까지 자리표시자(NotImplemented)로 둔다.
"""

from __future__ import annotations

import html
import re

import requests

from autoblog.config import load_env
from autoblog.collect.fact_card import CardType, FactCard, PlaceFacts, Source

_SEARCH_URL = "https://openapi.naver.com/v1/search/local.json"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text)).strip()


def search_place(query: str) -> PlaceFacts | None:
    """네이버 지역검색 API로 가게 식별.

    제약: 결과 5개·start=1 고정(2020.07~), 상세정보 없음. 식별 + 주소/좌표/전화만.
    좌표는 KATECH(TM128)으로 내려오므로 표시는 가능하나 WGS84 변환은 별도.
    """
    env = load_env()
    if not env.has_naver_api:
        return None

    resp = requests.get(
        _SEARCH_URL,
        params={"query": query, "display": 5},
        headers={
            "X-Naver-Client-Id": env.naver_client_id or "",
            "X-Naver-Client-Secret": env.naver_client_secret or "",
        },
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return None

    top = items[0]
    return PlaceFacts(
        name=_strip(top.get("title", "")),
        category=top.get("category") or None,
        address=top.get("address") or None,
        road_address=top.get("roadAddress") or None,
        phone=top.get("telephone") or None,
        place_url=top.get("link") or None,
    )


def scrape_place(place_url: str) -> dict:
    """Playwright로 영업시간/메뉴/가격/평점 스크래핑.

    셀렉터는 collect.selectors.PLACE 한 곳에서 관리(§3.1).
    TODO: 실제 플레이스 페이지 구조 확인 후 구현.
    """
    raise NotImplementedError("플레이스 스크래핑은 셀렉터 확정 후 구현 예정")


def collect_place(query: str) -> FactCard:
    """맛집 사실 카드 조립 (검색 API → 스크래핑 → 병합, 실패 시 fallback)."""
    facts = search_place(query)
    if facts is None:
        return FactCard(
            type=CardType.place,
            sources=[Source.fallback],
            is_fallback=True,
            warnings=["네이버 검색 API 키 미설정 또는 검색 결과 없음"],
        )

    card = FactCard(type=CardType.place, sources=[Source.search_api], place=facts)

    if facts.place_url:
        try:
            detail = scrape_place(facts.place_url)
            facts.business_hours = detail.get("business_hours")
            facts.rating = detail.get("rating")
            facts.menus = detail.get("menus", [])
            card.sources.append(Source.scrape)
        except NotImplementedError:
            card.is_fallback = True
            card.warnings.append("스크래핑 미구현 — 검색 API 정보만으로 구성")
        except Exception as exc:  # noqa: BLE001 - fallback 경로
            card.is_fallback = True
            card.warnings.append(f"스크래핑 실패: {exc}")

    return card
