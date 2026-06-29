"""네이버 Smart Editor 3.0 자동 게시 스켈레톤 (기획서 §6).

가장 깨지기 쉬운 부분. 공식 쓰기 API가 없어 Playwright 브라우저 자동화가 필수다.
Smart Editor 3.0은 iframe 기반 커스텀 에디터라 일반 textarea 입력이 불가하고
내부 contenteditable을 직접 조작해야 한다.

⚠️ 이 모듈은 사용자 네이버 로그인이 필요해 개발 환경에서 끝까지 테스트할 수 없다.
   실제 셀렉터(collect.selectors.SMART_EDITOR)는 로그인 후 에디터 구조를 확인해 채운다.
   여기서는 게시 흐름의 골격과 연동 지점을 정의한다.

세션은 쿠키(persistent context)로 유지해 매번 로그인하지 않는다.
"""

from __future__ import annotations

import difflib
import os
import re
import tempfile
from pathlib import Path

from autoblog.collect.selectors import NAVER_LOGIN, SMART_EDITOR
from autoblog.config import REPO_ROOT
from autoblog.publish.emphasis import EmphasisStyle
from autoblog.publish.plan import PublishBlock, PublishPlan

# 로그인 세션을 storage_state(JSON)로 저장해 재사용.
# (persistent context는 세션 쿠키 NID_AUT를 닫을 때 버려 매번 로그인됨 → storage_state로 해결)
STATE_PATH = REPO_ROOT / "data" / "naver_state.json"

# 협찬 고지 사진을 '가장 작게' 표시하기 위한 업로드 폭(px). SE-ONE은 원본보다 키우지 않으므로
# 이 폭으로 줄인 사본을 올리면 본문에서 작게 보인다. 더 작게/크게 하려면 값만 조절.
SPONSOR_PHOTO_WIDTH = 160


def _small_copy(path: str, max_width: int) -> str:
    """이미지를 max_width 이하 폭으로 줄인 임시 사본 경로 반환(원본 미변경).

    이미 그보다 작거나, 열기/저장에 실패하면 원본 경로를 그대로 돌려준다(업로드는 계속됨).
    호출부는 반환 경로가 원본과 다르면 업로드 후 삭제할 책임이 있다.
    """
    try:
        from PIL import Image

        img = Image.open(path)
        if img.width <= max_width:
            return path
        h = max(1, round(img.height * max_width / img.width))
        small = img.convert("RGBA").resize((max_width, h))
        fd, tmp = tempfile.mkstemp(prefix="spon_", suffix=".png")
        os.close(fd)
        small.save(tmp)
        return tmp
    except Exception:
        return path  # 어떤 이유로든 실패하면 원본 그대로 올린다(작게만 못 될 뿐 누락은 없음)

# 본문에서 특정 텍스트의 화면 좌표(Range rect)를 구하는 JS.
# SE는 프로그램적 Range 선택을 색상 적용에 반영하지 않으므로, 좌표를 받아
# 실제 마우스 드래그로 선택해야 SE가 선택을 인식한다.
_RANGE_RECT_JS = """(t) => {
  // 본문 텍스트 컴포넌트를 '전부' 순회한다(첫 컴포넌트만 보면 뒤쪽 문단의
  // 강조 문구를 못 찾아 강조가 통째로 빠진다). 찾은 텍스트는 화면 안으로
  // 스크롤한 뒤 좌표를 재측정한다 — 타이핑 후 스크롤이 끝에 가 있어 위쪽
  // 텍스트가 viewport 밖이면 마우스 드래그 선택이 빗나가기 때문.
  const roots = document.querySelectorAll('.se-component.se-text');
  for (const root of roots) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while (n = w.nextNode()) {
      const tc = n.textContent;
      let i = tc.indexOf(t);
      // 해시태그(#로 시작하는 토큰) 안의 매치는 건너뛴다 — 본문 강조 문구가
      // '#가게명' 같은 해시태그 속 같은 글자에 잘못 입혀지는 충돌을 막는다.
      while (i > 0 && /[#＃]/.test(tc[i - 1])) i = tc.indexOf(t, i + 1);
      if (i !== -1) {
        const r = document.createRange();
        r.setStart(n, i); r.setEnd(n, i + t.length);
        const el = n.parentElement;
        if (el && el.scrollIntoView) el.scrollIntoView({block: 'center'});
        const b = r.getBoundingClientRect();
        return {x: b.x, y: b.y, w: b.width, h: b.height};
      }
    }
  }
  return null;
}"""


class EditorNotImplemented(NotImplementedError):
    """로그인 후 셀렉터 확정 전까지 미구현인 단계."""


