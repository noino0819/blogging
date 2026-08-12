from autoblog import rank


def test_post_key_formats():
    assert rank._post_key("https://blog.naver.com/foo/223456") == ("foo", "223456")
    assert rank._post_key("https://m.blog.naver.com/foo/223456") == ("foo", "223456")
    assert rank._post_key(
        "https://blog.naver.com/PostView.naver?blogId=foo&logNo=223456"
    ) == ("foo", "223456")
    assert rank._post_key("https://example.tistory.com/12") is None


def test_find_rank():
    items = [{"link": f"https://blog.naver.com/u{i}/{1000 + i}"} for i in range(5)]
    assert rank.find_rank(items, "https://m.blog.naver.com/u2/1002") == 3
    assert rank.find_rank(items, "https://blog.naver.com/nope/9") is None


def test_add_dedupe_check_history(tmp_path, monkeypatch):
    monkeypatch.setattr(rank, "_RANKS_PATH", tmp_path / "ranks.json")
    rank.add_entry("성수동 맛집", "https://blog.naver.com/me/100")
    rank.add_entry("성수동 맛집", "https://m.blog.naver.com/me/100")  # 같은 글 다른 형식
    assert len(rank.list_entries()) == 1

    monkeypatch.setattr(
        rank, "_search_blog", lambda kw: [{"link": "https://blog.naver.com/me/100"}]
    )
    rows = rank.check_all()
    assert rows[0]["rank"] == 1 and rows[0]["prev"] is None
    rows = rank.check_all()
    assert rows[0]["prev"] == 1  # 직전 이력이 prev로

    assert rank.remove_entry("성수동 맛집", "https://blog.naver.com/me/100")
    assert rank.list_entries() == []


def test_discover_topics_dedupe_filter_rank(monkeypatch):
    """주제 발굴 — 시드 간 중복 제거, 검색량 하한 필터, ratio 내림차순 정렬."""
    monkeypatch.setattr(rank, "load_env", lambda: type("E", (), {"has_searchad": True})())
    related = {
        "버거킹": [
            {"keyword": "버거킹 아침메뉴", "volume": 170000},
            {"keyword": "맥모닝 시간", "volume": 80000},
            {"keyword": "듣보 키워드", "volume": 500},  # 하한 미달 → 제외
        ],
        "맥도날드": [
            {"keyword": "맥모닝시간", "volume": 80000},  # 공백만 다른 중복 → 제외
            {"keyword": "맥도날드 런치", "volume": 20000},
        ],
    }
    monkeypatch.setattr(
        rank, "_searchad_related", lambda kw, n, require_tokens=True: related[kw]
    )
    totals = {"버거킹 아침메뉴": 79000, "맥모닝 시간": 183000, "맥도날드 런치": 43000}
    monkeypatch.setattr(rank, "_total", lambda kw: totals[kw])
    rows = rank.discover_topics(["버거킹", "맥도날드"], min_volume=1000)
    assert [r["keyword"] for r in rows] == ["버거킹 아침메뉴", "맥도날드 런치", "맥모닝 시간"]
    assert rows[0]["ratio"] > rows[-1]["ratio"]
    assert all("듣보" not in r["keyword"] for r in rows)


def test_keyword_competition_survives_volume_failure(monkeypatch):
    """검색량(부가) 조회가 터져도 경쟁 판정은 나와야 한다 — 아니면 칩에 판정이 안 뜬다."""
    monkeypatch.setattr(rank, "_search_blog_full", lambda kw: {"total": 42, "items": []})
    monkeypatch.setattr(
        rank, "search_volumes", lambda kws: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    d = rank.keyword_competition("강남맛집")
    assert d["total"] == 42 and d["volume"] is None
