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

from pathlib import Path

from autoblog.collect.selectors import NAVER_LOGIN, SMART_EDITOR
from autoblog.config import REPO_ROOT
from autoblog.publish.emphasis import EmphasisStyle
from autoblog.publish.plan import PublishBlock, PublishPlan

# 로그인 세션을 storage_state(JSON)로 저장해 재사용.
# (persistent context는 세션 쿠키 NID_AUT를 닫을 때 버려 매번 로그인됨 → storage_state로 해결)
STATE_PATH = REPO_ROOT / "data" / "naver_state.json"

# 본문에서 특정 텍스트의 화면 좌표(Range rect)를 구하는 JS.
# SE는 프로그램적 Range 선택을 색상 적용에 반영하지 않으므로, 좌표를 받아
# 실제 마우스 드래그로 선택해야 SE가 선택을 인식한다.
_RANGE_RECT_JS = """(t) => {
  const root = document.querySelector('.se-component.se-text');
  if (!root) return null;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n;
  while (n = w.nextNode()) {
    const i = n.textContent.indexOf(t);
    if (i !== -1) {
      const r = document.createRange();
      r.setStart(n, i); r.setEnd(n, i + t.length);
      const b = r.getBoundingClientRect();
      return {x: b.x, y: b.y, w: b.width, h: b.height};
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
    ):
        """게시 플랜을 에디터에 주입. 기본은 임시저장만, submit=True면 발행까지.

        category가 주어지면 발행 레이어에서 해당 카테고리를 선택한다(유저별 동적).
        """
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
                self._insert_image(block.image_path)
            elif block.kind == "divider":
                self._insert_divider(block.variant)
            elif block.kind == "quote":
                self._insert_quote(block.text, block.variant)
            elif block.kind == "sticker" and block.sticker_pack is not None:
                self._insert_sticker(block.sticker_pack, block.sticker_index or 0)
        # 본문 입력을 모두 마친 뒤 강조 서식 적용(커서 간섭 방지)
        for span in emphases:
            try:
                self._apply_emphasis(span.text, span.style)
            except Exception as exc:  # noqa: BLE001 - 강조는 보조라 실패해도 본문 유지
                self._page.keyboard.press("Escape")
                _ = exc
        if save:
            self.save_draft()
        if submit:
            if category:
                self._open_publish_layer()
                self.select_category(category)
            self._submit()

    def save_draft(self):
        """임시저장."""
        self._page.click(SMART_EDITOR["save_button"])
        self._page.wait_for_timeout(1500)

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
        """남아있는 토글 서식(취소선/굵게/기울임/밑줄, se-is-selected)을 해제.

        SE는 마지막 서식 상태를 유지해, 직전에 켜진 취소선 등이 새 글에 묻어난다.
        커서가 본문에 자리잡은 뒤(대기) 활성 토글을 JS로 끈다.
        """
        self._page.wait_for_timeout(300)
        self._page.evaluate("""() => {
          const names = ['se-strikethrough-toolbar-button','se-bold-toolbar-button',
                         'se-italic-toolbar-button','se-underline-toolbar-button'];
          for (const name of names) {
            const b = document.querySelector('button.' + name);
            if (b && /se-is-selected/.test(b.className)) b.click();
          }
        }""")
        self._page.wait_for_timeout(300)

    def _type_text_block(self, block: PublishBlock):
        """본문 한 블록 입력. \\n은 Enter(문단), 블록 끝에 빈 줄 하나."""
        self._page.keyboard.type(block.text, delay=4)
        self._page.keyboard.press("Enter")

    def _apply_emphasis(self, text: str, style: EmphasisStyle):
        """본문에서 text를 선택 → 글자색/배경색을 커스텀 hex로 정확히 적용.

        '더보기 → hex 입력 → 확인'은 SE 네이티브 명령이라 내부 모델을 갱신 →
        커스텀 색이 저장까지 유지된다(검증됨).
        """
        if not (style.text_color or style.background_color):
            return
        if not self._select_body_text(text):  # 한 번만 선택(SE가 적용 후 선택 유지)
            return
        if style.text_color:
            self._apply_color(SMART_EDITOR["toolbar_text_color"], style.text_color)
        if style.background_color:
            self._apply_color(SMART_EDITOR["toolbar_bg_color"], style.background_color)

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

    def _insert_divider(self, variant: int = 1):
        """구분선 삽입. variant>1이면 종류 선택 드롭다운에서 N번째 선택."""
        if variant and variant > 1:
            self._pick_insert_variant("horizontal-line", variant)
        else:
            self._page.click(SMART_EDITOR["divider_button"])
        self._page.wait_for_timeout(500)

    def _insert_quote(self, text: str, variant: int = 1):
        """인용구 삽입 후 본문 텍스트 입력. variant>1이면 종류 선택."""
        if variant and variant > 1:
            self._pick_insert_variant("quotation", variant)
        else:
            self._page.click(SMART_EDITOR["quote_button"])
        self._page.wait_for_timeout(500)
        self._page.keyboard.type(text, delay=4)
        self._page.wait_for_timeout(200)
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
                  return {pack: m?m[1]:null,
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
            for item in meta["items"]:
                idx = item["idx"]
                img_path = pack_dir / f"{idx}.png"
                # 1순위: CDN 개별 고해상도. 실패 시 에디터 버튼 스크린샷 폴백.
                if not download_sticker_image(pack, idx, img_path):
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

    def _insert_image(self, path: str):
        """이미지 툴바 버튼 → 파일 다이얼로그로 업로드."""
        with self._page.expect_file_chooser() as fc_info:
            self._page.click(SMART_EDITOR["image_upload_button"])
        fc_info.value.set_files(path)
        self._page.wait_for_timeout(2500)  # 업로드 대기

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
