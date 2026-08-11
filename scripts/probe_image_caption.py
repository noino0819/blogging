"""SE-ONE 이미지 '사진 설명(캡션)' 입력 mechanic 프로브. 저장/발행 안 함.

가설: 이미지 컴포넌트를 클릭(객체 선택)하면 이미지 아래에 캡션 영역
('사진 설명을 입력하세요.' placeholder)이 나타나고, 그 영역을 클릭해 타이핑하면
.se-caption 텍스트로 들어간다. 이 프로브가 실제 DOM(클래스·placeholder·클릭 대상)을
캡처하고, 타이핑 결과가 캡션 요소에 실렸는지 검증한다.

흐름: 글쓰기 새로 열기 → 더미 이미지 삽입 → 컴포넌트 DOM 덤프 → 이미지 클릭(선택) →
캡션 영역 탐색·DOM 덤프 → 클릭 → 타이핑 → 캡션 텍스트 실측 → Escape(저장 안 함).

사용:
    .venv/bin/python scripts/probe_image_caption.py [이미지경로] [--headless]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoblog.publish.editor import BlogPublisher  # noqa: E402

_DEFAULT_IMG = str(
    Path(__file__).resolve().parents[1] / "config/editor_previews/quote_quotation_postit.png"
)
_CAPTION = "프로브 캡션 테스트 문구"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    headless = "--headless" in sys.argv
    img = args[0] if args else _DEFAULT_IMG
    if not Path(img).exists():
        print(f"[probe] 이미지 없음: {img}")
        return 2

    pub = BlogPublisher(headless=headless).start()
    try:
        if not pub.is_logged_in():
            print("[probe] 로그인 세션 없음 — 중단(먼저 로그인한 세션이 필요)")
            return 1
        pub.open_write_page()
        page = pub._page
        pub._type_title("캡션 프로브(저장 안 함)")
        pub._insert_image(img)
        page.wait_for_timeout(1500)

        # 1) 삽입 직후 이미지 컴포넌트 DOM 스냅샷(캡션 관련 요소 유무)
        dump = page.evaluate(
            """() => {
              const comp = [...document.querySelectorAll('.se-component')]
                .find(c => c.querySelector('img.se-image-resource'));
              if (!comp) return {found: false};
              const cap = comp.querySelector('.se-caption');
              return {
                found: true,
                compClass: comp.className,
                html: comp.outerHTML.slice(0, 3000),
                capExists: !!cap,
                capClass: cap ? cap.className : null,
                capText: cap ? cap.textContent : null,
              };
            }"""
        )
        print("[probe] 삽입 직후:", {k: v for k, v in dump.items() if k != "html"})

        # 2) 이미지 클릭(객체 선택) → 캡션 영역 변화 관찰
        page.click("img.se-image-resource")
        page.wait_for_timeout(800)
        dump2 = page.evaluate(
            """() => {
              const comp = [...document.querySelectorAll('.se-component')]
                .find(c => c.querySelector('img.se-image-resource'));
              const cap = comp && comp.querySelector('.se-caption');
              return {
                capExists: !!cap,
                capClass: cap ? cap.className : null,
                capHTML: cap ? cap.outerHTML.slice(0, 1500) : null,
                compHTML: comp ? comp.outerHTML.slice(0, 3000) : null,
              };
            }"""
        )
        print("[probe] 이미지 선택 후 캡션:", dump2.get("capClass"), "|", (dump2.get("capHTML") or "")[:300])
        if not dump2.get("capExists"):
            print("[probe] 선택 후에도 .se-caption 없음 — 컴포넌트 HTML:")
            print((dump2.get("compHTML") or "")[:2000])
            return 3

        # 3) 캡션 영역 클릭 → 타이핑 → 실측
        page.click(".se-component .se-caption")
        page.wait_for_timeout(400)
        page.keyboard.type(_CAPTION, delay=30)
        page.wait_for_timeout(600)
        got = page.evaluate(
            """() => {
              const cap = document.querySelector('.se-component .se-caption');
              return cap ? cap.textContent : null;
            }"""
        )
        print(f"[probe] 캡션 실측: {got!r}")
        ok = bool(got) and _CAPTION in got
        print("[probe]", "PASS — 캡션 입력 확인" if ok else "FAIL — 타이핑이 캡션에 안 실림")
        page.keyboard.press("Escape")
        return 0 if ok else 4
    finally:
        pub.close()


if __name__ == "__main__":
    raise SystemExit(main())