class BlogPublisher:
    """Smart Editor 자동 게시 오케스트레이터.

    사용 흐름:
        pub = BlogPublisher(blog_id="myblog")
        pub.start()           # 브라우저(persistent) 기동
        pub.ensure_login()    # 세션 없으면 로그인(최초 1회는 수동 보조)
        pub.publish(plan)     # 게시
        pub.close()
    """

    def __init__(self, blog_id: str | None = None, headless: bool = False, state_path: Path | None = None):
        from autoblog.config import load_env

        self.blog_id = blog_id or load_env().naver_blog_id
        if not self.blog_id:
            raise ValueError("blog_id가 필요합니다(.env NAVER_BLOG_ID 또는 인자로 전달)")
        self.headless = headless  # 게시는 사람 확인이 필요할 때가 많아 기본 headful
        self.state_path = state_path or STATE_PATH
        self._ctx = None
        self._page = None

    # --- 세션/브라우저 ---
    def start(self):
        """브라우저 기동. 저장된 storage_state(JSON)가 있으면 로드해 자동 로그인."""
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless, args=["--disable-blink-features=AutomationControlled"]
        )
        storage = str(self.state_path) if self.state_path.exists() else None
        self._ctx = self._browser.new_context(
            storage_state=storage, locale="ko-KR", viewport={"width": 1440, "height": 900}
        )
        self._page = self._ctx.new_page()
        return self

    def save_state(self):
        """현재 로그인 세션을 storage_state(JSON)로 저장(세션 쿠키 포함 → 다음 실행 자동 로그인)."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._ctx.storage_state(path=str(self.state_path))

    def is_logged_in(self) -> bool:
        """현재 세션이 로그인 상태인지 확인(NID_AUT 쿠키)."""
        return any(c["name"] == "NID_AUT" for c in self._ctx.cookies())

    def wait_for_login(self, timeout_sec: int = 360) -> bool:
        """로그인 페이지를 띄우고 사용자가 직접 로그인할 때까지 대기(세션 없을 때)."""
        import time

        if self.is_logged_in():
            return True
        self._page.goto(NAVER_LOGIN["url"], wait_until="domcontentloaded")
        for _ in range(timeout_sec // 4):
            if self.is_logged_in():
                self.save_state()  # 로그인 즉시 세션 저장
                return True
            time.sleep(4)
        return False

    # --- 게시 ---
    def open_write_page(self):
        url = NAVER_LOGIN["write_url"].format(blog_id=self.blog_id)
        self._page.goto(url, wait_until="domcontentloaded")
        self._page.wait_for_timeout(4000)
        self._dismiss_draft_popup()
        self._page.wait_for_selector(SMART_EDITOR["content_component"], timeout=20000)

    def _dismiss_draft_popup(self):
        """진입 시 뜨는 팝업/오버레이 닫기(이어쓰기 팝업 취소 + 도움말 패널 닫기)."""
        for sel in (
            SMART_EDITOR["draft_popup_cancel"],
            "button:has-text('취소')",
            SMART_EDITOR["help_close"],
        ):
            try:
                el = self._page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    self._page.wait_for_timeout(400)
            except Exception:
                pass

    def publish(
        self, plan: PublishPlan, *, category: str | None = None, save: bool = True, submit: bool = False
    ) -> list[str]:
        """게시 플랜을 에디터에 주입. 기본은 임시저장만, submit=True면 발행까지.

        category가 주어지면 발행 레이어에서 해당 카테고리를 선택한다(유저별 동적).
        자동 삽입에 실패해 본문에서 빠진 항목(예: 검색 결과 없는 지도)이 있으면 사람이
        읽을 수 있는 경고 메시지 목록으로 반환한다(유저가 나중에 직접 보완하도록 안내용)."""
        warnings: list[str] = []
        self.open_write_page()
        self._type_title(plan.title)
        self._page.click(SMART_EDITOR["content_component"])
        self._reset_text_toggles()  # 이전 세션에서 남은 토글 서식(취소선 등) 해제
        emphases = []
        for block in plan.blocks:
            if block.kind == "text":
                self._type_text_block(block)
                emphases.extend(block.emphases)
            elif block.kind == "image" and block.image_path:
                self._insert_image(block.image_path, size=block.image_size)
            elif block.kind == "divider":
                self._insert_divider(block.variant, align=block.align)
            elif block.kind == "quote":
                self._insert_quote(block.text, block.variant, align=block.align)
            elif block.kind == "sticker" and block.sticker_pack is not None:
                self._insert_sticker(block.sticker_pack, block.sticker_index or 0)
            elif block.kind == "place" and block.text:
                try:
                    ok = self._insert_place(block.text, address=block.place_address)
                except Exception as exc:  # noqa: BLE001 - 지도는 보조, 실패해도 본문 유지
                    self._page.keyboard.press("Escape")
                    ok, _ = False, exc
                if not ok:
                    warnings.append(
                        f"지도(장소) 자동 삽입 실패: ‘{block.text}’ — 네이버 장소 검색 결과가 없어 "
                        "건너뛰었어요. 에디터에서 직접 ‘장소’를 추가해 주세요."
                    )
            elif block.kind == "link" and block.link_url:
                self._insert_link(block.link_url)
        # 본문 입력을 모두 마친 뒤 강조 서식 적용(커서 간섭 방지)
        for span in emphases:
            try:
                self._apply_emphasis(span.text, span.style)
            except Exception as exc:  # noqa: BLE001 - 강조는 보조라 실패해도 본문 유지
                self._page.keyboard.press("Escape")
                _ = exc
        if save:
            # 임시저장에도 카테고리가 반영되도록, 발행 레이어에서 카테고리만 고르고 레이어를 닫는다.
            # (submit이면 아래 발행 분기에서 카테고리를 고르므로 중복 적용하지 않는다.)
            if category and not submit:
                self._apply_category_for_draft(category)
            self.save_draft()
        if submit:
            if category:
                self._open_publish_layer()
                self.select_category(category)
            self._submit()
        return warnings

    def _apply_category_for_draft(self, category: str):
        """발행하지 않고 카테고리만 선택해 임시저장에 반영한다.

        발행 레이어를 열어 카테고리를 고른 뒤, Esc로 레이어만 닫는다(발행 X).
        카테고리 적용에 실패해도 본문 임시저장은 그대로 진행한다(보조 기능).
        """
        try:
            self._open_publish_layer()
            self.select_category(category)
            self._page.keyboard.press("Escape")  # 발행하지 않고 레이어만 닫기
            self._page.wait_for_timeout(500)
        except Exception:  # noqa: BLE001 - 카테고리는 보조, 실패해도 저장 진행
            self._page.keyboard.press("Escape")

    def save_draft(self):
        """임시저장."""
        self._page.click(SMART_EDITOR["save_button"])
        self._page.wait_for_timeout(1500)

    # --- 임시저장 글 불러오기(사진 추출) ---
    def _open_draft_list(self):
        """'저장글 N' 버튼을 눌러 임시저장 목록 팝업을 연다(필요 시 글쓰기 페이지부터)."""
        if "postwrite" not in (self._page.url or ""):
            self.open_write_page()
        if not self._page.query_selector(SMART_EDITOR["draft_list"]):
            self._page.click(SMART_EDITOR["save_count_button"])
            self._page.wait_for_selector(SMART_EDITOR["draft_list"], timeout=8000)
            self._page.wait_for_timeout(600)

    def list_drafts(self) -> list[dict]:
        """임시저장 글 목록을 [{idx, title, date}]로 반환."""
        self._open_draft_list()
        return self._page.eval_on_selector_all(
            SMART_EDITOR["draft_list"] + " li",
            """els => els.map((e, i) => ({
                idx: i,
                title: ((e.querySelector('[data-click-area="tpb*s.tlist"] strong') || {}).innerText || '').trim(),
                date: ((e.querySelector('[class*=date]') || {}).innerText || '').trim(),
            }))""",
        )

    def import_draft_photos(self, idx: int, dest_dir: Path) -> list[str]:
        """idx번 임시저장 글을 에디터에 로드해 본문 사진을 dest_dir에 내려받고 로컬 경로 목록을 반환.

        - 본문 사진은 img.se-image-resource(지도 se-map-image는 클래스가 달라 자동 제외).
        - lazy-load라 각 이미지를 화면에 스크롤시켜 실제 CDN URL이 채워질 때까지 폴링한다.
        - 다운로드는 로그인 세션(컨텍스트)으로 수행해 권한 문제를 피한다.
        """
        import uuid

        page = self._page
        self._open_draft_list()
        buttons = page.query_selector_all(SMART_EDITOR["draft_item_button"])
        if idx < 0 or idx >= len(buttons):
            raise ValueError(f"임시저장 인덱스 범위를 벗어남: {idx} (총 {len(buttons)}건)")
        buttons[idx].click()
        page.wait_for_timeout(1500)
        confirm = page.query_selector(SMART_EDITOR["draft_load_confirm"])  # '불러오기' 확인 팝업
        if confirm and confirm.is_visible():
            confirm.click()
        # 사진이 없는 글일 수 있으니 짧게만 기다린다.
        try:
            page.wait_for_selector(SMART_EDITOR["editor_image"], timeout=8000)
        except Exception:
            return []
        page.wait_for_timeout(1000)
        urls = page.evaluate(
            """async () => {
                const imgs = [...document.querySelectorAll('img.se-image-resource')];
                const out = [];
                for (const im of imgs) {
                    im.scrollIntoView({block: 'center'});
                    for (let t = 0; t < 25; t++) {
                        if (im.src && !im.src.startsWith('data:')) break;
                        await new Promise(r => setTimeout(r, 150));
                    }
                    if (im.src && !im.src.startsWith('data:')) out.push(im.src);
                }
                return out;
            }"""
        )
        # 순서 유지 중복 제거
        seen, ordered = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
        # 로그인 컨텍스트로 다운로드
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for u in ordered:
            try:
                resp = self._ctx.request.get(u)
                if resp.status != 200:
                    continue
                ctype = resp.headers.get("content-type", "")
                ext = ".png" if "png" in ctype else ".jpg"
                dest = dest_dir / f"draft_{uuid.uuid4().hex[:8]}{ext}"
                dest.write_bytes(resp.body())
                saved.append(str(dest))
            except Exception:  # noqa: BLE001 - 일부 이미지 실패해도 나머지 진행
                continue
        return saved

    # --- 카테고리 (유저별 동적) ---
    def _open_publish_layer(self):
        self._page.click(SMART_EDITOR["publish_button"])
        self._page.wait_for_timeout(1500)

    def get_categories(self) -> list[str]:
        """현재 유저의 블로그 카테고리 목록을 동적으로 읽는다(발행 레이어).

        하드코딩 없이 계정마다 다른 카테고리를 그대로 가져온다.
        글쓰기 페이지가 아니면 먼저 연다.
        """
        if "postwrite" not in (self._page.url or ""):
            self.open_write_page()
        self._open_publish_layer()
        self._page.click(SMART_EDITOR["category_button"])
        self._page.wait_for_timeout(1000)
        names = self._page.evaluate("""() => {
            const seen = [];
            // 카테고리 셀렉트박스 내부 라벨만(공개설정/발행시점 라디오 제외)
            const scope = document.querySelector('[class*=option_category]') || document;
            scope.querySelectorAll('label[class*=radio_label]').forEach(el => {
                if (!el.offsetParent) return;
                const t = (el.innerText || '').trim().split('\\n').pop().trim();
                if (t && !seen.includes(t)) seen.push(t);
            });
            return seen;
        }""")
        # 네이버 표준 공개설정/발행시점 값은 카테고리가 아니므로 제외
        skip = {"전체공개", "이웃공개", "서로이웃공개", "비공개", "공개", "현재", "예약"}
        return [n for n in names if n not in skip]

    def get_categories_detailed(self) -> list[dict]:
        """카테고리를 이름+뎁스로 읽는다(들여쓰기 padLeft 기준). 중첩 카테고리도 계층 반영.

        반환: [{"name": str, "depth": int}]. depth는 들여쓰기 단계(0=최상위).
        """
        if "postwrite" not in (self._page.url or ""):
            self.open_write_page()
        self._open_publish_layer()
        self._page.click(SMART_EDITOR["category_button"])
        self._page.wait_for_timeout(1000)
        rows = self._page.evaluate("""() => {
            const scope = document.querySelector('[class*=option_category]') || document;
            const out = [];
            scope.querySelectorAll('label[class*=radio_label]').forEach(el => {
                if (!el.offsetParent) return;
                const t = (el.innerText || '').trim().split('\\n').pop().trim();
                const pl = parseFloat(getComputedStyle(el).paddingLeft) || 0;
                if (t) out.push({name: t, pad: pl});
            });
            return out;
        }""")
        skip = {"전체공개", "이웃공개", "서로이웃공개", "비공개", "공개", "현재", "예약"}
        rows = [r for r in rows if r["name"] not in skip]
        if not rows:
            return []
        # 들여쓰기(padLeft)를 뎁스로 환산: 최소 pad=깊이0, 그 위는 최소 양수 차이를 한 단계로
        pads = sorted({r["pad"] for r in rows})
        base = pads[0]
        steps = [b - a for a, b in zip(pads, pads[1:]) if b - a > 0]
        step = min(steps) if steps else 1
        seen, result = set(), []
        for r in rows:
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            result.append({"name": r["name"], "depth": round((r["pad"] - base) / step)})
        return result

    def select_category(self, name: str):
        """카테고리를 이름(텍스트)으로 선택. 레이어/드롭다운이 열려있다고 가정."""
        # 드롭다운이 닫혀 있으면 연다
        try:
            self._page.click(SMART_EDITOR["category_button"], timeout=2000)
            self._page.wait_for_timeout(600)
        except Exception:
            pass
        self._page.get_by_text(name, exact=True).first.click()
        self._page.wait_for_timeout(500)

    # --- 에디터 조작 ---
    def _type_title(self, title: str):
        self._page.click(SMART_EDITOR["title_component"])
        self._page.keyboard.type(title, delay=8)

    def _reset_text_toggles(self):
        """본문 진입 시, 직전 세션에서 켜진 채 남은 토글 서식(취소선/굵게/기울임/밑줄)이
        활성(se-is-selected)이면 한 번 눌러 끈다. 활성이 아니면 건드리지 않는다.

        커서가 본문에 자리잡고 툴바가 실제 상태를 반영할 시간을 준 뒤(대기) 판정한다 —
        포커스 직후엔 직전 상태가 잠깐 남아 오판할 수 있어 충분히 기다린다.
        """
        page = self._page
        page.wait_for_timeout(500)  # 툴바가 현재 커서 서식을 반영하도록 충분히 대기
        page.evaluate("""() => {
          const names = ['se-strikethrough-toolbar-button','se-bold-toolbar-button',
                         'se-italic-toolbar-button','se-underline-toolbar-button'];
          for (const name of names) {
            const b = document.querySelector('button.' + name);
            if (b && /se-is-selected/.test(b.className)) b.click();  // 활성일 때만 끈다
          }
        }""")
        page.wait_for_timeout(300)

    def _type_text_block(self, block: PublishBlock):
        """본문 한 블록 입력. \\n은 Enter(문단), 블록 끝에 빈 줄 하나.

        block.align(center 등)이 있으면 타이핑 전에 현재 단락에 걸어 둔다 — SE는 정렬을
        다음 단락으로 이어받으므로 글 전체가 center면 그대로 유지된다(left로 되돌리지 않음)."""
        if block.align and block.align != "left":
            self._apply_align(block.align)
        self._page.keyboard.type(block.text, delay=4)
        self._page.keyboard.press("Enter")

    def _insert_place(self, query: str, address: str | None = None) -> bool:
        """SE 네이티브 '장소' 카드 삽입: 가게명 검색 → 수집 주소와 가장 잘 맞는 결과 '추가' → '확인'.

        address(수집된 도로명 주소)를 주면 동명 가게가 여럿일 때 주소 유사도로 정확한
        결과를 고른다. 없거나 매칭이 약하면 첫 결과로 폴백. 결과가 아예 없으면 팝업만
        닫고 False(본문 유지). 커서 위치에 지도 카드가 삽입된다."""
        page = self._page
        page.click("button.se-map-toolbar-button")
        page.wait_for_timeout(1500)
        page.fill("input.react-autosuggest__input", query)
        page.wait_for_timeout(400)
        page.click("button.se-place-search-button")
        page.wait_for_timeout(2800)
        items = page.evaluate(
            r"""()=>[...document.querySelectorAll('.se-place-map-search-result-item')].map(it=>({
              title:(it.querySelector('.se-place-map-search-result-title')||{}).textContent||'',
              address:(it.querySelector('.se-place-map-search-result-address')||{}).textContent||'',
            }))"""
        )
        if not items:
            close = page.query_selector("button.se-popup-close-button")
            if close:
                close.click()
            return False
        idx = self._best_place_index(items, query, address)
        # 결과 리스트가 스크롤 영역이라 Playwright 가시성 검사에 안 걸릴 때가 있어 DOM .click()으로.
        page.evaluate(
            "(i)=>{const its=document.querySelectorAll('.se-place-map-search-result-item');"
            "const b=its[i]&&its[i].querySelector('.se-place-add-button');if(b)b.click();}",
            idx,
        )
        page.wait_for_timeout(800)
        page.evaluate(
            "()=>{const b=document.querySelector('button.se-popup-button-confirm');if(b)b.click();}"
        )
        page.wait_for_timeout(1500)
        return True

    def _insert_link(self, url: str) -> bool:
        """SE 링크 카드(oglink) 삽입 — 본문에 URL을 합성 paste 이벤트로 붙여넣어 카드 생성.

        툴바 '링크'(글감검색) 버튼은 외부 URL을 "글감을 가져올 수 없습니다"로 거부하므로 못 쓴다.
        대신 contenteditable에 DataTransfer 기반 paste 이벤트를 디스패치하면(시스템 클립보드 불필요
        → 권한 팝업 없음) 네이버가 OG 메타데이터를 받아 se-oglink 카드를 만든다. 붙여넣기는 URL을
        '일반 텍스트 줄'로도 남기므로, 카드 생성 뒤 그 텍스트 줄을 찾아 삭제한다(SEO상 맨 URL 방지).
        라이브 검증: 쿠팡파트너스 링크 → 'Coupang Partners' 카드 1개, 텍스트 잔여 없음."""
        page = self._page
        page.click(SMART_EDITOR["content_component"])
        page.wait_for_timeout(300)
        page.keyboard.press("End")
        page.keyboard.press("Enter")  # 직전 문단과 안 섞이게 새 줄에서
        page.wait_for_timeout(200)

        before = page.evaluate("()=>document.querySelectorAll('.se-component.se-oglink').length")
        dispatched = page.evaluate(
            """(url)=>{
              const el=(document.activeElement&&document.activeElement.isContentEditable)
                ? document.activeElement : document.querySelector('[contenteditable=true]');
              if(!el) return false;
              el.focus(); const dt=new DataTransfer(); dt.setData('text/plain', url);
              el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
              return true;
            }""",
            url,
        )
        if not dispatched:
            return False
        # OG 카드 변환 대기(최대 ~7초). 첨부 확인 팝업이 뜨면 확인 클릭.
        created = False
        for _ in range(14):
            page.wait_for_timeout(500)
            confirm = page.query_selector("button.se-popup-button-confirm")
            if confirm:
                confirm.click()
                page.wait_for_timeout(600)
            if page.evaluate("()=>document.querySelectorAll('.se-component.se-oglink').length") > before:
                created = True
                break
        if not created:
            return False
        # 붙여넣기가 남긴 '일반 URL 텍스트 줄' 제거(트리플클릭으로 줄 선택 → 삭제)
        box = page.evaluate(
            """(url)=>{
              const t=[...document.querySelectorAll('.se-component.se-text')]
                .find(c=>(c.textContent||'').trim()===url);
              if(!t) return null; const r=t.getBoundingClientRect();
              return {x:r.x+r.width/2, y:r.y+r.height/2};
            }""",
            url,
        )
        if box:
            page.mouse.click(box["x"], box["y"], click_count=3)
            page.wait_for_timeout(200)
            page.keyboard.press("Delete")
            page.wait_for_timeout(150)
            page.keyboard.press("Backspace")  # 남은 빈 줄 제거
            page.wait_for_timeout(300)
        return True

    # 시/도 풀네임 → 약칭(수집 주소는 '서울', SE 결과는 '서울특별시'라 통일)
    _SIDO = {
        "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
        "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
        "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
        "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
        "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
    }

    @classmethod
    def _norm_addr(cls, s: str) -> str:
        s = s or ""
        for long, short in cls._SIDO.items():
            s = s.replace(long, short)
        return re.sub(r"\s+", "", s)

    @classmethod
    def _best_place_index(cls, items: list[dict], name: str, address: str | None) -> int:
        """검색 결과 중 수집한 이름·주소와 가장 잘 맞는 항목의 인덱스(약하면 0)."""
        a1 = cls._norm_addr(address) if address else ""
        best_i, best_score = 0, -1.0
        for i, it in enumerate(items):
            ns = difflib.SequenceMatcher(None, name or "", it.get("title", "")).ratio()
            a2 = cls._norm_addr(it.get("address", ""))
            if a1 and a2:
                asc = difflib.SequenceMatcher(None, a1, a2).ratio()
                if a1 in a2 or a2 in a1:  # 한쪽이 다른 쪽을 포함하면 강한 일치
                    asc = max(asc, 0.95)
            else:
                asc = 0.0
            score = 0.55 * asc + 0.45 * ns if a1 else ns
            if score > best_score:
                best_i, best_score = i, score
        # 주소 힌트가 있는데도 매칭이 약하면(동명 다수·오검색 의심) 그래도 최고점을 쓰되,
        # 첫 결과가 더 그럴듯하면 첫 결과. 임계 미만이면 0으로 폴백.
        return best_i if best_score >= 0.5 else 0

    def _apply_align(self, value: str):
        """현재 단락 정렬(left/center/right/justify). 선택 없이 커서 위치 단락에 적용."""
        page = self._page
        page.evaluate("()=>{const b=document.querySelector('li.se-toolbar-item-align button');if(b)b.click();}")
        page.wait_for_timeout(300)
        page.evaluate(
            "(v)=>{const o=document.querySelector("
            "'button[data-name=\"align-drop-down-with-justify\"][data-value=\"'+v+'\"]');if(o)o.click();}",
            value,
        )
        page.wait_for_timeout(250)

    def _apply_emphasis(self, text: str, style: EmphasisStyle):
        """본문에서 text를 선택 → 글자색/배경색을 커스텀 hex로 정확히 적용.

        '더보기 → hex 입력 → 확인'은 SE 네이티브 명령이라 내부 모델을 갱신 →
        커스텀 색이 저장까지 유지된다(검증됨).
        """
        if not (style.text_color or style.background_color or style.font_family or style.font_size):
            return
        if not self._select_body_text(text):  # 한 번만 선택(SE가 적용 후 선택 유지)
            return
        if style.text_color:
            self._apply_color(SMART_EDITOR["toolbar_text_color"], style.text_color)
        if style.background_color:
            self._apply_color(SMART_EDITOR["toolbar_bg_color"], style.background_color)
        if style.font_family:
            self._apply_font(style.font_family)
        if style.font_size:
            self._apply_font_size(style.font_size)

    def _apply_font(self, font_value: str):
        """선택 텍스트에 서체 적용(프리셋 fontFamily). 드롭다운 열고 data-value 옵션 클릭."""
        page = self._page
        page.evaluate("()=>{const b=document.querySelector('li.se-toolbar-item-font-family button');if(b)b.click();}")
        page.wait_for_timeout(400)
        page.evaluate(
            "(v)=>{const o=[...document.querySelectorAll('button[data-name=\"font-family\"][data-role=\"option\"]')]"
            ".find(e=>e.getAttribute('data-value')===v);if(o)o.click();}",
            font_value,
        )
        page.wait_for_timeout(300)

    def _apply_font_size(self, size):
        """선택 텍스트에 글자 크기 적용(프리셋 fontSize → data-value 'fs<N>')."""
        page = self._page
        page.evaluate("()=>{const b=document.querySelector('li.se-toolbar-item-font-size-code button');if(b)b.click();}")
        page.wait_for_timeout(400)
        page.evaluate(
            "(v)=>{const o=[...document.querySelectorAll('button[data-name=\"font-size\"][data-role=\"option\"]')]"
            ".find(e=>e.getAttribute('data-value')===v);if(o)o.click();}",
            f"fs{size}",
        )
        page.wait_for_timeout(300)

    def _select_body_text(self, text: str) -> bool:
        """본문에서 text를 실제 마우스 드래그로 선택(SE가 선택을 인식하도록)."""
        rect = self._page.evaluate(_RANGE_RECT_JS, text)
        if not rect or rect["w"] < 1:
            return False
        page = self._page
        y = rect["y"] + rect["h"] / 2
        page.mouse.move(rect["x"] + 1, y)
        page.mouse.down()
        page.mouse.move(rect["x"] + rect["w"] - 1, y, steps=6)
        page.mouse.up()
        page.wait_for_timeout(200)
        return True

    def _apply_color(self, toolbar_button: str, hex_color: str):
        """글자색/배경색 버튼 → 더보기 → hex 입력 → 확인 (네이티브, 저장 유지)."""
        page = self._page
        page.click(toolbar_button)
        page.wait_for_timeout(350)
        page.click(SMART_EDITOR["color_more_button"])
        page.wait_for_timeout(350)
        inp = page.query_selector(SMART_EDITOR["color_hex_input"])
        inp.click()
        inp.fill(hex_color.lstrip("#"))
        page.wait_for_timeout(200)
        page.click(SMART_EDITOR["color_apply_button"])
        page.wait_for_timeout(350)

    def _insert_divider(self, variant: int = 1, align: str | None = None):
        """구분선 삽입. 항상 종류 드롭다운에서 variant번째를 고른다(variant=1=기본선).

        기본 빠른버튼(...-default-toolbar-button)을 쓰지 않는 이유: 드롭다운으로 한 번
        다른 종류를 고르면 SE-ONE이 그 종류를 기억해 빠른버튼 클래스가 바뀌어 사라진다.
        그래서 변형>1 다음 변형1을 넣을 때 기본 버튼을 못 찾는다 → 경로를 드롭다운으로 통일."""
        self._pick_insert_variant("horizontal-line", max(variant, 1))
        self._page.wait_for_timeout(500)
        if align and align != "left":
            self._apply_align(align)

    def _insert_quote(self, text: str, variant: int = 1, align: str | None = None):
        """인용구 삽입 후 본문 텍스트 입력. 구분선과 같은 이유로 드롭다운 경로로 통일.

        text의 \\n은 인용구 안에서 줄바꿈(Enter)으로 넣어 한마디를 여러 줄로 보여준다."""
        self._pick_insert_variant("quotation", max(variant, 1))
        self._page.wait_for_timeout(500)
        for i, line in enumerate(text.split("\n")):
            if i:
                self._page.keyboard.press("Enter")
            self._page.keyboard.type(line, delay=4)
        self._page.wait_for_timeout(200)
        if align and align != "left":
            self._apply_align(align)  # 내용 입력 후(커서가 인용구 안에 있을 때) 정렬 적용
        # 인용 블록 탈출: '본문 추가'로 블록 뒤에 새 문단을 만들고 거기로 포커스
        try:
            self._page.click(SMART_EDITOR["canvas_bottom_button"])
            self._page.wait_for_timeout(300)
        except Exception:
            self._page.keyboard.press("ArrowDown")

    def _pick_insert_variant(self, name: str, n: int):
        """삽입 종류 드롭다운 열고 N번째 옵션 클릭(구분선/인용구 종류 선택)."""
        page = self._page
        item = (
            "li.se-toolbar-item-insert-horizontal-line"
            if name == "horizontal-line"
            else "li.se-toolbar-item-insert-quotation"
        )
        page.evaluate(
            "(sel)=>{const b=document.querySelector(sel+' button.se-document-toolbar-select-option-button');if(b)b.click();}",
            item,
        )
        page.wait_for_timeout(500)
        page.evaluate(
            """(args)=>{const {name,n}=args;
              const opts=[...document.querySelectorAll('button[data-name='+JSON.stringify(name)+'][data-role=\\"option\\"]')].filter(e=>e.offsetParent);
              if(opts[n-1]) opts[n-1].click();}""",
            {"name": name, "n": n},
        )
        page.wait_for_timeout(500)

    # --- 스티커 ---
    def _open_sticker_panel(self):
        """스티커 사이드바 패널을 연다(이미 열려있으면 그대로)."""
        panel = self._page.query_selector(SMART_EDITOR["sticker_panel"])
        if panel and panel.is_visible():
            return
        self._page.click(SMART_EDITOR["sticker_button"])
        self._page.wait_for_selector(SMART_EDITOR["sticker_panel"], timeout=8000)
        self._page.wait_for_timeout(800)

    def _select_sticker_pack(self, pack: str):
        """팩 코드(ogq_xxx/clip_xxx)가 썸네일 URL에 든 탭을 클릭해 그 팩을 활성화."""
        ok = self._page.evaluate(
            """(code)=>{
              const tabs=[...document.querySelectorAll('ul.se-panel-tab-list li.se-tab-item button.se-tab-button')];
              const t=tabs.find(b=>((b.getAttribute('style')||'')+ (b.querySelector('*')?.getAttribute?.('style')||'')).includes(code));
              if(t){t.click();return true;} return false;
            }""",
            pack,
        )
        self._page.wait_for_timeout(700)
        return ok

    def _insert_sticker(self, pack: str, index: int):
        """(팩, 인덱스) 스티커를 본문 커서 위치에 삽입(검증된 메커니즘).

        패널 열기 → 팩 탭 선택 → 활성 목록에서 data-index 클릭 → 본문 끝으로 포커스 복귀.
        """
        self._open_sticker_panel()
        self._select_sticker_pack(pack)
        sel = f"{SMART_EDITOR['sticker_active_list']} {SMART_EDITOR['sticker_element']}[data-index='{index}']"
        try:
            self._page.click(sel, timeout=4000)
        except Exception:
            return  # 해당 스티커가 없으면(팩 변경 등) 조용히 건너뜀
        self._page.wait_for_timeout(700)
        # 다음 본문 입력을 위해 본문 끝으로 포커스 복귀
        try:
            self._page.click(SMART_EDITOR["canvas_bottom_button"])
            self._page.wait_for_timeout(200)
        except Exception:
            pass

    def pull_stickers(self, out_dir: Path | None = None) -> list:
        """현재 계정의 스티커를 전부 훑어 개별 고해상도 PNG로 저장하고 Sticker 목록 반환(라이브).

        에디터에서 보유 팩(코드·인덱스·애니여부)만 열거하고, 이미지는 **CDN 개별 원본**을
        직접 받는다(에디터 스프라이트는 ~80px로 깨짐). CDN 실패 팩(clip/moti 등 다른 스킴)은
        그 자리에서 element 스크린샷으로 폴백. 팩 코드는 스티커 span URL에서 추출.
        """
        from autoblog.publish.stickers import (
            STICKER_DATA_DIR,
            Sticker,
            crop_sprite,
            download_sprite,
            download_sticker_image,
        )

        out_dir = out_dir or STICKER_DATA_DIR
        page = self._page
        self.open_write_page()
        page.click(SMART_EDITOR["content_component"])
        self._open_sticker_panel()
        tabs = page.query_selector_all(SMART_EDITOR["sticker_tab_button"])
        results: list = []
        for tab in tabs:
            if "history" in (tab.get_attribute("class") or ""):
                continue  # 최근사용 탭은 건너뜀(중복)
            try:
                tab.click()
                page.wait_for_timeout(700)
            except Exception:
                continue
            meta = page.evaluate(
                """() => {
                  const ul=document.querySelector('ul.se-sidebar-list.se-is-on');
                  if(!ul) return {pack:null, items:[]};
                  const btns=[...ul.querySelectorAll('button.se-sidebar-element-sticker')];
                  const span=btns[0]?.querySelector('.se-sidebar-sticker');
                  const bg=span?getComputedStyle(span).backgroundImage:'';
                  const m=bg.match(/pstatic\\.net\\/([^/]+)\\//);
                  // cols = 서로 다른 background-position-x 개수(스프라이트 격자 열 수)
                  const xs=new Set(btns.map(b=>{const s=b.querySelector('.se-sidebar-sticker');
                    return s?getComputedStyle(s).backgroundPositionX:'';}));
                  return {pack: m?m[1]:null, cols: xs.size||3,
                          items: btns.map(b=>({idx:+b.getAttribute('data-index'),
                                               animated:b.getAttribute('data-animated')==='true'}))};
                }"""
            )
            pack = meta.get("pack")
            if not pack:
                continue
            pack_dir = out_dir / pack
            btns = page.query_selector_all(
                f"{SMART_EDITOR['sticker_active_list']} {SMART_EDITOR['sticker_element']}"
            )
            btn_by_idx = {it["idx"]: b for b, it in zip(btns, meta["items"])}
            cols = meta.get("cols") or 3
            count = len(meta["items"])
            sprite: bytes | None | bool = False  # False=미시도, None=없음, bytes=받음
            for item in meta["items"]:
                idx = item["idx"]
                img_path = pack_dir / f"{idx}.png"
                # 1순위: CDN 개별 고해상도(ogq/clip/일부 cafe). 실패 시 스프라이트 크롭, 그래도 안 되면 스크린샷.
                if download_sticker_image(pack, idx, img_path):
                    pass
                else:
                    if sprite is False:  # 이 팩에서 처음 폴백 — 스프라이트 1회 받기
                        sprite = download_sprite(pack)
                    if sprite:
                        pack_dir.mkdir(parents=True, exist_ok=True)
                        img_path.write_bytes(crop_sprite(sprite, cols, count, idx))
                    else:  # 최후: 에디터 버튼 스크린샷(저화질)
                        b = btn_by_idx.get(idx)
                        if b is None:
                            continue
                        try:
                            b.evaluate("e => e.scrollIntoView({block: 'center'})")
                            page.wait_for_timeout(60)
                            box = b.bounding_box()
                            if not box or box["width"] < 1:
                                continue
                            pack_dir.mkdir(parents=True, exist_ok=True)
                            page.screenshot(path=str(img_path), animations="disabled", clip=box)
                        except Exception:
                            continue
                rel = (
                    str(img_path.relative_to(REPO_ROOT))
                    if img_path.is_relative_to(REPO_ROOT)
                    else str(img_path)
                )
                results.append(Sticker(pack=pack, index=idx, animated=item["animated"], image=rel))
        return results

    def _insert_image(self, path: str, size: str | None = None):
        """이미지 툴바 버튼 → 파일 다이얼로그로 업로드.

        size="small"이면(협찬 고지 사진 등) 업로드 전에 작은 폭으로 줄인 임시 사본을 올린다.
        SE-ONE은 원본보다 큰 폭으로 확대하지 않아, 작은 원본은 본문에서 작게 표시된다.
        """
        upload = _small_copy(path, SPONSOR_PHOTO_WIDTH) if size == "small" else path
        with self._page.expect_file_chooser() as fc_info:
            self._page.click(SMART_EDITOR["image_upload_button"])
        fc_info.value.set_files(upload)
        self._page.wait_for_timeout(2500)  # 업로드 대기
        if upload != path:
            try:
                os.remove(upload)  # 업로드를 마쳤으니 임시 사본 정리
            except OSError:
                pass

    def _submit(self):
        self._page.click(SMART_EDITOR["publish_button"])
        self._page.wait_for_timeout(1500)
        try:
            self._page.click(SMART_EDITOR["publish_confirm"], timeout=5000)
        except Exception:
            pass  # 발행 레이어 확인 버튼은 라이브에서 확정

    def close(self, save_session: bool = True):
        if self._ctx:
            if save_session and self.is_logged_in():
                try:
                    self.save_state()  # 세션 영속화(다음 실행 자동 로그인)
                except Exception:
                    pass
            self._ctx.close()
        if getattr(self, "_browser", None):
            self._browser.close()
        if getattr(self, "_pw", None):
            self._pw.stop()


# 핵심 셀렉터가 채워졌는지 점검(개발 보조). editor_iframe은 top frame이라 비워둠.
def selectors_ready() -> bool:
    required = ("title_component", "content_component", "save_button", "publish_button")
    return all(SMART_EDITOR.get(k) for k in required)
