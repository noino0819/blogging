"""정보글 주제 준비(팩트 시트) — 조립·필터 로직 (네트워크·LLM 모킹)."""

import pytest

from autoblog.collect import info_topic


def test_prepare_info_sheet_assembly(monkeypatch):
    monkeypatch.setattr(
        info_topic, "_related_terms", lambda t: ["복숭아 보관법", "딱딱한 복숭아 후숙", "물복 냉장"]
    )
    monkeypatch.setattr(
        info_topic,
        "_search_blog",
        lambda t: [
            {"title": "복숭아 <b>보관</b> 총정리", "link": "https://blog.naver.com/aaa/111"},
            {"title": "짧은 글", "link": "https://blog.naver.com/bbb/222"},
        ],
    )
    texts = {"https://blog.naver.com/aaa/111": "본문 " * 200, "https://blog.naver.com/bbb/222": "짧음"}
    monkeypatch.setattr(info_topic, "_fetch_post_text", lambda link, max_chars=4000: texts[link])
    monkeypatch.setattr(
        info_topic, "chat", lambda msgs, model=None: "- 후숙은 실온 2~3일 [1]\n- 냉장은 3~5일 [1]"
    )
    out = info_topic.prepare_info_sheet("복숭아 보관법")
    sheet = out["sheet"]
    # 자기 자신과 같은 검색어는 목차에서 빠지고, 나머지는 커버 목록으로
    assert "딱딱한 복숭아 후숙" in sheet and out["terms"][0] != "복숭아 보관법"
    assert "후숙은 실온 2~3일 [1]" in sheet
    assert "[내 경험" in sheet and "[출처" in sheet
    # 본문이 짧은 글(300자 미만)은 출처에서 제외, 제목 태그는 제거
    assert len(out["sources"]) == 1 and out["sources"][0]["title"] == "복숭아 보관 총정리"


def test_prepare_info_sheet_no_sources(monkeypatch):
    monkeypatch.setattr(info_topic, "_related_terms", lambda t: [])
    monkeypatch.setattr(info_topic, "_search_blog", lambda t: [])
    with pytest.raises(RuntimeError):
        info_topic.prepare_info_sheet("아무도 안 쓴 주제")
    with pytest.raises(ValueError):
        info_topic.prepare_info_sheet("  ")
