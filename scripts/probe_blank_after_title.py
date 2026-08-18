"""임시저장 글의 '제목 뒤 / 대제목 뒤 빈 줄' 실물 확인 — 읽기 전용, 저장 안 함.

유저 보고: 제목 뒤와 대제목 뒤에 빈 줄이 들어간다. 기존 probe_drip_inspect_draft는
빈 문단을 건너뛰어(!t continue) 이 증상을 볼 수 없다. 여기선 제목 컴포넌트의 문단 수와
본문 앞쪽 문단을 '빈 문단 포함'으로 전부 덤프한다.

실행: uv run python scripts/probe_blank_after_title.py [제목키워드 ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoblog.collect.selectors import SMART_EDITOR  # noqa: E402
from autoblog.publish.editor import BlogPublisher  # noqa: E402

_DUMP_JS = r"""
() => {
  const clean = s => (s || '').replace(/[​﻿]/g, '');
  const out = [];
  for (const c of document.querySelectorAll('.se-component')) {
    const cls = c.className.toString();
    let kind = 'etc';
    if (/se-documentTitle/.test(cls)) kind = 'TITLE';
    else if (/se-text(\s|$)/.test(cls)) kind = 'text';
    else if (/se-image/.test(cls)) kind = 'image';
    else if (/se-video/.test(cls)) kind = 'video';
    else if (/se-horizontalLine/.test(cls)) kind = 'divider';
    else if (/se-sticker/.test(cls)) kind = 'sticker';
    else if (/se-quotation/.test(cls)) kind = 'quote';
    const ps = [...c.querySelectorAll('p.se-text-paragraph')];
    if (ps.length) {
      ps.forEach((p, i) => {
        const t = clean(p.textContent);
        const span = p.querySelector('span');
        out.push({kind, p: i, empty: t.trim() === '', text: t.slice(0, 30),
                  cls: span ? span.className : ''});
      });
    } else {
      out.push({kind, p: 0, empty: false, text: '', cls: ''});
    }
    if (out.length > 24) break;
  }
  return out;
}
"""


def main() -> int:
    keywords = sys.argv[1:]
    pub = BlogPublisher().start()
    try:
        if not pub.is_logged_in():
            print("[probe] 로그인 세션 없음 — 중단.")
            return 1
        page = pub._page
        pub.open_write_page()
        pub._open_draft_list()
        items = pub._read_draft_items()
        print("[probe] 임시저장 목록:")
        for it in items[:10]:
            print("   ", it.get("idx"), (it.get("title") or "")[:45], it.get("date"))
        k = 0
        if keywords:
            k = next((i for i, it in enumerate(items)
                      if any(kw in (it.get("title") or "") for kw in keywords)), 0)
        buttons = page.query_selector_all(SMART_EDITOR["draft_item_button"])
        if k >= len(buttons):
            print("[probe] 대상 글 없음 — 중단.")
            return 1
        buttons[k].click()
        page.wait_for_timeout(1500)
        conf = page.query_selector(SMART_EDITOR["draft_load_confirm"])
        if conf and conf.is_visible():
            conf.click()
        page.wait_for_timeout(2500)
        print(f"\n===== 글 #{k}: {(items[k].get('title') or '')[:45]} =====")
        raw = page.evaluate(
            "()=>{const t=document.querySelector('.se-component.se-documentTitle');"
            "return t?{html:t.innerHTML.slice(0,600),text:JSON.stringify(t.innerText)}:null;}"
        )
        print("  [TITLE innerText]", raw and raw["text"])
        print("  [TITLE html]", raw and raw["html"])
        for i, row in enumerate(page.evaluate(_DUMP_JS)):
            mark = "  <<< 빈 문단" if row["empty"] else ""
            print(f"  [{i:02d}] {row['kind']:8s} p{row['p']} {row['text']!r}{mark}")
        print("\n[probe] 읽기 전용 종료(저장 안 함).")
        return 0
    finally:
        pub.close(save_session=False)


if __name__ == "__main__":
    raise SystemExit(main())
