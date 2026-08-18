"""컴포넌트(사진·인용구·스티커·구분선) 뒤 '첫 줄 증발' 전수 점검 — 새 글 경로. 저장 안 함.

각 컴포넌트를 넣은 직후 두 줄짜리 텍스트 블록을 치고, 첫 줄이 살아남는지 본다.
구분선 정렬이 HR을 객체 선택으로 남겨 첫 줄을 삼키던 사고(2026-08-18)의 형제 사례 확인용.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_blank_after_title import _DUMP_JS  # noqa: E402

from autoblog.collect.selectors import SMART_EDITOR  # noqa: E402
from autoblog.publish.plan import PublishBlock, QUOTE_META  # noqa: E402
from autoblog.publish.editor import BlogPublisher  # noqa: E402


def main() -> int:
    photo = next(iter(sorted(Path("data/uploads").glob("*.png"))), None)
    if photo is None:
        print("[probe] data/uploads에 샘플 사진이 없음 — 사진 항목은 건너뜀.")
    pub = BlogPublisher(headless=True).start()
    try:
        if not pub.wait_for_login():
            print("로그인 필요"); return 1
        page = pub._page
        pub.open_write_page()
        pub._type_title("컴포넌트 뒤 첫 줄 증발 점검")
        page.click(SMART_EDITOR["content_component"])
        pub._reset_text_toggles()
        pub._type_text_block(PublishBlock(kind="text", text="시작 줄", align="center"))

        def after(tag: str):
            pub._type_text_block(
                PublishBlock(kind="text", text=f"{tag}첫줄\n{tag}둘째줄", align="center")
            )

        pub._insert_divider(1, align="center"); after("구분선")
        pub._insert_quote("인용구 한마디", QUOTE_META["quotation_underline"][0]); after("인용구")
        if photo is not None:
            pub._insert_image(str(photo)); after("사진")
        print("\n--- 결과 ---")
        rows = page.evaluate(_DUMP_JS)
        for i, r in enumerate(rows[:24]):
            mark = "  <<< 빈 문단" if r["empty"] else ""
            print(f"  [{i:02d}] {r['kind']:8s} p{r['p']} {r['text']!r}{mark}")
        texts = {r["text"] for r in rows}
        print()
        for tag in ("구분선", "인용구", "사진"):
            if tag == "사진" and photo is None:
                continue
            ok = f"{tag}첫줄" in texts
            print(f"  {tag} 뒤 첫 줄: {'✅ 살아있음' if ok else '❌ 증발'}")
        print("\n[probe] 저장하지 않고 종료.")
        return 0
    finally:
        pub.close(save_session=False)


if __name__ == "__main__":
    raise SystemExit(main())
