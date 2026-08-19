import json

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


def test_load_topic_seeds_merges_month(tmp_path):
    """저장 시드 — base + 해당 월만 병합, 중복 제거, 파일 없으면 빈 리스트."""
    p = tmp_path / "seeds.yaml"
    p.write_text(
        "base: [버거킹 메뉴, 편의점 신상]\nmonthly:\n  8: [무화과, 버거킹 메뉴]\n  9: [샤인머스캣]\n",
        encoding="utf-8",
    )
    seeds = rank.load_topic_seeds(month=8, path=p)
    assert seeds == ["버거킹 메뉴", "편의점 신상", "무화과"]  # 9월 시드 제외, 중복 병합
    assert rank.load_topic_seeds(month=8, path=tmp_path / "없음.yaml") == []


def test_keyword_competition_survives_volume_failure(monkeypatch):
    """검색량(부가) 조회가 터져도 경쟁 판정은 나와야 한다 — 아니면 칩에 판정이 안 뜬다."""
    monkeypatch.setattr(rank, "_search_blog_full", lambda kw: {"total": 42, "items": []})
    monkeypatch.setattr(
        rank, "search_volumes", lambda kws: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    d = rank.keyword_competition("강남맛집")
    assert d["total"] == 42 and d["volume"] is None


def test_title_keywords_ngrams():
    """제목 → 1~3어 n-gram, 한 글자 토큰·기호 제외, 중복 제거."""
    kws = rank._title_keywords("[더현대] 다이소 팝콘 또 삼")
    assert "다이소" in kws and "다이소 팝콘" in kws and "더현대 다이소 팝콘" in kws
    assert "또" not in kws and "[더현대]" not in kws  # 한 글자·기호는 후보 아님
    assert len(kws) == len(set(kws))


def test_exposure_scan_filters_and_scores(tmp_path, monkeypatch):
    """검색량 하한으로 후보를 거르고, 100위 밖은 버리고, 1페이지 검색량만 점수에 넣는다."""
    monkeypatch.setattr(rank, "_RANKS_PATH", tmp_path / "ranks.json")
    monkeypatch.setattr(
        rank, "load_env",
        lambda: type("E", (), {"has_searchad": True, "naver_blog_id": "me"})(),
    )
    monkeypatch.setattr(rank.time, "sleep", lambda s: None)
    import autoblog.collect.blog_posts as bp

    monkeypatch.setattr(
        bp, "fetch_recent_posts",
        lambda b, n: [{"logNo": "100", "title": "다이소 팝콘 후기", "url": "https://blog.naver.com/me/100"}],
    )
    monkeypatch.setattr(bp, "fetch_popular_posts", lambda b, n: [])
    monkeypatch.setattr(
        rank, "search_volumes",
        lambda kws: {"다이소 팝콘": {"volume": 5000}, "후기": {"volume": 3000}, "팝콘": {"volume": 50}},
    )
    ranks = {"다이소 팝콘": 3, "후기": None}  # 1페이지 / 100위 밖
    monkeypatch.setattr(rank, "_OBS_PATH", tmp_path / "obs.json")
    monkeypatch.setattr(
        rank, "_search_blog_full",
        lambda kw: {"total": 5_000,
                    "items": [{"link": "https://blog.naver.com/me/100"}] if ranks[kw] == 3 else []},
    )
    d = rank.exposure_scan()
    # 진 키워드까지 관측으로 남아야 승률 표본이 된다
    assert [(o["keyword"], o["rank"]) for o in json.loads((tmp_path / "obs.json").read_text())] == [
        ("다이소 팝콘", 1), ("후기", None)
    ]
    assert [r["keyword"] for r in d["rows"]] == ["다이소 팝콘"]  # 하한 미달·100위 밖 제외
    assert d["score"] == 5000 and d["top10"] == 1 and d["missed"] == 1
    assert [e["keyword"] for e in rank.list_entries()] == ["다이소 팝콘"]  # 추적 자동 등록


def test_sm_rank_parses_position_and_share(monkeypatch):
    """슈멤 원본 — 상위 50 목록에 내 아이디가 있는 키워드만, 기여도는 검색량÷순위²."""
    payload = {"value": [{
        "rank": 66804, "percentage": 23.21, "adFee": 23637, "score": 110.776,
        "visitorEx": 136.77, "updatedAt": "2026-08-09T19:13:11.000Z",
        "keywords": [
            {"name": "아쿠아슈즈", "mmqccnt": 202900, "cat1": "제품", "cat2": "패션/잡화",
             "ids": ["a"] * 56 + ["me"] + ["b"] * 3},  # 57/60위
            {"name": "냉동떡", "mmqccnt": 1530, "cat1": None, "cat2": None,
             "ids": ["a"] * 11 + ["me"] + ["b"] * 38},  # 12/50위
            {"name": "남의키워드", "mmqccnt": 999999, "ids": ["a", "b"]},  # 내 아이디 없음 → 제외
        ],
        "histories": [{"week": "2026-08-10", "rank": 66804, "score": 110.776, "adFee": 23637,
                       "percentage": 23.21}],
    }]}
    monkeypatch.setattr(
        rank, "load_env", lambda: type("E", (), {"naver_blog_id": "me"})()
    )
    monkeypatch.setattr(
        rank.requests, "get",
        lambda *a, **k: type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: payload})(),
    )
    d = rank.sm_rank()
    assert [k["keyword"] for k in d["keywords"]] == ["아쿠아슈즈", "냉동떡"]  # 남의 키워드 제외
    assert d["keywords"][0]["pos"] == 57 and d["keywords"][0]["of"] == 60
    assert d["keywords"][0]["share"] > d["keywords"][1]["share"]  # sm_score 기준 아쿠아슈즈가 더 큼
    assert round(sum(k["share"] for k in d["keywords"])) == 100
    assert d["rank"] == 66804 and len(d["history"]) == 1


