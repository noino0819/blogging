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

# 네이버 Smart Editor 3.0 (게시 단계, §6) — iframe 기반 contenteditable
# 로그인 후 실제 에디터에서 확인해 채운다(여기 한 곳만 수정). 현재는 자리표시자.
SMART_EDITOR = {
    "editor_iframe": "",  # 에디터 본체 iframe (mainFrame 등)
    "title_area": "",  # 제목 입력 contenteditable
    "content_area": "",  # 본문 contenteditable
    "image_upload_button": "",  # 사진 추가 버튼
    "image_file_input": "",  # 파일 다이얼로그 input[type=file]
    "publish_button": "",  # 발행 버튼
    "publish_confirm": "",  # 발행 확인(레이어) 버튼
    # 서식 툴바 (텍스트 선택 후 클릭)
    "toolbar_text_color": "",  # 글자색 버튼
    "toolbar_bg_color": "",  # 배경색 버튼
    "toolbar_font_family": "",  # 글꼴
    "toolbar_font_size": "",  # 크기
}

# 네이버 로그인
NAVER_LOGIN = {
    "url": "https://nid.naver.com/nidlogin.login",
    "write_url": "https://blog.naver.com/{blog_id}/postwrite",
    "id_input": "#id",
    "pw_input": "#pw",
    "login_button": ".btn_login",
}
