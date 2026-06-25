from pathlib import Path

from autoblog.collect.place_detail import (
    extract_apollo_state,
    parse_place_detail,
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


def test_extract_empty_when_absent():
    assert extract_apollo_state("<html><body>no state</body></html>") == {}