def test_sm_score_favors_position_over_volume():
    """실측 공식의 핵심 — 작은 키워드 1위가 큰 키워드 하위권을 이긴다."""
    assert rank.sm_score(1000, 1) > rank.sm_score(200000, 30)  # 75 vs 35
    assert rank.sm_score(500, 1) > rank.sm_score(202900, 57)  # 57 vs 20 (내 아쿠아슈즈)
    assert rank.sm_score(0, 1) == 0 and rank.sm_score(1000, 0) == 0


def test_keyword_suggest_scores_and_sorts_by_payoff(monkeypatch):
    """추천 목록 — 3위 기준 슈멤 점수를 붙이고, 생검색량이 아니라 페이오프로 정렬."""
    monkeypatch.setattr(rank, "load_env", lambda: type("E", (), {"has_searchad": True})())
    monkeypatch.setattr(rank, "_related_terms", lambda kw: ["큰키워드", "작은키워드"])
    monkeypatch.setattr(rank, "_searchad_related", lambda kw, n, require_tokens=True: [])
    monkeypatch.setattr(rank, "_total", lambda kw: {"큰키워드": 500000, "작은키워드": 300}[kw])
    monkeypatch.setattr(
        rank, "search_volumes",
        lambda kws: {"큰키워드": {"volume": 200000}, "작은키워드": {"volume": 2000}},
    )
    d = rank.keyword_suggest("씨앗")
    # 검색량은 100배 차이지만 문서수(경쟁)가 1666배라 작은 쪽이 위로 와야 한다
    assert [s["keyword"] for s in d["suggestions"]] == ["작은키워드", "큰키워드"]
    assert d["suggestions"][0]["sm3"] == round(rank.sm_score(2000, 3), 1)


def test_win_rates_and_expected_score(tmp_path, monkeypatch):
    """실측 승률 — 경쟁 구간별 1페이지 비율, 기대값은 승률 × 3위 점수."""
    obs = ([{"keyword": f"a{i}", "total": 5_000, "rank": 3, "t": "x"} for i in range(5)]
           + [{"keyword": f"b{i}", "total": 5_000, "rank": None, "t": "x"} for i in range(5)]
           + [{"keyword": f"c{i}", "total": 500_000, "rank": None, "t": "x"} for i in range(20)])
    p = tmp_path / "obs.json"
    p.write_text(json.dumps(obs), encoding="utf-8")
    monkeypatch.setattr(rank, "_OBS_PATH", p)
    rates = rank.win_rates()
    mid = [r for r in rates if r["lo"] == 1_000][0]
    assert mid["n"] == 10 and mid["top10"] == 0.5
    big = [r for r in rates if r["lo"] == 100_000][0]
    assert big["top10"] == 0.0
    # 검색량이 100배 커도 승률 0이면 기대값 0 — 이게 이 기능의 존재 이유
    assert rank.expected_score(2_000, 5_000)["ev"] == round(0.5 * rank.sm_score(2_000, 3), 1)
    assert rank.expected_score(200_000, 500_000)["ev"] == 0.0
    assert rank.expected_score(2_000, 5_000)["ev"] > rank.expected_score(200_000, 500_000)["ev"]


