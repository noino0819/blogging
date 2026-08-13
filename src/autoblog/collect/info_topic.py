"""정보글 주제 준비 — 목차(자동완성) + 상위 글 근거 수집 + LLM 팩트 시트.

정보 글은 재료(메모)가 곧 글의 전부라 준비가 손이 많이 갔다: 연관 검색어로 목차를
뽑고, 상위 글들을 읽고, 교차 확인된 사실만 추려 메모를 만드는 일. 이 모듈이 그
수작업을 한 번의 호출로 만든다 — 웹UI '주제 준비' 버튼의 백엔드.

수집은 검색 오픈API + PostView HTML(비로그인)이라 발행용 네이버 세션과 충돌하지
않는다(프로브 세션 동시성 금지 원칙과 무관).
"""

from __future__ import annotations

import re
from datetime import datetime

import requests

from autoblog.llm import chat
from autoblog.rank import _post_key, _related_terms, _search_blog

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_WS_RE = re.compile(r"[ \t ]+")
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# 팩트 추출 지시 — 원문에 명시된 것만, 수치는 교차 일치 우선. 지어내기 금지가 핵심.
_EXTRACT_SYSTEM = """너는 블로그 글 재료를 준비하는 리서처다. 아래 원문들에서 주제에 대한 사실만 추려라.

규칙:
- 원문에 명시된 사실만. 원문에 없는 지식을 보태지 마라.
- 수치·기간·온도는 두 개 이상 원문이 일치하는 값을 우선하고, 원문마다 다르면 "원문마다 다름(A: x, B: y)"로 표기하거나 빼라.
- 각 사실 끝에 근거 원문 번호를 [1][3] 형식으로 붙여라.
- 광고·협찬 문구, 특정 가게·쇼핑몰 홍보, 개인 경험담은 제외. 일반화할 수 있는 정보만.
- 사실 8~15개, 한 줄에 하나씩 "- "로 시작. 다른 말은 일절 쓰지 마라."""


def _fetch_post_text(link: str, max_chars: int = 4000) -> str:
    """네이버 블로그 글 링크 → 서버 렌더 PostView HTML → 본문 위주 텍스트."""
    key = _post_key(link or "")
    if not key:
        return ""
    url = f"https://blog.naver.com/PostView.naver?blogId={key[0]}&logNo={key[1]}"
    try:
        html = requests.get(url, headers=_UA, timeout=10).text
    except requests.RequestException:
        return ""
    # 본문 컨테이너 이후만 잘라 사이드바·헤더 노이즈를 줄인다(없으면 전체).
    idx = html.find("se-main-container")
    if idx > 0:
        html = html[idx:]
    text = _TAG_RE.sub(" ", _SCRIPT_RE.sub(" ", html))
    text = _WS_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)[:max_chars]


def prepare_info_sheet(topic: str, n_sources: int = 4, model: str | None = None) -> dict:
    """주제 → {sheet, terms, sources}. sheet는 메모칸에 그대로 넣는 팩트 시트 텍스트.

    목차는 자동완성(실제 검색어), 사실은 블로그 상위 글에서 LLM이 추출(출처 번호 포함).
    수치 환각을 원천 차단할 수는 없으므로 시트에 출처 URL을 남겨 발행 전 확인을 유도한다.
    """
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("주제가 비어 있어요")
    try:
        terms = [t for t in _related_terms(topic) if t.replace(" ", "") != topic.replace(" ", "")][:8]
    except Exception:  # noqa: BLE001 — 목차는 부가 재료, 자동완성 실패해도 시트는 만든다
        terms = []

    sources: list[dict] = []
    bodies: list[str] = []
    for it in _search_blog(topic)[:12]:
        if len(sources) >= n_sources:
            break
        link = it.get("link", "")
        text = _fetch_post_text(link)
        if len(text) < 300:  # 본문이 사실상 안 잡힌 글은 근거로 못 쓴다
            continue
        title = _TAG_RE.sub("", it.get("title", "")).replace("&amp;", "&").strip()
        sources.append({"title": title, "link": link})
        bodies.append(text)
    if not bodies:
        raise RuntimeError("근거로 쓸 상위 글을 가져오지 못했어요 — 주제를 바꾸거나 잠시 후 다시 시도해 주세요")

    docs = "\n\n".join(f"### 원문 {i} — {s['title']}\n{b}" for i, (s, b) in enumerate(zip(sources, bodies), 1))
    facts = chat(
        [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": f"주제: {topic}\n\n{docs}"},
        ],
        model=model,
    ).strip()

    now = datetime.now()
    parts = [f"주제: {topic}"]
    if terms:
        parts.append("타깃 검색어: " + ", ".join([topic] + terms[:3]))
        parts.append("[커버할 내용 — 사람들이 실제 검색하는 것. 재료 있는 것만 소제목으로]\n" + "\n".join(f"- {t}" for t in terms))
    parts.append(f"[조사한 사실 — {now.year}년 {now.month}월 기준. 끝의 [번호]는 아래 출처, 본문에는 번호를 옮기지 말 것]\n{facts}")
    parts.append("[내 경험 — 직접 해본 것 두 줄만 채우고, 이 대괄호 안내줄은 지우세요]\n- \n- ")
    parts.append(
        "[출처 — 발행 전 수치가 맞는지 열어서 확인 권장. 이 목록은 본문에 절대 넣지 말 것]\n"
        + "\n".join(f"{i}. {s['title']} — {s['link']}" for i, s in enumerate(sources, 1))
    )
    return {"sheet": "\n\n".join(parts), "terms": terms, "sources": sources}
