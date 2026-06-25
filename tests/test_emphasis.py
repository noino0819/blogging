import json
from pathlib import Path

from autoblog.publish.emphasis import (
    DEFAULT_STYLES,
    CyclingPool,
    EmphasisConfig,
    EmphasisRequest,
    assign_emphasis,
    load_emphasis_config,
    load_power_shortcuts,
    parse_emphasis_markup,
    parse_style,
)

FIXTURE = Path(__file__).parent / "fixtures" / "power_shortcuts.json"


def test_load_real_power_shortcuts_export():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    styles = load_power_shortcuts(data)

    # 단축키 1: actions=[textColor,fontFamily,fontSize] → 배경은 미적용
    s1 = styles[1]
    assert s1.text_color == "#eb7d7d"
    assert s1.font_family == "nanumuriddalsongeulssi"
    assert s1.font_size == "16"
    assert s1.background_color is None  # 값은 있으나 actions에 없음

    # 단축키 7: actions=[textColor,backgroundColor]
    assert styles[7].text_color == "#065F46"
    assert styles[7].background_color == "#D1FAE5"
    assert styles[7].font_family is None

    # 단축키 6: editorMode=insert(인용 삽입) → 텍스트 강조에서 제외
    assert 6 not in styles


def test_parse_style_lenient_keys():
    # 키 이름이 달라도 흡수
    s1 = parse_style({"textColor": "#FF0000", "backgroundColor": "#FFFF00", "fontSize": "16"})
    assert s1.text_color == "#FF0000" and s1.background_color == "#FFFF00" and s1.font_size == "16"
    s2 = parse_style({"color": "#00FF00", "bg": "#000", "font": "굴림"})
    assert s2.text_color == "#00FF00" and s2.background_color == "#000" and s2.font_family == "굴림"


def test_load_power_shortcuts_formats():
    # 리스트 형식
    by_list = load_power_shortcuts([{"textColor": "#111"}, {"textColor": "#222"}])
    assert by_list[1].text_color == "#111" and by_list[2].text_color == "#222"
    # 딕셔너리 형식
    by_dict = load_power_shortcuts({"7": {"fontColor": "#FB8C00", "bold": True}})
    assert by_dict[7].text_color == "#FB8C00" and by_dict[7].bold is True
    # shortcuts 래핑
    wrapped = load_power_shortcuts({"shortcuts": [{"color": "#abc"}]})
    assert wrapped[1].text_color == "#abc"


def test_cycling_pool_rotates_without_consecutive():
    pool = CyclingPool([1, 3, 5])
    seq = [pool.next() for _ in range(7)]
    assert seq == [1, 3, 5, 1, 3, 5, 1]  # 순환
    assert all(a != b for a, b in zip(seq, seq[1:]))  # 연속 중복 없음
    assert CyclingPool([]).next() is None


def test_assign_emphasis_cycle_and_fixed():
    config = EmphasisConfig(cycling_pool=[1, 3, 5], fixed_map={"price": 7, "name": 4})
    reqs = [
        EmphasisRequest(text="정말 인상적이었어요", role="cycle"),
        EmphasisRequest(text="13,000원", role="price"),
        EmphasisRequest(text="분위기가 좋았다", role="cycle"),
        EmphasisRequest(text="수지골남원추어탕", role="name"),
        EmphasisRequest(text="추천해요", role="cycle"),
    ]
    spans = assign_emphasis(reqs, DEFAULT_STYLES, config)
    ids = [s.preset_id for s in spans]
    # 고정 매핑은 항상 동일, 순환은 1→3→5
    assert ids == [1, 7, 3, 4, 5]
    # 가격 스타일은 7번 프리셋(주황 볼드)
    price_span = spans[1]
    assert price_span.style == DEFAULT_STYLES[7]


def test_parse_emphasis_markup():
    raw = "오늘 <<name:수지골>>에서 <<price:13,000원>> 추어탕을 먹었는데 <<cycle:정말 좋았어요>>."
    clean, reqs = parse_emphasis_markup(raw)
    # 마킹은 제거되고 안쪽 텍스트는 본문에 그대로 남음
    assert clean == "오늘 수지골에서 13,000원 추어탕을 먹었는데 정말 좋았어요."
    assert [(r.role, r.text) for r in reqs] == [
        ("name", "수지골"),
        ("price", "13,000원"),
        ("cycle", "정말 좋았어요"),
    ]
    # 마킹 없으면 원문 유지 + 빈 목록
    assert parse_emphasis_markup("강조 없음") == ("강조 없음", [])


def test_load_emphasis_config_from_file():
    cfg = load_emphasis_config()  # config/emphasis.yaml
    assert cfg.cycling_pool  # 비어있지 않음
    assert "price" in cfg.fixed_map and "name" in cfg.fixed_map
