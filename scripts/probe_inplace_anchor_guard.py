"""in-place 앵커 가드 검증 — Enter가 씹히는 고장 상황에서 저장 대신 중단하는지 확인.

실사고(2026-08-11 화성 장학금 글): 에디터 지연으로 제목 끝 Enter가 계속 무시돼 캐럿이
이전 위치에 남았고, 역순 삽입되는 모든 블록이 그 자리에 짜깁기돼 문서가 통째로 뒤섞였다
(인용구가 뒤 본문을 삼키고, 서론·마무리가 한 컴포넌트에 역순 병합, 소제목 2개 유실).
이 프로브는 그 고장을 Enter 무시 몽키패치로 재현해 ① RuntimeError로 중단하는지
② 센티널(‡)이 제목에 남지 않는지 검증한다. 일회용 ZZ 글 생성→검증→삭제.

실행: .venv/bin/python scripts/probe_inplace_anchor_guard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoblog.publish.editor import BlogPublisher  # noqa: E402
from autoblog.publish.plan import PublishBlock, PublishPlan  # noqa: E402

TITLE = "ZZ앵커 가드 프로브 지우세요"


def main() -> int:
    pub = BlogPublisher(headless=True).start()
    try:
        if not pub.is_logged_in():
            print("no login")
            return 1
        page = pub._page
        print("[1] 시드 생성…")
        seed = PublishPlan(title=TITLE, blocks=[
            PublishBlock(kind="text", text="시드 본문.", align="center"),
        ])
        pub.publish(seed, save=True, submit=False, prune_same_title=False)

        # 고장 시뮬레이션: Enter 키만 씹히게 (SE 지연/오버레이로 Enter가 무시되던 실사고 재현)
        orig_press = page.keyboard.press

        def broken_press(key, **kw):
            if key == "Enter":
                print("   (Enter 씹힘 시뮬레이션)")
                return None
            return orig_press(key, **kw)

        page.keyboard.press = broken_press

        plan = PublishPlan(title=TITLE, blocks=[
            PublishBlock(kind="text", text="새 본문 P1", align="center"),
            PublishBlock(kind="quote", text="Q1 소제목", align="center"),
        ])
        print("[2] publish_inplace — RuntimeError 기대…")
        try:
            pub.publish_inplace(plan, draft_title=TITLE, save=False,
                                clean_imported=True, mark_ai=False)
            print("❌ 중단되지 않음 — 가드 실패")
            return 1
        except RuntimeError as exc:
            print(f"✅ 중단됨: {exc}")

        page.keyboard.press = orig_press
        title_now = page.evaluate(
            "()=>{const t=document.querySelector('.se-component.se-documentTitle');"
            "return t?(t.textContent||''):'(없음)';}")
        clean = title_now.replace("​", "").strip()
        mark_free = "‡" not in title_now
        print(f"[3] 제목 상태: {clean!r} / 센티널 잔존 없음: {mark_free}")
        print("✅ PASS" if mark_free else "❌ 제목에 센티널 잔존")
        return 0
    finally:
        try:
            deleted = 0
            for _ in range(3):
                pub.open_write_page()
                pub._open_draft_list()
                idx = pub._resolve_draft_idx(TITLE, "")
                if idx is None:
                    break
                if not pub._delete_draft_at(idx):
                    break
                deleted += 1
            print(f"[4] ZZ 삭제: {deleted}건")
        except Exception as exc:  # noqa: BLE001
            print("[4] 삭제 실패:", exc)
        pub.close(save_session=False)


if __name__ == "__main__":
    raise SystemExit(main())
