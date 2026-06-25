"""스크래핑 셀렉터 집결지 (기획서 §3.1).

네이버 구조 변경 시 '여기 한 곳'만 수정하면 되도록 모든 CSS/XPath 셀렉터를 모은다.
값은 실제 페이지 구조 확인 후 채운다 — 현재는 자리표시자.
"""

from __future__ import annotations

# 네이버 플레이스 (m.place.naver.com)
# 주의: 상세 데이터(메뉴/가격/평점/좌표)는 CSS 셀렉터로 긁지 않고
# 페이지에 SSR된 window.__APOLLO_STATE__ JSON을 파싱한다(place_detail.py).
# 클래스명 변경에 덜 깨지므로 이쪽이 기본. CSS 셀렉터는 필요 시에만 추가.
PLACE: dict[str, str] = {}

# 상품 페이지 (쿠팡·스마트스토어 등) — 텍스트형/이미지형 판별에 사용
PRODUCT = {
    "title": "",
    "price": "",
    "detail_container": "",  # 상세설명 영역
    "detail_images": "",  # 이미지형일 때 다운로드 대상 <img>
}

# 네이버 Smart Editor ONE (게시 단계, §6).
# 확인 결과: 에디터는 별도 iframe이 아니라 글쓰기 페이지(top frame)에 직접 렌더된다.
# se-* 클래스는 안정적, 발행 버튼은 data-click-area 속성으로 잡는다(해시 클래스 회피).
SMART_EDITOR = {
    "editor_iframe": "",  # 없음(top frame). 비워두면 page에서 바로 조작.
    "title_area": ".se-documentTitle .se-text-paragraph",  # 제목 입력 영역
    "title_component": ".se-component.se-documentTitle",
    "content_area": ".se-component.se-text .se-text-paragraph",  # 본문 입력 영역
    "content_component": ".se-component.se-text",
    "image_upload_button": ".se-toolbar-item-image button",  # 사진 추가 버튼
    "image_file_input": "input[type=file]",  # 파일 input
    "publish_button": 'button[data-click-area="tpb.publish"]',  # 발행(설정 레이어 열기)
    "publish_confirm": '.layer_btn_area button[class*=confirm], button[data-click-area="tpb*v.publish"]',
    # 서식 툴바 (텍스트 선택 후 나타남)
    "toolbar_text_color": "li.se-toolbar-item-text-color button",
    "toolbar_bg_color": "li.se-toolbar-item-background-color button",
    # 글쓰기 진입 시 뜨는 '이전 글 이어쓰기' 팝업 닫기(취소)
    "draft_popup_cancel": ".se-popup-button-cancel",
}

# 네이버 로그인
NAVER_LOGIN = {
    "url": "https://nid.naver.com/nidlogin.login",
    "write_url": "https://blog.naver.com/{blog_id}/postwrite",
    "id_input": "#id",
    "pw_input": "#pw",
    "login_button": ".btn_login",
}
