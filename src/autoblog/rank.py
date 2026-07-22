"""키워드 순위 추적 — 게시한 글이 블로그 검색에서 몇 위에 뜨는지 실측.

블로그 검색 API(sort=sim, 상위 100위)는 블로그탭 정확도순 근사치다 —
통합검색 스마트블록 순서와 다를 수 있고 AI 브리핑 인용 여부는 알 수 없다.
목적은 글별 노출 추이(진입·등락·이탈)를 데이터로 남겨 감이 아닌 실측으로
검증하는 것. 검색 API 키(.env)를 그대로 쓴다(일 25,000회 무료).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import requests

from autoblog.config import DATA_DIR, load_env

_BLOG_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"
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
    return {"keyword": keyword, "total": data.get("total", 0), "mine": mine, "top": top}


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
