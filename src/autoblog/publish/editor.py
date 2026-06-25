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
        """진입 시 뜨는 '이전 글 이어쓰기' 팝업이 있으면 취소(새 글)."""
        for sel in (SMART_EDITOR["draft_popup_cancel"], "button:has-text('취소')"):
            try:
                el = self._page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    self._page.wait_for_timeout(500)
                    return
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
        for block in plan.blocks:
            if block.kind == "text":
                self._type_text_block(block)
            elif block.kind == "image" and block.image_path:
                self._insert_image(block.image_path)
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
        """
        self._open_publish_layer()
        self._page.click(SMART_EDITOR["category_button"])
        self._page.wait_for_timeout(1000)
        names = self._page.evaluate("""() => {
            const seen = new Set();
            document.querySelectorAll('label[class*=radio_label]').forEach(el => {
                if (!el.offsetParent) return;
                // '하위 카테고리\\n강남맛집' → 마지막 줄만
                const t = (el.innerText || '').trim().split('\\n').pop().trim();
                if (t) seen.add(t);
            });
            return [...seen];
        }""")
        return names

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

    def _type_text_block(self, block: PublishBlock):
        """본문 한 블록 입력. \\n은 Enter(문단), 블록 끝에 빈 줄 하나."""
        self._page.keyboard.type(block.text, delay=4)
        self._page.keyboard.press("Enter")
        # 강조 서식은 best-effort로 별도 적용(실패해도 본문은 유지)
        for span in block.emphases:
            try:
                self._apply_emphasis(span.text, span.style)
            except Exception:
                pass

    def _apply_emphasis(self, text: str, style: EmphasisStyle):
        """본문에서 text를 선택 → 툴바 글자색/배경 적용.

        색상 팔레트의 커스텀 hex 입력이 필요해 브라우저에서 반복 검증이 필요하다.
        현재는 연동 지점만 두고, 실제 팔레트 조작은 라이브 셋업에서 확정한다.
        """
        raise EditorNotImplemented("색상 팔레트(커스텀 hex) 조작은 라이브 셋업에서 확정")

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
