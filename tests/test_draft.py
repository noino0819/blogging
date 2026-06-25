from autoblog.collect.fact_card import CardType, FactCard, MenuItem, PlaceFacts
from autoblog.draft.guideline import Guidelines, check_guidelines
from autoblog.draft.prompt import build_system_prompt, build_user_prompt, render_fact_card
from autoblog.draft.prompts import load_base_prompt
from autoblog.draft.rules import CommonRules


def _place_card():
    return FactCard(
        type=CardType.place,
        place=PlaceFacts(
            name="언제나 초밥",
            category="초밥,롤",
            road_address="경기 용인시 수지구 손곡로 89",
            business_hours="매일 11:00~21:00",
            menus=[MenuItem(name="모둠초밥", price="12,900원")],
        ),
    )


def test_rules_default_and_toggle():
    default = CommonRules()
    frags = default.active_fragments()
    assert len(frags) == 3  # mobile/authenticity/structure 기본 켜짐
    # seo/emoji 켜면 5개
    assert len(CommonRules(seo=True, emoji=True).active_fragments()) == 5


def test_render_fact_card_place():
    text = render_fact_card(_place_card())
    assert "언제나 초밥" in text
    assert "모둠초밥(12,900원)" in text
    assert "매일 11:00~21:00" in text


def test_system_prompt_hierarchy():
    # 가이드라인은 맨 위(최우선), 그 아래 베이스 프롬프트
    base = "베이스 프롬프트 본문"
    g = Guidelines(required_keywords=["수지맛집"], min_chars=500)
    sys = build_system_prompt(base, guidelines=g)
    assert sys.index("최우선 제약") < sys.index(base)
    # 추가 문체 지시는 베이스 뒤
    from autoblog.draft.style import StyleProfile

    sys2 = build_system_prompt(base, style=StyleProfile(tone="반말로"))
    assert sys2.index(base) < sys2.index("추가 문체 지시")


def test_load_base_prompt_strips_meta():
    # 상단 메타(제목+안내, 첫 '---' 이전)는 제거되고 역할 설정부터 시작
    base = load_base_prompt()
    assert "## 역할 설정" in base
    assert "이 파일은 초안 작성" not in base  # 메타 안내 제거됨


def test_user_prompt_experience_is_lead():
    user = build_user_prompt(_place_card(), "비 오는 날 들렀는데 따뜻했다")
    assert user.index("나의 경험") < user.index("참고 정보")
    assert "비 오는 날" in user
    assert "언급하거나 인용하지 마세요" in user  # 라벨 누수 방지 지시


def test_guideline_checklist():
    g = Guidelines(
        required_keywords=["수지맛집", "초밥"],
        required_hashtags=["#협찬"],
        forbidden_expressions=["강력추천"],
        min_chars=20,
    )
    draft = "수지맛집 초밥 다녀왔어요. 정말 좋았습니다. #협찬"
    checks = check_guidelines(draft, g)
    by_item = {c.item: c.ok for c in checks}
    assert by_item["키워드 '수지맛집'"] is True
    assert by_item["키워드 '초밥'"] is True
    assert by_item["해시태그 '#협찬'"] is True
    assert by_item["금지어 '강력추천' 미포함"] is True  # 없으므로 통과
    # 글자수 미달 케이스
    short = check_guidelines("짧음", Guidelines(min_chars=100))
    assert short[0].ok is False


def test_guidelines_empty_is_ignored():
    assert Guidelines().is_empty()
    assert Guidelines().as_prompt() is None


def test_enforce_format():
    from autoblog.draft.postprocess import enforce_format

    raw = "### 제목\n\n- 항목 하나\n맛있어요! 또 가야지~ 😊✨"
    out = enforce_format(raw)
    assert "###" not in out
    assert "\n- " not in out and not out.startswith("- ")
    assert "항목 하나" in out  # 글머리 기호만 제거, 텍스트 유지
    assert "!" not in out and ".ᐟ" in out
    assert "~" not in out
    assert "😊" not in out  # 금지 이모지 제거
    assert "✨" in out  # 허용 이모지는 유지
    # 물결표를 포함한 허용 이모지는 보호(치환되지 않음)
    assert enforce_format("맛 (๑´~ˋ๑) 좋아").count("(๑´~ˋ๑)") == 1
