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

# 로그인 세션(쿠키)을 저장해 재사용할 디렉터리
SESSION_DIR = REPO_ROOT / "data" / "naver_session"


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

    def __init__(self, blog_id: str, headless: bool = False, session_dir: Path | None = None):
        self.blog_id = blog_id
        self.headless = headless  # 게시는 사람 확인이 필요할 때가 많아 기본 headful
        self.session_dir = session_dir or SESSION_DIR
        self._ctx = None
        self._page = None

    # --- 세션/브라우저 ---
    def start(self):
        """persistent context로 브라우저 기동(쿠키 유지)."""
        from playwright.sync_api import sync_playwright

        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.session_dir),
            headless=self.headless,
            locale="ko-KR",
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def is_logged_in(self) -> bool:
        """현재 세션이 로그인 상태인지 확인."""
        self._page.goto("https://www.naver.com", wait_until="domcontentloaded")
        # TODO: 로그인 상태 판별 셀렉터 확인(내 정보 영역 존재 등)
        return bool(self._page.query_selector("a.MyView-module__link_login"))  # 자리표시자(반대 의미일 수 있음)

    def ensure_login(self):
        """세션이 없으면 로그인. 캡차/2차인증 때문에 최초 1회는 수동 보조가 안전.

        자동 입력은 봇 탐지·캡차 위험이 있어, 기본은 로그인 페이지를 띄우고
        사용자가 직접 로그인하도록 둔 뒤 세션을 저장하는 방식을 권장한다.
        """
        if self.is_logged_in():
            return
        self._page.goto(NAVER_LOGIN["url"], wait_until="domcontentloaded")
        # 권장: 사용자가 직접 로그인 → 세션이 persistent context에 저장됨.
        # (자동 ID/PW 입력은 NAVER_LOGIN 셀렉터로 가능하나 캡차 위험)
        raise EditorNotImplemented(
            "로그인 페이지를 띄웠습니다. 사용자가 직접 로그인 후 진행하세요(세션 저장됨)."
        )

    # --- 게시 ---
    def open_write_page(self):
        url = NAVER_LOGIN["write_url"].format(blog_id=self.blog_id)
        self._page.goto(url, wait_until="domcontentloaded")
        # TODO: 에디터 iframe 로딩 대기

    def publish(self, plan: PublishPlan, *, submit: bool = False):
        """게시 플랜을 에디터에 주입. submit=False면 작성만 하고 발행 직전 멈춘다(안전)."""
        self.open_write_page()
        self._type_title(plan.title)
        for block in plan.blocks:
            if block.kind == "text":
                self._type_text_block(block)
            elif block.kind == "image":
                self._insert_image(block.image_path)
        if submit:
            self._submit()

    # --- 에디터 조작(셀렉터 확정 후 구현) ---
    def _type_title(self, title: str):
        raise EditorNotImplemented("title_area 셀렉터 확인 후 구현")

    def _type_text_block(self, block: PublishBlock):
        """본문 한 블록 입력 후 강조 span에 서식 적용(툴바 클릭, §6.1 A안)."""
        raise EditorNotImplemented("content_area 입력 + 강조 서식 적용 구현 필요")

    def _apply_emphasis(self, text: str, style: EmphasisStyle):
        """본문에서 text를 선택 → 툴바로 글자색/배경/글꼴/크기 적용."""
        raise EditorNotImplemented("텍스트 선택 + 툴바 클릭 매핑 구현 필요")

    def _insert_image(self, path: str | None):
        raise EditorNotImplemented("이미지 업로드(파일 다이얼로그) 구현 필요")

    def _submit(self):
        raise EditorNotImplemented("발행 버튼/확인 레이어 구현 필요")

    def close(self):
        if self._ctx:
            self._ctx.close()
        if getattr(self, "_pw", None):
            self._pw.stop()


# 셀렉터가 비어 있는지 빠른 점검(개발 보조)
def selectors_ready() -> bool:
    required = ("editor_iframe", "title_area", "content_area", "publish_button")
    return all(SMART_EDITOR.get(k) for k in required)