def test_keyword_suggest_broadens_to_head_noun(monkeypatch):
    """'다이소 팝콘'처럼 브랜드+상품이면 핵심 명사로도 넓힌다 — 안 그러면 0점 후보만 나온다."""
    monkeypatch.setattr(rank, "load_env", lambda: type("E", (), {"has_searchad": True})())
    monkeypatch.setattr(rank, "_related_terms", lambda kw: [])
    rel = {
        "다이소 팝콘": [{"keyword": "다이소 팝콘통", "volume": 310}],
        "팝콘": [{"keyword": "곤약팝콘", "volume": 780}],  # 씨앗 토큰 필터로는 절대 안 나온다
    }
    monkeypatch.setattr(rank, "_searchad_related", lambda kw, n, require_tokens=True: rel.get(kw, []))
    monkeypatch.setattr(rank, "_total", lambda kw: {"다이소 팝콘통": 9_693, "곤약팝콘": 10_268}[kw])
    monkeypatch.setattr(rank, "search_volumes", lambda kws: {})
    monkeypatch.setattr(rank, "win_rates", lambda: [])
    d = rank.keyword_suggest("다이소 팝콘")
    assert {s["keyword"] for s in d["suggestions"]} == {"다이소 팝콘통", "곤약팝콘"}
    assert d["head"] == "팝콘"
    # 한 토큰짜리 씨앗은 넓힐 게 없다
    assert rank.keyword_suggest("팝콘")["head"] == ""


def test_keyword_suggest_strips_brand_token(monkeypatch):
    """'다이소 팝콘 전자레인지' → '전자레인지팝콘' — 어순 둘 다 시도, 검색량으로 거른다."""
    monkeypatch.setattr(rank, "load_env", lambda: type("E", (), {"has_searchad": True})())
    monkeypatch.setattr(rank, "_related_terms", lambda kw: [])
    monkeypatch.setattr(
        rank, "_searchad_related",
        lambda kw, n, require_tokens=True:
            [{"keyword": "다이소 팝콘 전자레인지", "volume": 10}] if kw == "다이소 팝콘" else [],
    )
    # 붙여쓴 '전자레인지팝콘'만 실검색어 — 뒤집힌 '팝콘전자레인지'는 하한 미달로 탈락
    monkeypatch.setattr(
        rank, "search_volumes",
        lambda kws: {k: {"volume": 1590} for k in kws if k == "전자레인지팝콘"}
        | {k: {"volume": 20} for k in kws if k == "팝콘전자레인지"},
    )
    monkeypatch.setattr(rank, "_total", lambda kw: 38_640)
    monkeypatch.setattr(rank, "win_rates", lambda: [])
    got = {s["keyword"] for s in rank.keyword_suggest("다이소 팝콘")["suggestions"]}
    assert "전자레인지팝콘" in got and "팝콘전자레인지" not in got


def test_keyword_suggest_drops_below_sm_floor(monkeypatch):
    """월 300 미만은 슈멤 DB 하한 아래라 추천에서 뺀다 — 1위를 해도 집계가 안 된다."""
    monkeypatch.setattr(rank, "load_env", lambda: type("E", (), {"has_searchad": True})())
    monkeypatch.setattr(rank, "_related_terms", lambda kw: [])
    monkeypatch.setattr(
        rank, "_searchad_related",
        lambda kw, n, require_tokens=True: [
            {"keyword": "쓸만한키워드", "volume": 890},
            {"keyword": "티끌키워드", "volume": 25},  # 하한 미달 → 제외
        ] if kw == "씨앗" else [],
    )
    calls = []
    monkeypatch.setattr(rank, "_total", lambda kw: calls.append(kw) or 3_669)
    monkeypatch.setattr(rank, "search_volumes", lambda kws: {})
    monkeypatch.setattr(rank, "win_rates", lambda: [])
    d = rank.keyword_suggest("씨앗")
    assert [s["keyword"] for s in d["suggestions"]] == ["쓸만한키워드"]
    assert calls == ["쓸만한키워드"]  # 버릴 후보엔 문서수 조회(API 1회)를 쓰지 않는다


def test_find_targets_ranks_by_expected_score(monkeypatch):
    """노려볼 키워드 — 씨앗은 슈멤 집계 키워드, 순위는 기대 점수(못 잡는 큰 건 바닥)."""
    monkeypatch.setattr(rank, "load_env", lambda: type("E", (), {"has_searchad": True})())
    monkeypatch.setattr(rank, "sm_rank", lambda *a, **k: {"keywords": [{"keyword": "냉동떡"}]})
    monkeypatch.setattr(rank.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        rank, "_searchad_related",
        lambda kw, n, require_tokens=True: [
            {"keyword": "큰거못잡음", "volume": 50_000},
            {"keyword": "작지만잡음", "volume": 900},
        ],
    )
    monkeypatch.setattr(
        rank, "_total", lambda kw: {"큰거못잡음": 500_000, "작지만잡음": 3_000}[kw]
    )
    monkeypatch.setattr(rank, "win_rates", lambda: [
        {"lo": 1_000, "hi": 10_000, "n": 15, "top10": 0.47, "top30": 0.6},
        {"lo": 100_000, "hi": 10**12, "n": 135, "top10": 0.0, "top30": 0.0},
    ])
    d = rank.find_targets()
    assert d["source"] == "슈멤 집계 중인 내 키워드"
    assert [r["keyword"] for r in d["rows"]] == ["작지만잡음", "큰거못잡음"]
    assert d["rows"][0]["exp"]["ev"] > 0 and d["rows"][1]["exp"]["ev"] == 0.0
