from pathlib import Path

from autoblog.collect.place_detail import (
    extract_apollo_state,
    parse_place_detail,
    parse_visitor_reviews,
    resolve_place_id,
)

FIXTURE = Path(__file__).parent / "fixtures" / "place_detail.html"
PLACE_ID = "2077697260"


def test_resolve_place_id():
    assert resolve_place_id("https://m.place.naver.com/restaurant/2077697260/home") == PLACE_ID
    assert resolve_place_id("https://naver.me/xONmtkQc") is None  # 단축링크는 리다이렉트 후 해석


def test_extract_and_parse_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    state = extract_apollo_state(html)
    assert state, "apollo state가 추출돼야 함"

    facts = parse_place_detail(state, PLACE_ID)
    assert facts is not None
    assert facts.name == "언제나, 초밥"
    assert facts.category == "초밥,롤"
    assert facts.road_address and "용인시" in facts.road_address
    assert facts.lat and 37.0 < facts.lat < 38.0  # WGS84
    assert facts.lng and 127.0 < facts.lng < 128.0
    assert len(facts.menus) == 8
    # 가격 포맷 + 추천 메뉴 존재
    names = {m.name: m.price for m in facts.menus}
    assert names["오늘의초밥(11p)"] == "15,900원"


def test_business_hours_parsing():
    html = (FIXTURE.parent / "place_detail_hours.html").read_text(encoding="utf-8")
    state = extract_apollo_state(html)
    facts = parse_place_detail(state, "32056494")
    assert facts is not None
    # 연속 동일 시간 요일 묶기 + 휴무 표기
    assert facts.business_hours == "목~화 10:30~21:00 (L.O. 20:30) / 수 정기휴무 (매주 수요일)"


def test_info_fields_parsing():
    html = (FIXTURE.parent / "place_detail_hours.html").read_text(encoding="utf-8")
    facts = parse_place_detail(extract_apollo_state(html), "32056494")
    assert facts is not None
    assert facts.description and "2004년" in facts.description  # 사장님 소개글
    assert "주차" in facts.conveniences and "예약" in facts.conveniences
    assert any("지역화폐" in p for p in facts.payment_info)
    assert facts.micro_reviews == ["동네 주민이 인정한 건강한 추어탕"]


def test_business_hours_none_when_absent():
    # hours 픽스처가 아닌 기본 픽스처에는 ROOT_QUERY 영업시간이 없음
    state = extract_apollo_state(FIXTURE.read_text(encoding="utf-8"))
    facts = parse_place_detail(state, PLACE_ID)
    assert facts is not None
    assert facts.business_hours is None


def test_visitor_reviews_parsing():
    html = (FIXTURE.parent / "place_reviews.html").read_text(encoding="utf-8")
    state = extract_apollo_state(html)
    keywords, snippets = parse_visitor_reviews(state, limit=5)

    # 키워드 빈도 집계 (가장 많이 고른 것이 맨 앞)
    assert keywords[0].name == "음식이 맛있어요"
    assert keywords[0].count >= keywords[-1].count
    # 의미있는 본문만(한글 10자 이상) 수집
    assert snippets
    assert all(len(s.body) >= 10 for s in snippets)
    assert "추어탕" in snippets[0].body
    assert snippets[0].visited  # 방문일 보존


def test_extract_empty_when_absent():
    assert extract_apollo_state("<html><body>no state</body></html>") == {}
