"""키워드 순위 추적 — 게시한 글이 블로그 검색에서 몇 위에 뜨는지 실측.

블로그 검색 API(sort=sim, 상위 100위)는 블로그탭 정확도순 근사치다 —
통합검색 스마트블록 순서와 다를 수 있고 AI 브리핑 인용 여부는 알 수 없다.
목적은 글별 노출 추이(진입·등락·이탈)를 데이터로 남겨 감이 아닌 실측으로
검증하는 것. 검색 API 키(.env)를 그대로 쓴다(일 25,000회 무료).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone

import requests

from autoblog.config import DATA_DIR, load_env

_BLOG_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"
_AUTOCOMPLETE_URL = "https://ac.search.naver.com/nx/ac"  # 자동완성=연관검색어, 키 불필요
_SEARCHAD_URL = "https://api.searchad.naver.com"  # 검색광고 API — 월간 검색량(키워드 도구)
_RANKS_PATH = DATA_DIR / "ranks.json"
# 게시글 URL → (blogId, logNo). 데스크톱/모바일/PostView 형식 모두 수용.
_POST_RE = re.compile(
    r"blog\.naver\.com/(?:PostView\.naver\?blogId=([\w.-]+)&logNo=(\d+)|([\w.-]+)/(\d+))"
)


def _post_key(url: str) -> tuple[str, str] | None:
    m = _POST_RE.search(url or "")
    if not m:
        return None
    return (m.group(1) or m.group(3), m.group(2) or m.group(4))


def _load() -> list[dict]:
    if _RANKS_PATH.exists():
        try:
            return json.loads(_RANKS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(entries: list[dict]) -> None:
    _RANKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RANKS_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")


def add_entry(keyword: str, url: str) -> dict:
    """추적 항목 등록. 같은 (키워드, 글) 조합은 중복 등록하지 않는다."""
    keyword = keyword.strip()
    url = url.strip()
    if not keyword:
        raise ValueError("키워드가 비어 있어요")
    if _post_key(url) is None:
        raise ValueError("네이버 블로그 글 URL이 아니에요 (blog.naver.com/아이디/글번호 형식)")
    entries = _load()
    for e in entries:
        if e["keyword"] == keyword and _post_key(e["url"]) == _post_key(url):
            return e
    entry = {
        "keyword": keyword,
        "url": url,
        "added": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "history": [],
    }
    entries.append(entry)
    _save(entries)
    return entry


def remove_entry(keyword: str, url: str) -> bool:
    entries = _load()
    kept = [
        e for e in entries
        if not (e["keyword"] == keyword.strip() and _post_key(e["url"]) == _post_key(url))
    ]
    if len(kept) == len(entries):
        return False
    _save(kept)
    return True


def find_rank(items: list[dict], url: str) -> int | None:
    """검색 결과 목록에서 해당 글의 순위(1부터). 100위 밖이면 None."""
    key = _post_key(url)
    if key is None:
        return None
    for i, item in enumerate(items, 1):
        if _post_key(item.get("link", "")) == key:
            return i
    return None


def _search_blog_full(keyword: str) -> dict:
    env = load_env()
    if not env.has_naver_api:
        raise RuntimeError("검색 API 키 미설정 (.env의 NAVER_CLIENT_ID/SECRET)")
    resp = requests.get(
        _BLOG_SEARCH_URL,
        params={"query": keyword, "display": 100, "sort": "sim"},
        headers={
            "X-Naver-Client-Id": env.naver_client_id or "",
            "X-Naver-Client-Secret": env.naver_client_secret or "",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _search_blog(keyword: str) -> list[dict]:
    return _search_blog_full(keyword).get("items", [])


_TAG_RE = re.compile(r"<[^>]+>")


def keyword_competition(keyword: str) -> dict:
    """발행 전 키워드 경쟁 가늠 — 블로그 문서수(경쟁량) + 현재 상위결과 + 내 글 순위.

    검색광고 API가 없어 '검색량'은 못 주고, 대신 openapi 블로그 검색으로
    '이미 쓰인 문서 수'(경쟁강도의 대리 지표)와 상위 결과 면면을 보여준다.
    공식 저경쟁 임계값은 존재하지 않으므로(리서치 검증), total은 참고용 상대 신호이고
    실제 판단은 top(상위 블로그가 대형매체·최적화 블로그로 꽉 찼는지)과 mine(내 글이
    이미 top100에 드는지)으로 눈으로 한다.
    """
    keyword = (keyword or "").strip()
    if not keyword:
        raise ValueError("키워드가 비어 있어요")
    data = _search_blog_full(keyword)
    items = data.get("items", [])
    blog_id = (load_env().naver_blog_id or "").strip().lower()
    mine = None
    if blog_id:
        for i, it in enumerate(items, 1):
            link = (it.get("link", "") + " " + it.get("bloggerlink", "")).lower()
            if f"blog.naver.com/{blog_id}" in link or f"/{blog_id}" in link:
                mine = i
                break
    top = [
        {
            "title": _TAG_RE.sub("", it.get("title", "")).replace("&amp;", "&").strip(),
            "blogger": it.get("bloggername", ""),
            "link": it.get("link", ""),
        }
        for it in items[:5]
    ]
    # 검색량은 부가 정보 — 여기서 터지면 멀쩡한 경쟁 판정까지 통째로 날아간다(→ 칩에 판정 안 뜸)
    try:
        vol = search_volumes([keyword]).get(keyword) or {}
    except Exception:  # noqa: BLE001
        vol = {}
    v = vol.get("volume")
    return {
        "keyword": keyword, "total": data.get("total", 0), "mine": mine, "top": top,
        "volume": v,  # 월간 검색수(PC+모바일) — 검색광고 키 없으면 None
        "comp_idx": vol.get("comp_idx", ""),
        # 이 키워드를 잡았을 때 슈멤 점수가 얼마나 오르는지 — 순위별 전망
        "sm": {str(p): round(sm_score(v, p), 1) for p in (1, 3, 10, 30)} if v else None,
        # 내 실측 승률까지 곱한 기대값 — 점수만 크고 못 잡는 키워드를 걸러낸다
        "exp": expected_score(v or 0, int(data.get("total", 0))),
    }


def _searchad_headers(method: str, path: str) -> dict:
    """검색광고 API 인증 헤더 — {timestamp}.{method}.{path}를 비밀키로 HMAC-SHA256 서명."""
    env = load_env()
    ts = str(round(time.time() * 1000))
    sig = base64.b64encode(
        hmac.new(
            (env.searchad_secret or "").encode(),
            f"{ts}.{method}.{path}".encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    return {
        "X-Timestamp": ts,
        "X-API-KEY": env.searchad_api_key or "",
        "X-Customer": env.searchad_customer_id or "",
        "X-Signature": sig,
    }


def _qc(v) -> int:
    """월간 검색수 필드 파싱 — 10 미만이면 '< 10' 문자열로 오므로 5로 근사."""
    if isinstance(v, str):
        return 5 if "<" in v else int(re.sub(r"[^\d]", "", v) or 0)
    return int(v or 0)


def search_volumes(keywords: list[str]) -> dict[str, dict]:
    """키워드별 월간 검색수(PC+모바일)·광고 경쟁도. 검색광고 키 미설정이면 {}.

    keywordstool의 hintKeywords는 공백 불가·한 번에 5개까지라, 공백을 뺀 형태로
    5개씩 끊어 조회하고 응답 relKeyword(공백 없는 대문자)를 원래 키워드로 되맞춘다.
    검색량은 부가 정보라 개별 실패는 건너뛴다(경쟁도만으로도 동작해야 함).
    """
    if not load_env().has_searchad:
        return {}
    want = {}  # 정규화(공백 제거·대문자) → 원래 키워드
    for kw in keywords:
        k = (kw or "").strip()
        if k:
            want.setdefault(k.replace(" ", "").upper(), k)
    out: dict[str, dict] = {}
    hints = list(want.keys())
    for i in range(0, len(hints), 5):
        try:
            resp = requests.get(
                _SEARCHAD_URL + "/keywordstool",
                params={"hintKeywords": ",".join(hints[i : i + 5]), "showDetail": 1},
                headers=_searchad_headers("GET", "/keywordstool"),
                timeout=10,
            )
            resp.raise_for_status()
            # 응답엔 힌트 외 연관 키워드도 잔뜩 오므로, 요청한 것만 골라 담는다.
            for row in resp.json().get("keywordList", []) or []:
                orig = want.get((row.get("relKeyword") or "").replace(" ", "").upper())
                if orig and orig not in out:
                    out[orig] = {
                        "volume": _qc(row.get("monthlyPcQcCnt")) + _qc(row.get("monthlyMobileQcCnt")),
                        "comp_idx": row.get("compIdx") or "",  # 광고 입찰 경쟁도(낮음/중간/높음)
                    }
        except Exception:  # noqa: BLE001
            continue
    return out


def _searchad_related(keyword: str, limit: int, *, require_tokens: bool = True) -> list[dict]:
    """keywordstool이 힌트 외에 얹어 주는 연관 키워드 — 검색량이 이미 붙어 온다.

    자동완성과 달리 광고 시장 기준 연관어라 엉뚱한 지역·주제가 섞인다. 기본은 원 키워드
    토큰을 전부 포함하는 세부 롱테일만 남기고 검색량순 상위 limit개만 쓴다.
    require_tokens=False(주제 발굴)면 토큰 필터를 끄고 인접 주제까지 넓게 받는다
    — 엉뚱한 후보는 발굴 쪽에서 검색량 하한·비율 정렬로 걸러진다.
    """
    tokens = [t.lower() for t in keyword.split()] if require_tokens else []
    try:
        resp = requests.get(
            _SEARCHAD_URL + "/keywordstool",
            params={"hintKeywords": keyword.replace(" ", ""), "showDetail": 1},
            headers=_searchad_headers("GET", "/keywordstool"),
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json().get("keywordList", []) or []
    except Exception:  # noqa: BLE001 — 부가 후보라 실패해도 자동완성만으로 동작
        return []
    out = [
        {
            "keyword": t,
            "volume": _qc(row.get("monthlyPcQcCnt")) + _qc(row.get("monthlyMobileQcCnt")),
        }
        for row in rows
        if (t := (row.get("relKeyword") or "").strip())
        and all(tok in t.replace(" ", "").lower() for tok in tokens)
    ]
    out.sort(key=lambda x: x["volume"], reverse=True)
    return out[:limit]


def _related_terms(keyword: str) -> list[str]:
    """네이버 자동완성(=연관검색어) — 검색창에 뜨는 추천어. 공개 엔드포인트라 키 불필요."""
    resp = requests.get(
        _AUTOCOMPLETE_URL,
        params={"q": keyword, "st": 100, "r_format": "json", "frm": "nv", "ans": 2},
        headers={"User-Agent": "Mozilla/5.0"},  # UA 없으면 빈 응답
        timeout=6,
    )
    resp.raise_for_status()
    out: list[str] = []
    for group in resp.json().get("items", []) or []:
        for row in group or []:
            t = (row[0] if isinstance(row, list) and row else row) or ""
            t = t.strip()
            if t and t not in out:
                out.append(t)
    return out


def _total(keyword: str) -> int:
    """문서 수만 필요한 가벼운 조회(display=1) — 추천어 경쟁 정렬용."""
    env = load_env()
    resp = requests.get(
        _BLOG_SEARCH_URL,
        params={"query": keyword, "display": 1},
        headers={
            "X-Naver-Client-Id": env.naver_client_id or "",
            "X-Naver-Client-Secret": env.naver_client_secret or "",
        },
        timeout=8,
    )
    resp.raise_for_status()
    return int(resp.json().get("total", 0))


def load_topic_seeds(month: int | None = None, path=None) -> list[str]:
    """config/topic_seeds.yaml → base + 해당 월 시드. 파일 없으면 빈 리스트.

    discover를 인자 없이 돌리는 경로의 단일 출처 — 매달 뭘 시드로 줄지 사람이
    생각하지 않아도 되게 시즌 캘린더를 파일에 박아둔다(유저 수정 가능).
    """
    import yaml

    from autoblog.config import CONFIG_DIR

    p = path or CONFIG_DIR / "topic_seeds.yaml"
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    seeds = [str(s).strip() for s in (data.get("base") or []) if str(s).strip()]
    monthly = data.get("monthly") or {}
    m = month or datetime.now().month
    for s in monthly.get(m) or monthly.get(str(m)) or []:
        s = str(s).strip()
        if s and s not in seeds:
            seeds.append(s)
    return seeds


def discover_topics(
    seeds: list[str],
    per_seed: int = 15,
    min_volume: int = 1000,
    max_check: int = 60,
) -> list[dict]:
    """주제 발굴 — 시드 키워드들에서 연관 주제를 넓게 확장해 수요/공급 비율로 랭킹.

    시드마다 검색광고 연관 키워드(검색량 포함, 토큰 필터 없이)를 받아 합치고,
    검색량 하한으로 거른 뒤 상위 max_check개만 문서 수(경쟁 대리 지표)를 재서
    ratio(월간 검색량 ÷ 블로그 문서수) 내림차순으로 돌려준다. 검색광고 키 필수.

    ratio는 공식 지표가 아니라 대리 신호 — 문서수는 누적 전체라 최근 경쟁과 다를 수
    있으니, 실제 발행 전 keyword_competition의 top(상위 블로그 면면)을 눈으로 확인.
    """
    if not load_env().has_searchad:
        raise RuntimeError("검색광고 API 키(.env NAVER_SEARCHAD_*)가 필요해요")
    seen: set[str] = set()
    by_seed: list[list[dict]] = []  # 시드별 후보(검색량순) — 전역 정렬로 합치면 안 됨
    for seed in seeds:
        s = (seed or "").strip()
        if not s:
            continue
        rows = []
        for r in _searchad_related(s, per_seed, require_tokens=False):
            norm = r["keyword"].replace(" ", "").lower()
            if norm not in seen and r["volume"] >= min_volume:
                seen.add(norm)
                rows.append({"keyword": r["keyword"], "volume": r["volume"], "seed": s})
        by_seed.append(rows)
        time.sleep(0.3)  # keywordstool 연속 호출 제한 회피
    # 문서수 조회가 비싸니 max_check개만 재되, 전역 검색량순으로 자르면 검색량 큰
    # 시드(프랜차이즈 등)가 다른 카테고리를 다 밀어낸다 → 시드별 라운드로빈으로 고르게.
    candidates: list[dict] = []
    i = 0
    while len(candidates) < max_check and any(by_seed):
        picked = False
        for rows in by_seed:
            if i < len(rows) and len(candidates) < max_check:
                candidates.append(rows[i])
                picked = True
        if not picked:
            break
        i += 1
    out: list[dict] = []
    for c in candidates:
        try:
            total = _total(c["keyword"])
        except Exception:  # noqa: BLE001 — 개별 실패는 건너뛰고 나머지로 발굴
            continue
        out.append({**c, "total": total, "ratio": round(c["volume"] / (total + 1), 2)})
    out.sort(key=lambda x: x["ratio"], reverse=True)
    return out


def keyword_suggest(keyword: str, limit: int = 8) -> dict:
    """연관검색어 중 '더 유리한' 키워드 추천.

    자동완성으로 실제 검색되는 연관어를 뽑고 각각 문서 수(경쟁 대리 지표)를 잰다.
    검색광고 키가 있으면 월간 검색량도 붙여 '검색량 대비 경쟁이 유리한' 순으로,
    없으면 기존대로 문서 수 오름차순으로 정렬한다.
    """
    kw = (keyword or "").strip()
    if not kw:
        raise ValueError("키워드가 비어 있어요")
    seen = {kw.replace(" ", "").lower()}

    def _fresh(t: str) -> bool:
        n = t.replace(" ", "").lower()
        if n in seen:
            return False
        seen.add(n)
        return True

    terms = [t for t in _related_terms(kw) if _fresh(t)][:limit]
    # 검색광고 연관 키워드로 후보 풀 확장 — 검색량이 응답에 이미 있어 추가 조회 불필요
    known_vol = {}
    for r in _searchad_related(kw, limit) if load_env().has_searchad else []:
        if _fresh(r["keyword"]):
            terms.append(r["keyword"])
            known_vol[r["keyword"]] = r["volume"]
    scored = []
    for t in terms:
        try:
            scored.append({"keyword": t, "total": _total(t)})
        except Exception:  # noqa: BLE001 — 개별 실패는 건너뛰고 나머지로 추천
            continue
    vols = search_volumes([s["keyword"] for s in scored if s["keyword"] not in known_vol])
    for s in scored:
        v = vols.get(s["keyword"]) or {}
        s["volume"] = known_vol.get(s["keyword"], v.get("volume"))
    rates = win_rates()
    for s in scored:
        # 1페이지(3위 가정)를 잡았을 때 슈멤 점수가 얼마나 오르는지 — 뽑을지 말지의 기준
        s["sm3"] = round(sm_score(s["volume"] or 0, 3), 1)
        s["exp"] = expected_score(s["volume"] or 0, s["total"], rates)
    has_volume = any(s["volume"] is not None for s in scored)
    if rates and has_volume:
        # 내 승률까지 곱한 기대값 순 — 잡을 수 없는 큰 키워드가 위로 올라오지 않는다
        scored.sort(key=lambda x: ((x["exp"] or {}).get("ev", 0), x["sm3"]), reverse=True)
    elif has_volume:
        # 승률 표본이 없을 때(첫 사용) — 실측 페이오프(검색량^0.4)를 문서수로 나눈 순.
        # 슈멤 점수는 검색량에 ^0.4로만 반응해서, 생검색량 정렬은 큰 키워드를 과대평가한다.
        scored.sort(key=lambda x: (x["volume"] or 0) ** _SM_A / (x["total"] + 1), reverse=True)
    else:
        scored.sort(key=lambda x: x["total"])
    return {"keyword": kw, "suggestions": scored, "has_volume": has_volume}


def check_all() -> list[dict]:
    """전 항목 순위 확인 → 이력 저장 → 요약 행 반환.

    반환 행: {keyword, url, rank(이번), prev(직전), added}. 같은 키워드는
    API를 한 번만 호출한다(항목 수만큼이 아니라 키워드 수만큼 과금).
    """
    entries = _load()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results_cache: dict[str, list[dict]] = {}
    rows: list[dict] = []
    for e in entries:
        kw = e["keyword"]
        if kw not in results_cache:
            results_cache[kw] = _search_blog(kw)
        rank = find_rank(results_cache[kw], e["url"])
        prev = e["history"][-1]["rank"] if e["history"] else None
        e["history"].append({"t": now, "rank": rank})
        rows.append(
            {"keyword": kw, "url": e["url"], "rank": rank, "prev": prev, "added": e["added"]}
        )
    _save(entries)
    return rows


def list_entries() -> list[dict]:
    """API 호출 없이 저장된 항목 + 마지막 확인 결과 요약."""
    rows = []
    for e in _load():
        last = e["history"][-1] if e["history"] else None
        prev = e["history"][-2] if len(e["history"]) >= 2 else None
        rows.append({
            "keyword": e["keyword"], "url": e["url"], "added": e["added"],
            "rank": last["rank"] if last else None,
            "prev": prev["rank"] if prev else None,
            "checked": last["t"] if last else None,
            "checks": len(e["history"]),
        })
    return rows


_TITLE_SPLIT = re.compile(r"[^0-9A-Za-z가-힣]+")


def _title_keywords(title: str, limit: int = 24) -> list[str]:
    """제목 → 검색 후보 n-gram(1~3어). 진짜 검색되는 말인지는 뒤의 검색량이 걸러준다."""
    toks = [t for t in _TITLE_SPLIT.split(title or "") if len(t) >= 2]
    out: list[str] = []
    seen: set[str] = set()
    for n in (1, 2, 3):
        for i in range(len(toks) - n + 1):
            kw = " ".join(toks[i : i + n])
            if kw.lower() not in seen:
                seen.add(kw.lower())
                out.append(kw)
    return out[:limit]


def exposure_scan(
    blog_id: str | None = None,
    posts: int = 20,
    min_volume: int = 100,
    per_post: int = 8,
    register: bool = True,
) -> dict:
    """내 글들이 실제로 어떤 키워드에서 몇 위에 떠 있는지 자동 스캔.

    제목 n-gram을 후보로 만들고 → 월간 검색량으로 실제 검색되는 말만 남긴 뒤 →
    블로그 검색 상위 100위에서 내 글을 찾는다. 슈퍼멤버스류 등급이 보는 재료
    (상위노출 키워드 × 월간 검색량)와 같지만, 순위는 openapi 정확도순 근사라
    통합검색 블로그탭 순서와는 다를 수 있다(rank.py 모듈 주석 참고).

    score는 1페이지(10위 이내) 키워드들의 월간 검색량 합 — 공식 등급 공식이 아니라
    '상위노출 키워드의 검색량이 클수록 가산점'이라는 공개 설명을 그대로 옮긴 대리 지표.
    """
    from autoblog.collect.blog_posts import fetch_popular_posts, fetch_recent_posts

    env = load_env()
    blog_id = (blog_id or env.naver_blog_id or "").strip()
    if not blog_id:
        raise ValueError("블로그 ID가 없어요 (.env의 NAVER_BLOG_ID)")
    if not env.has_searchad:
        raise RuntimeError("검색광고 API 키(.env NAVER_SEARCHAD_*)가 필요해요 — 검색량으로 후보를 걸러요")

    items = fetch_recent_posts(blog_id, posts)
    try:  # 인기글은 오래돼도 순위가 살아 있는 글 — 있으면 얹고 실패하면 최신글만으로
        items += fetch_popular_posts(blog_id, 5)
    except Exception:  # noqa: BLE001
        pass
    uniq: list[dict] = []
    seen_posts: set[str] = set()
    for p in items:
        if p["logNo"] not in seen_posts:
            seen_posts.add(p["logNo"])
            uniq.append(p)

    rows: list[dict] = []
    obs: list[dict] = []
    missed = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in uniq:
        vols = search_volumes(_title_keywords(p["title"]))
        hot = sorted(
            ((k, v.get("volume") or 0) for k, v in vols.items() if (v.get("volume") or 0) >= min_volume),
            key=lambda x: -x[1],
        )[:per_post]
        for kw, vol in hot:
            try:
                data = _search_blog_full(kw)
            except Exception:  # noqa: BLE001 — 개별 키워드 실패는 건너뛰고 나머지로 스캔
                continue
            rank = find_rank(data.get("items", []), p["url"])
            # 이긴 것도 진 것도 다 남긴다 — '이 정도 경쟁이면 내가 몇 번 이겼나'의 표본이 된다
            obs.append({"keyword": kw, "volume": vol, "total": int(data.get("total", 0)),
                        "rank": rank, "t": now})
            if rank is None:
                missed += 1
                continue
            rows.append(
                {"keyword": kw, "volume": vol, "rank": rank, "total": int(data.get("total", 0)),
                 "url": p["url"], "title": p["title"]}
            )
            if register and rank <= 30:  # 볼 만한 것만 추적에 넣어 추이를 쌓는다
                add_entry(kw, p["url"])
        time.sleep(0.3)  # keywordstool 연속 호출 제한 회피
    rows.sort(key=lambda r: (r["rank"], -r["volume"]))
    _save_obs(obs)
    return {
        "blog": blog_id,
        "posts": len(uniq),
        "rows": rows,
        "missed": missed,
        "score": sum(r["volume"] for r in rows if r["rank"] <= 10),
        "top10": sum(1 for r in rows if r["rank"] <= 10),
        "top30": sum(1 for r in rows if r["rank"] <= 30),
    }


_SM_RANK_URL = "https://api.supermembers.co.kr/influencer/rank"  # 슈퍼멤버스 rank 앱이 쓰는 공개 엔드포인트
# 슈멤 score 근사 — 계정 8개(키워드 2~1000개, score 11~27,000)에 그리드 서치로 맞춘 값.
# 평균 로그오차 0.11이고 지수는 둘 다 뚜렷한 최소점이다(a는 0.3/0.5에서, b는 0.6/1.0에서 악화).
# 핵심은 상수가 아니라 지수: 검색량은 ^0.4로 완만하고(400배 차이가 11배), 순위는 거의 반비례다.
# 그래서 '검색량 큰 키워드 하위권'보다 '작은 키워드 1위'가 언제나 이긴다.
_SM_A, _SM_B, _SM_C = 0.4, 0.85, 4.729


def sm_score(volume: int, pos: int) -> float:
    """키워드 하나가 슈멤 score에 얹는 점수(근사). volume=월간 검색량, pos=노출 순위."""
    if not volume or not pos or pos < 1:
        return 0.0
    return _SM_C * float(volume) ** _SM_A / float(pos) ** _SM_B


def sm_rank(account: str | None = None) -> dict:
    """슈퍼멤버스가 실제로 집계 중인 내 등급·키워드를 원본 그대로 읽는다.

    흉내 내지 않는 이유: 슈멤은 아무 단어나 세지 않는다. 카테고리(cat1/cat2)가 달린
    자기네 키워드 DB에 등록된 단어만, 그것도 키워드별 상위 50명(일부 60명) 블로거
    목록에 내 아이디가 들어 있을 때만 집계한다. 제목 n-gram으로 찾는 exposure_scan으로는
    재현이 안 되는 기준이라(1위를 해도 DB에 없는 단어면 0점) 원본을 읽는 게 정확하다.

    share는 sm_score() 기준 기여도 추정치다. 비공식 엔드포인트라 언제든 바뀔 수 있고,
    그때는 이 함수만 죽는다(exposure_scan은 영향 없음).
    """
    account = (account or load_env().naver_blog_id or "").strip()
    if not account:
        raise ValueError("블로그 ID가 없어요 (.env의 NAVER_BLOG_ID)")
    resp = requests.get(
        _SM_RANK_URL,
        params={"account": account},
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://rank.supermembers.co.kr/"},
        timeout=15,
    )
    resp.raise_for_status()
    rows = (resp.json() or {}).get("value") or []
    if not rows:
        raise RuntimeError(f"슈퍼멤버스에 집계된 계정이 아니에요 (account={account})")
    v = rows[0]
    kws = []
    for k in v.get("keywords") or []:
        ids = k.get("ids") or []
        if account not in ids:
            continue  # 목록 밖이면 집계 대상이 아니다
        pos = ids.index(account) + 1
        vol = int(k.get("mmqccnt") or 0)
        kws.append({
            "keyword": k.get("name", ""),
            "volume": vol,
            "pos": pos,
            "of": len(ids),
            "cat": "/".join(x for x in (k.get("cat1"), k.get("cat2")) if x),
            "weight": sm_score(vol, pos),  # 점수 기여 추정
        })
    total = sum(k["weight"] for k in kws) or 1
    for k in kws:
        k["share"] = round(k["weight"] / total * 100, 1)
    kws.sort(key=lambda k: -k["weight"])
    hist = [
        {"week": h.get("week"), "rank": h.get("rank"), "score": h.get("score"),
         "adFee": h.get("adFee"), "percentage": h.get("percentage")}
        for h in (v.get("histories") or [])
    ][-9:]
    return {
        "account": account,
        "rank": v.get("rank"),
        "percentage": v.get("percentage"),  # 상위 %
        "adFee": v.get("adFee"),  # 슈멤이 매긴 광고 단가(원)
        "score": v.get("score"),
        "visitor_ex": v.get("visitorEx"),
        "updated": v.get("updatedAt"),
        "categories": v.get("categories") or {},
        "keywords": kws,
        "history": hist,
    }


_OBS_PATH = DATA_DIR / "exposure_obs.json"
# 경쟁(문서수) 구간 — 자릿수로 끊는다. 구간 경계는 임의지만 승률은 실측이다.
_COMP_BANDS = [(0, 1_000), (1_000, 10_000), (10_000, 100_000), (100_000, 10**12)]


def _save_obs(obs: list[dict]) -> None:
    """스캔에서 나온 (경쟁, 내 순위) 관측을 누적 저장 — 승률 표본이 발행할수록 늘어난다."""
    if not obs:
        return
    try:
        old = json.loads(_OBS_PATH.read_text(encoding="utf-8")) if _OBS_PATH.exists() else []
    except (json.JSONDecodeError, OSError):
        old = []
    seen = {(o.get("keyword"), o.get("t")) for o in old}
    old += [o for o in obs if (o["keyword"], o["t"]) not in seen]
    _OBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OBS_PATH.write_text(json.dumps(old[-5000:], ensure_ascii=False), encoding="utf-8")


def win_rates(path=None) -> list[dict]:
    """내 블로그 실측 승률 — 경쟁 구간별로 '1페이지에 든 비율'.

    '준최 7' 같은 블로그 지수 등급은 네이버 공식 지표가 아니고 공개된 공식도 없어서
    입력값으로 쓸 수 없다. 대신 같은 걸 훨씬 정확하게 대신하는 게 내 블로그의 실제
    전적이다 — 같은 경쟁 구간에서 내가 실제로 몇 번 1페이지에 들었는지.
    표본이 적으면(n<10) 참고용이고, 발행·스캔을 반복할수록 정확해진다.
    """
    p = path or _OBS_PATH
    try:
        obs = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return []
    out = []
    for lo, hi in _COMP_BANDS:
        band = [o for o in obs if lo <= (o.get("total") or 0) < hi]
        if not band:
            continue
        out.append({
            "lo": lo, "hi": hi, "n": len(band),
            "top10": sum(1 for o in band if o.get("rank") and o["rank"] <= 10) / len(band),
            "top30": sum(1 for o in band if o.get("rank") and o["rank"] <= 30) / len(band),
        })
    return out


def win_rate_for(total: int, rates: list[dict] | None = None) -> dict | None:
    """문서 수(경쟁)에 해당하는 실측 승률 한 줄. 표본 없으면 None."""
    for r in win_rates() if rates is None else rates:
        if r["lo"] <= (total or 0) < r["hi"]:
            return r
    return None


def expected_score(volume: int, total: int, rates: list[dict] | None = None) -> dict | None:
    """기대 점수 = 내 실측 1페이지 승률 × 3위 잡았을 때의 슈멤 점수.

    점수만 크고 못 잡는 키워드를 걸러내는 게 목적이다 — 문서 10만짜리는 점수가
    아무리 커도 승률이 0이면 기대값도 0이다. 표본(n)이 작으면 신뢰도가 낮으니 같이 준다.
    """
    w = win_rate_for(total, rates)
    if w is None or not volume:
        return None
    return {"win": round(w["top10"], 3), "n": w["n"],
            "ev": round(w["top10"] * sm_score(volume, 3), 1)}
