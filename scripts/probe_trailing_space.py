"""강조 문단 꼬리 공백 원인 추적 프로브 — 1회성, 저장 안 함.

실측 배경(2026-08-13): 발행본 4개 전수 대조 결과 꼬리 공백은 '강조(색·서체) 적용
문단'에서만 발생(11/109 vs 일반 문단 0/215). 플랜 텍스트는 전 줄 strip이라 타이핑
원본에는 공백이 없다 → 에디터 상호작용 어딘가에서 생긴다. 어느 단계인지 특정한다.

모드:
  --forensic [제목키워드]   임시저장 글을 열어(저장 안 함) 문단별 꼬리 공백의 위치·
                            문자코드·span 구조를 덤프. 키워드 없으면 목록만 출력.
  --repro N                 새 글에서 퍼블리시와 동일한 타이핑→강조를 N회 반복하며
                            강조 하위 단계(선택/글자색/배경/서체/크기)마다 전 문단의
                            꼬리 공백을 추적. 트리거 단계를 특정한다.

실행: .venv/bin/python scripts/probe_trailing_space.py --forensic 택배
      .venv/bin/python scripts/probe_trailing_space.py --repro 20
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoblog.collect.selectors import SMART_EDITOR  # noqa: E402
from autoblog.publish.editor import BlogPublisher  # noqa: E402
from autoblog.publish.emphasis import EmphasisStyle  # noqa: E402

# ── 공통: 문단(텍스트·인용구) 꼬리 공백 덤프 ─────────────────────────────────
# ZWSP(200B)/FEFF는 SE 자리표시자라 제외하고, 눈에 보이는 공백류(20/A0/3000)만 잡는다.
_DUMP_JS = r"""
() => {
  const out = [];
  const push = (kind, p) => {
    const raw = p.textContent || '';
    const t = raw.replace(/[​﻿]/g, '');
    if (!t.trim()) return;
    const m = t.match(/[  　]+$/);
    const spans = [...p.querySelectorAll('span')].map(s => ({
      styled: !!(s.getAttribute('style') || '').match(/color/),
      cls: (s.className.toString().match(/se-f[fs]-?\S+/g) || []).join(','),
      tail: (s.textContent || '').slice(-3),
    }));
    out.push({
      kind, text: t.slice(0, 40),
      trail: m ? [...m[0]].map(c => c.charCodeAt(0).toString(16)) : [],
      spans,
    });
  };
  for (const p of document.querySelectorAll('.se-component.se-text .se-text-paragraph')) push('text', p);
  for (const q of document.querySelectorAll('.se-component.se-quotation .se-text-paragraph')) push('quote', q);
  return out;
}
"""


def dump(page):
    return page.evaluate(_DUMP_JS)


def trails(rows):
    """꼬리 공백 있는 문단만 [(kind, text, trail코드들)]로."""
    return [(r["kind"], r["text"], r["trail"]) for r in rows if r["trail"]]


# ── forensic: 임시저장 글 열어 실물 확인 ─────────────────────────────────────
def forensic(kw: str | None) -> int:
    pub = BlogPublisher().start()
    try:
        if not pub.is_logged_in():
            print("[probe] 로그인 세션 없음 — 중단.")
            return 1
        items = pub.list_drafts()
        for it in items:
            print(f"  [{it['idx']}] {it['title']!r} ({it['date']})")
        if not kw:
            return 0
        match = next((it for it in items if kw in (it.get("title") or "")), None)
        if match is None:
            print(f"[probe] 제목에 {kw!r} 포함된 임시저장 글 없음.")
            return 1
        print(f"\n[probe] 로드: {match['title']!r}")
        pub._load_draft_into_editor(match["idx"])
        pub._page.wait_for_timeout(1500)
        rows = dump(pub._page)
        bad = 0
        for r in rows:
            mark = ""
            if r["trail"]:
                bad += 1
                mark = f"  ◀◀ 꼬리공백 {r['trail']}"
            styled = any(s["styled"] for s in r["spans"])
            print(f"[{r['kind']}] {'S' if styled else '-'} {r['text']!r}{mark}")
            if r["trail"]:
                for s in r["spans"]:
                    print(f"      span styled={s['styled']} cls={s['cls']} tail={s['tail']!r}")
        print(f"\n[probe] 꼬리 공백 문단 {bad}/{len(rows)}. 저장 없이 종료.")
        return 0
    finally:
        pub.close(save_session=False)


# ── repro: 타이핑→강조 하위 단계별 추적 ──────────────────────────────────────
BIG = "천원 아끼는 재미가 쏠쏠"
DRIP = "아낀 택배비로 커피 한 잔이면 남는 장사죠"
BODY = "* 심지어 통창 매장인데 밖에서도 안이 잘 보여요"
CONTROL = "이 줄은 대조군으로 강조 없이 남는 문장이에요"
MID_TARGET = "통창 매장"

# 실제 config 값 그대로(structure_styles.yaml / emphasis.yaml preset 4)
ST_BIG = EmphasisStyle(text_color="#395D73", font_family="nanummaruburi", font_size="30")
ST_DRIP = EmphasisStyle(text_color="#4383BF", font_family="system", font_size="11")
ST_MID = EmphasisStyle(
    text_color="#eb7d7d", background_color="#fef3c7",
    font_family="nanumdasisijaghae", font_size="13",
)


def _apply_steps(pub, text: str, style: EmphasisStyle, log):
    """_apply_emphasis와 동일 호출을 단계별로 쪼개 각 단계 후 전 문단 꼬리 공백을 기록."""
    page = pub._page
    if not pub._select_body_text(text):
        print(f"    !! 선택 실패: {text!r}")
        return
    log(f"select:{text[:8]}")
    if style.text_color:
        pub._apply_color(SMART_EDITOR["toolbar_text_color"], style.text_color)
        log("color")
    if style.background_color:
        pub._apply_color(SMART_EDITOR["toolbar_bg_color"], style.background_color)
        log("bg")
    if style.font_family:
        pub._apply_font(style.font_family)
        log("font")
    if style.font_size:
        pub._apply_font_size(style.font_size)
        log("size")


def repro(n: int) -> int:
    pub = BlogPublisher().start()
    incidents = []
    try:
        if not pub.is_logged_in():
            print("[probe] 로그인 세션 없음 — 중단.")
            return 1
        pub.open_write_page()
        page = pub._page
        pub._type_title("ZZ_꼬리공백프로브_저장안함")
        page.click(SMART_EDITOR["content_component"])
        pub._reset_text_toggles()

        for it in range(1, n + 1):
            # 본문 클리어(퍼블리시 in-place 정리와 동일 메커니즘)
            page.click(SMART_EDITOR["content_component"])
            page.keyboard.press("ControlOrMeta+a")
            page.keyboard.press("Delete")
            page.wait_for_timeout(300)
            pub._apply_align("center")  # 실제 글과 동일하게 가운데 정렬
            for line in [BIG, DRIP, BODY, CONTROL]:
                page.keyboard.type(line, delay=4)
                page.keyboard.press("Enter")
            page.wait_for_timeout(500)

            base = trails(dump(page))
            if base:
                print(f"[{it}] !! 타이핑 직후부터 꼬리 공백: {base}")
            state = {"prev": base}

            def log(step, _it=it, _state=state):
                cur = trails(dump(page))
                if cur != _state["prev"]:
                    new = [r for r in cur if r not in _state["prev"]]
                    print(f"[{_it}] ▶ {step} 단계에서 변화: +{new}")
                    incidents.append((_it, step, new))
                    _state["prev"] = cur

            # 실제 퍼블리시와 동일: 문서 순서(위→아래)로 강조
            _apply_steps(pub, BIG, ST_BIG, log)
            _apply_steps(pub, DRIP, ST_DRIP, log)
            _apply_steps(pub, MID_TARGET, ST_MID, log)

            final = trails(dump(page))
            print(f"[{it}] 최종 꼬리공백 문단: {len(final)} {final if final else ''}")

        print(f"\n[probe] {n}회 중 트리거 {len(incidents)}건:")
        for it, step, new in incidents:
            print(f"  회차{it} 단계={step} → {new}")
        print("[probe] 저장 없이 종료.")
        return 0
    finally:
        pub.close(save_session=False)


# ── split: 어절 공백에 캐럿 + Enter = 발행본 흔적('…밖에서도 ') 재현/복구 검증 ──
FULL_LINE = "* 심지어 통창 매장인데 밖에서도 미용모습이 보여서 안심 ,,"
SPLIT_BEFORE = "미용모습이"  # 이 어절 '앞 공백' 위치를 클릭한다

_SPACE_RECT_JS = r"""
(args) => {
  const {line, word} = args;
  const roots = document.querySelectorAll('.se-component.se-text');
  for (const root of roots) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while (n = w.nextNode()) {
      const tc = n.textContent;
      if (!tc.includes(line.slice(0, 10))) continue;
      const i = tc.indexOf(' ' + word);
      if (i === -1) continue;
      const r = document.createRange();
      r.setStart(n, i); r.setEnd(n, i + 1);  // 공백 한 글자
      n.parentElement.scrollIntoView({block: 'center'});
      const b = r.getBoundingClientRect();
      return {x: b.x + b.width / 2, y: b.y + b.height / 2};
    }
  }
  return null;
}
"""


def split_test(rounds: int) -> int:
    pub = BlogPublisher().start()
    try:
        if not pub.is_logged_in():
            print("[probe] 로그인 세션 없음 — 중단.")
            return 1
        pub.open_write_page()
        page = pub._page
        pub._type_title("ZZ_분할복구프로브_저장안함")
        page.click(SMART_EDITOR["content_component"])
        pub._reset_text_toggles()
        ok_split, ok_heal = 0, 0
        for it in range(1, rounds + 1):
            page.click(SMART_EDITOR["content_component"])
            page.keyboard.press("ControlOrMeta+a")
            page.keyboard.press("Delete")
            page.wait_for_timeout(300)
            page.keyboard.type(FULL_LINE, delay=4)
            page.keyboard.press("Enter")
            page.keyboard.type("다음 문단 대조군이에요", delay=4)
            page.wait_for_timeout(400)

            # 1) 어절 공백 클릭 → Enter (빗나간 앵커 Enter 시뮬레이션)
            pt = page.evaluate(_SPACE_RECT_JS, {"line": FULL_LINE, "word": SPLIT_BEFORE})
            if not pt:
                print(f"[{it}] 공백 좌표 못 찾음 — 건너뜀")
                continue
            page.mouse.click(pt["x"], pt["y"])
            page.wait_for_timeout(200)
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            rows = dump(page)
            t = trails(rows)
            texts = [r["text"] for r in rows]
            split_shape = any(r["trail"] for r in rows)
            print(f"[{it}] 분할 후 문단: {texts} | 꼬리공백: {t}")
            if split_shape:
                ok_split += 1

            # 2) 실패 브랜치 복구: '실제' _sentinel_check 경로 호출(문서에 사진이 없어
            #    미디어 앵커 검증은 확정 실패 → 새 분할 복구 브랜치가 발동해야 함)
            anchored = pub._sentinel_check(
                pub._MEDIA_ANCHOR_VERIFY_JS,
                {"mark": pub._ANCHOR_SENTINEL, "kind": "image", "n": 0, "videoSel": ""},
            )
            print(f"[{it}] _sentinel_check 반환(앵커성공?): {anchored} (False 기대)")
            page.wait_for_timeout(300)
            rows2 = dump(page)
            texts2 = [r["text"] for r in rows2]
            healed = any(FULL_LINE[:20] in r["text"] and not r["trail"] for r in rows2)
            print(f"[{it}] 복구 후 문단: {texts2} | 복구 {'성공' if healed else '실패'}")
            if healed:
                ok_heal += 1
        print(f"\n[probe] 분할 재현 {ok_split}/{rounds}, 복구 성공 {ok_heal}/{rounds}. 저장 없이 종료.")
        return 0
    finally:
        pub.close(save_session=False)


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--forensic":
        return forensic(args[1] if len(args) > 1 else None)
    if args and args[0] == "--repro":
        return repro(int(args[1]) if len(args) > 1 else 10)
    if args and args[0] == "--split":
        return split_test(int(args[1]) if len(args) > 1 else 3)
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
