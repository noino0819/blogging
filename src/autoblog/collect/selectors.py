"""스크래핑 셀렉터 집결지 (기획서 §3.1).

네이버 구조 변경 시 '여기 한 곳'만 수정하면 되도록 모든 CSS/XPath 셀렉터를 모은다.
값은 실제 페이지 구조 확인 후 채운다 — 현재는 자리표시자.
"""

from __future__ import annotations

# 네이버 플레이스 (m.place.naver.com) — iframe·동적 로딩 주의
PLACE = {
    # 영업시간·메뉴·가격·평점은 검색 API로 안 나와 스크래핑 필요
    "name": "",
    "category": "",
    "address": "",
    "business_hours": "",
    "rating": "",
    "menu_item": "",  # 반복 요소
    "menu_name": "",
    "menu_price": "",
}

# 상품 페이지 (쿠팡·스마트스토어 등) — 텍스트형/이미지형 판별에 사용
PRODUCT = {
    "title": "",
    "price": "",
    "detail_container": "",  # 상세설명 영역
    "detail_images": "",  # 이미지형일 때 다운로드 대상 <img>
}

# 네이버 Smart Editor 3.0 (게시 단계, §6) — iframe 기반 contenteditable
SMART_EDITOR = {
    "iframe": "",
    "title_area": "",
    "content_area": "",
    "image_upload_button": "",
    "publish_button": "",
}
