"""in-place 저장 관문 검증 — 뒤섞인 조립을 재현해 저장이 거부되는지 + 원본 무사한지 실측.

실사고(2026-08-11 화성 장학금 글)의 최종 방어선 검증. 앵커를 무력화(no-op 몽키패치)해
블록이 엉뚱한 자리에 짜깁기되는 상황을 만들고:
  ① publish_inplace(save=True)가 저장 '전' 최종 대조에서 RuntimeError로 중단하는지
  ② 중단 후 원본 임시저장 글이 갱신되지 않았는지(자동저장 누출 포함 실측)
  ③ 패치를 풀고 다시 저장하면 정상 순서로 저장되는지(양성 대조)
일회용 ZZ 글 생성→검증→삭제.

실행: .venv/bin/python scripts/probe_inplace_save_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoblog.collect.selectors import SMART_EDITOR  # noqa: E402
from autoblog.publish.editor import BlogPublisher  # noqa: E402
from autoblog.publish.plan import PublishBlock, PublishPlan  # noqa: E402

TITLE = "ZZ저장 관문 프로브 지우세요"
SEED_TEXT = "관문 시드 본문 문단입니다."

_BODY_JS = r"""
() => [...document.querySelectorAll('.se-component')].map(c => {
  const cls = c.className.toString();
  if (/se-documentTitle/.test(cls)) return null;
  if (/se-quotation/.test(cls)) return 'Q:' + (c.textContent || '').trim().slice(0, 12);
  if (/se-text(\s|$)/.test(cls)) {
    const ps = [...c.querySelectorAll('p.se-text-paragraph')]
      .map(p => (p.textContent || '').trim()).filter(Boolean);
    return ps.length ? 'T:' + ps.join('/').slice(0, 40) : null;
  }
  return null;
}).filter(Boolean)
"""


def _load_body(pub: BlogPublisher) -> list[str]:
    pub.open_write_page()
    pub._open_draft_list()
    idx = pub._resolve_draft_idx(TITLE, "")
    if idx is None:
        return ["(글 없음)"]
    page = pub._page
    page.query_selector_all(SMART_EDITOR["draft_item_button"])[idx].click()
    page.wait_for_timeout(1500)
    conf = page.query_selector(SMART_EDITOR["draft_load_confirm"])
    if conf and conf.is_visible():
        conf.click()
    page.wait_for_timeout(2500)
    return page.evaluate(_BODY_JS)


def main() -> int:
    fails = 0
    pub = BlogPublisher(headless=True).start()
    try:
        if not pub.is_logged_in():
            print("[probe] 로그인 세션 없음 — 중단.")
            return 1
        print("[1] 시드 임시저장 글 생성…")
        seed = PublishPlan(title=TITLE, blocks=[
            PublishBlock(kind="text", text=SEED_TEXT, align="center"),
        ])
        pub.publish(seed, save=True, submit=False, prune_same_title=False)

        plan = PublishPlan(title=TITLE, blocks=[
            PublishBlock(kind="text", text="새 본문 P1", align="center"),
            PublishBlock(kind="quote", text="Q1 소제목", align="center"),
            PublishBlock(kind="text", text="새 본문 P2", align="center"),
        ])

        # ── ① 앵커 무력화 → 짜깁기 재현 → 관문이 저장 거부해야 함
        pub._anchor_before_first_media = lambda: True  # no-op(실사고의 캐럿 유실 재현)
        print("[2] 앵커 무력화 후 publish_inplace(save=True) — 관문 중단 기대…")
        try:
            pub.publish_inplace(plan, draft_title=TITLE, save=True,
                                clean_imported=True, mark_ai=False)
            print("   ❌ 관문이 저장을 막지 못함")
            fails += 1
        except RuntimeError as exc:
            caught = "최종 검증" in str(exc) or "삽입 위치" in str(exc)
            print(f"   {'✅' if caught else '❌'} 중단됨: {exc}")
            fails += 0 if caught else 1
        del pub.__dict__["_anchor_before_first_media"]  # 패치 해제(클래스 원본 복원)

        # ── ② 원본 무사 확인(자동저장 누출 실측 포함)
        body = _load_body(pub)
        intact = any(SEED_TEXT[:8] in row for row in body)
        print(f"[3] 중단 후 임시저장 본문: {body}")
        print(f"   {'✅ 원본 무사' if intact else '❌ 원본이 변조됨(자동저장 누출?)'}")
        fails += 0 if intact else 1

        # ── ③ 양성 대조: 정상 앵커로 재발행 → 저장 성공 + 순서 일치
        print("[4] 정상 재발행(save=True)…")
        warnings, _ = pub.publish_inplace(plan, draft_title=TITLE, save=True,
                                          clean_imported=True, mark_ai=False)
        body = _load_body(pub)
        joined = " | ".join(body)
        ok = (joined.find("새 본문 P1") >= 0 and joined.find("Q1") > joined.find("새 본문 P1")
              and joined.find("새 본문 P2") > joined.find("Q1"))
        print(f"   저장 후 본문: {body}")
        print(f"   {'✅ 순서 일치 저장' if ok else '❌ 순서 불일치'}")
        fails += 0 if ok else 1
        for w in warnings:
            print("   [warn]", w)
        print(f"\n[결과] {'✅ PASS' if fails == 0 else f'❌ FAIL {fails}건'}")
        return 0 if fails == 0 else 1
    finally:
        try:
            deleted = 0
            for _ in range(4):
                pub.open_write_page()
                pub._open_draft_list()
                idx = pub._resolve_draft_idx(TITLE, "")
                if idx is None:
                    break
                if not pub._delete_draft_at(idx):
                    break
                deleted += 1
            print(f"[5] ZZ 글 삭제: {deleted}건")
        except Exception as exc:  # noqa: BLE001
            print(f"[5] ZZ 글 삭제 실패({exc}) — 목록에서 ‘{TITLE}’ 직접 삭제 필요")
        pub.close(save_session=False)


if __name__ == "__main__":
    raise SystemExit(main())
