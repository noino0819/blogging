"""맛집 — 네이버 플레이스 수집 (기획서 §3.1).

두 경로:
- collect_place_from_url(url): 사용자가 붙여넣은 플레이스 URL → 상세 추출(권장).
  메뉴/가격/평점/좌표 등은 place_detail.py가 __APOLLO_STATE__ 파싱으로 얻는다.
- collect_place(query): 검색 API로 가게 식별만(주소/좌표/전화). 자동 placeId
  검색은 캡차/IP 차단에 막혀, 상세는 URL 경로를 권장.
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


def ping_search_api() -> tuple[bool, str]:
    """검색 API 키가 실제로 동작하는지 라이브로 점검.

    반환: (성공여부, 메시지). doctor 명령에서 연동 검증에 사용.
    """
    env = load_env()
    if not env.has_naver_api:
        return False, "키 미설정 (.env)"
    try:
        resp = requests.get(
            _SEARCH_URL,
            params={"query": "스타벅스", "display": 1},
            headers={
                "X-Naver-Client-Id": env.naver_client_id or "",
                "X-Naver-Client-Secret": env.naver_client_secret or "",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"네트워크 오류: {exc}"
    if resp.status_code == 200:
        return True, "OK"
    if resp.status_code == 401:
        return False, "401 인증 실패 — Client ID/Secret 확인"
    return False, f"HTTP {resp.status_code}: {resp.text[:120]}"


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


def collect_place_from_url(url: str) -> FactCard:
    """사용자가 붙여넣은 플레이스 URL → 상세 사실 카드 (기획서 §3.1, 권장 경로).

    Apollo state 파싱으로 메뉴/가격/평점/좌표/주소를 추출. 추출 실패·IP 차단 시
    경고와 함께 가능한 정보만으로 fallback.
    """
    from autoblog.collect.place_detail import (
        extract_apollo_state,
        fetch_place_html,
        is_rate_limited,
        parse_place_detail,
        resolve_place_id,
    )

    final_url, html_text = fetch_place_html(url)
    place_id = resolve_place_id(final_url) or resolve_place_id(url)
    card = FactCard(type=CardType.place, sources=[Source.scrape])

    if place_id is None:
        card.is_fallback = True
        card.warnings.append(f"placeId를 URL에서 찾지 못함: {final_url}")
        return card

    state = extract_apollo_state(html_text)
    facts = parse_place_detail(state, place_id) if state else None
    if facts is None or not facts.name:
        card.is_fallback = True
        if is_rate_limited(html_text):
            card.warnings.append("네이버 IP 차단(과도한 접근) — 잠시 후 재시도")
        else:
            card.warnings.append("상세 데이터 추출 실패 (페이지 구조 변경 가능)")
        return card

    card.place = facts
    return card


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
