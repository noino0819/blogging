"""헤더(대제목·드립) 빈 줄 E2E 회귀 확인 — 실제로 임시저장하고, 저장본을 다시 열어 판정.

새 글 경로(publish)와 불러오기 경로(publish_inplace)를 같은 초안으로 각각 돌려서,
대제목과 드립 사이에 빈 문단이 끼는지 실물로 본다. 초안은 두 가지 헤더 표기를 쓴다:
  A) 드립과 태그줄 사이에 빈 줄 있음 → plan의 emit_drip_block 경로
  B) 드립 바로 다음 줄이 태그줄     → plan의 consume_tag_line 경로

테스트용 임시저장 글은 끝나고 지운다(제목 완전일치 항목만).
실행: uv run python scripts/probe_e2e_header_blank.py [--keep]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_blank_after_title import _DUMP_JS  # noqa: E402

from autoblog.collect.selectors import SMART_EDITOR  # noqa: E402
from autoblog.draft.generate import DraftResult  # noqa: E402
from autoblog.publish.editor import BlogPublisher  # noqa: E402
from autoblog.publish.plan import build_publish_plan, load_structure_styles  # noqa: E402

TITLE_A = "자동확인용 임시저장 헤더 빈줄 점검 가 유형"
TITLE_B = "자동확인용 임시저장 헤더 빈줄 점검 나 유형"

_BODY = """
사실 별 기대 없이 산 염색약이었어요.
6년 내내 다른 브랜드 쿨블랙만 썼거든요.

1. 두피는 하나도 안 아파요

바르는 동안 따가움이 전혀 없었어요.
헹굴 때도 편했습니당 .ᐟ
"""

# A: 드립 뒤에 빈 줄 → emit_drip_block 경로
DRAFT_A = f"""{TITLE_A}

이걸 이제 써봤다니 억울해요

6년째 쿨블랙에 정착했습니당 .ᐟ

#테스트태그 #헤더점검 #빈줄확인
{_BODY}"""

# B: 드립 바로 다음 줄이 태그줄 → consume_tag_line 경로
DRAFT_B = f"""{TITLE_B}

이걸 이제 써봤다니 억울해요
6년째 쿨블랙에 정착했습니당 .ᐟ
#테스트태그 #헤더점검 #빈줄확인
{_BODY}"""


def _plan(text: str):
    return build_publish_plan(
        DraftResult(text=text), structure_styles=load_structure_styles()
    )


def _open_draft(pub: BlogPublisher, title: str) -> bool:
    """제목이 정확히 일치하는 임시저장 글을 열어 본문을 로드한다."""
    page = pub._page
    pub.open_write_page()
    pub._open_draft_list()
    items = pub._read_draft_items()
    k = next(
        (i for i, it in enumerate(items) if (it.get("title") or "").strip() == title), None
    )
    if k is None:
        print(f"  [!] 저장본을 목록에서 못 찾음: {title!r}")
        return False
    buttons = page.query_selector_all(SMART_EDITOR["draft_item_button"])
    buttons[k].click()
    page.wait_for_timeout(1500)
    conf = page.query_selector(SMART_EDITOR["draft_load_confirm"])
    if conf and conf.is_visible():
        conf.click()
    page.wait_for_timeout(2500)
    return True


def _check(pub: BlogPublisher, label: str, title: str, plan) -> bool:
    """저장본을 열어 (1) 헤더에 빈 문단이 끼는지 (2) 플랜 내용이 다 들어갔는지 판정."""
    if not _open_draft(pub, title):
        return False
    rows = pub._page.evaluate(_DUMP_JS)
    print(f"\n----- {label} -----")
    for i, row in enumerate(rows[:10]):
        mark = "   <<< 빈 문단" if row["empty"] else ""
        print(f"  [{i:02d}] {row['kind']:8s} p{row['p']} {row['text']!r}{mark}")
    # 컴포넌트 단위로 자른다(문단 번호 p가 0으로 돌아가면 새 컴포넌트).
    comps: list[list[dict]] = []
    for row in rows:
        if row["p"] == 0:
            comps.append([])
        comps[-1].append(row)
    # 제목 다음 첫 텍스트 컴포넌트 = 헤더(대제목 줄들 + 드립). 마지막 문단은 블록 끝
    # Enter가 남기는 자리라 빼고, 그 앞에 빈 문단이 있으면 헤더가 벌어진 것.
    header = next((c for c in comps if c[0]["kind"] == "text"), [])
    gap = [r for r in header[:-1] if r["empty"]]
    # 내용 누락은 저장 전 관문과 같은 대조로 잡는다(구분선 뒤 첫 줄 증발 같은 사고).
    misses = pub._verify_inplace_result(plan, set(), check_videos=False)
    ok = not gap and not misses
    if gap:
        print("  판정: ❌ 헤더에 빈 문단 있음")
    if misses:
        print("  판정: ❌ 본문 누락 —", "; ".join(misses))
    if ok:
        print("  판정: ✅ 헤더 붙어 있고 본문 누락 없음")
    return ok


def main() -> int:
    keep = "--keep" in sys.argv
    ss_ok = True
    pub = BlogPublisher(headless=True).start()
    try:
        if not pub.wait_for_login():
            print("[probe] 네이버 로그인 필요 — 중단.")
            return 1
        # 1) 새 글 경로 — A 유형
        print("[1/3] 새 글(publish) — A 유형 저장 중…")
        pub.publish(_plan(DRAFT_A), save=True, submit=False, prune_same_title=True)
        ss_ok &= _check(pub, "새 글(publish) · A 유형", TITLE_A, _plan(DRAFT_A))

        # 2) 새 글 경로 — B 유형
        print("\n[2/3] 새 글(publish) — B 유형 저장 중…")
        pub.publish(_plan(DRAFT_B), save=True, submit=False, prune_same_title=True)
        ss_ok &= _check(pub, "새 글(publish) · B 유형", TITLE_B, _plan(DRAFT_B))

        # 3) 불러오기 경로 — 방금 저장한 A 글을 같은 플랜으로 in-place 재저장
        print("\n[3/3] 불러오기(publish_inplace) — A 글 재저장 중…")
        pub.publish_inplace(_plan(DRAFT_A), draft_title=TITLE_A, photo_paths=[], save=True)
        ss_ok &= _check(pub, "불러오기(publish_inplace) · A 유형", TITLE_A, _plan(DRAFT_A))
    finally:
        if not keep:
            try:
                for t in (TITLE_A, TITLE_B):
                    pub.delete_imported_draft(t, keep_title="")  # 같은 제목 전부 삭제
                print("\n[probe] 테스트용 임시저장 글 정리 완료.")
            except Exception as exc:  # noqa: BLE001
                print(f"\n[probe] 정리 실패({exc}) — 임시저장 목록에서 직접 지워주세요.")
        pub.close(save_session=False)
    print("\n[probe] 결과:", "✅ 전부 통과" if ss_ok else "❌ 실패 있음")
    return 0 if ss_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
