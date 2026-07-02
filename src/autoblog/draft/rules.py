"""공통 규칙 — 토글로 on/off 하는 프롬프트 조각 (기획서 §4.3).

토글 상태에 따라 해당 규칙 텍스트를 시스템 프롬프트에 추가/제거(프롬프트 조립).
설정은 프리셋으로 저장할 수 있다("체험단용", "일상 블로그용" 등).
"""

from __future__ import annotations

from pydantic import BaseModel

# '경험이 주연, 사실이 조연 + 지어내기 금지' 원칙은 build_user_prompt(prompt.py)의
# 재료 머리말('나의 경험'/'참고 정보')과 금지 지시로 전달된다 — 여기 중복 정의하지 않는다.

# 규칙 키 → 프롬프트 조각
_FRAGMENTS = {
    "mobile_friendly": (
        "모바일 친화: 문단을 2~3줄로 짧게 끊고 여백을 넉넉히 두세요. "
        "네이버 트래픽 대부분이 모바일입니다."
    ),
    "authenticity": (
        "진정성: '강력 추천!', '인생 맛집' 같은 과장·상투구와 AI식 표현을 피하고, "
        "솔직하고 담백하게 쓰세요. 단점이나 아쉬운 점도 자연스럽게 담을 수 있습니다."
    ),
    "structure_guide": (
        "구조: 방문/구매 동기 → 경험 → 평가 흐름으로 전개하고, "
        "소제목으로 구간을 나누세요."
    ),
    "seo": (
        "검색 노출: 제목의 대표 검색 키워드를 인트로 첫 문단에 1회 자연스럽게 포함하고, "
        "소제목 한두 개와 본문에도 몇 차례 자연스럽게 등장시키세요(제목에만 있고 본문에 "
        "없으면 제목-본문 불일치로 불리합니다). 지역명·업종/상품명 같은 연관 키워드도 "
        "1~2회 곁들이세요. 단 같은 키워드를 문장마다 반복(키워드 스터핑)하면 저품질로 "
        "보이니 절대 금지."
    ),
    "emoji": "이모티콘: 분위기에 맞는 이모지를 적절히 사용하세요.",
}

# 기본값: 검색 노출이 프로젝트 목표라 seo 포함 4개 켜짐, emoji만 꺼짐
_DEFAULT_ON = {"mobile_friendly", "authenticity", "structure_guide", "seo"}


class CommonRules(BaseModel):
    """공통 규칙 토글."""

    mobile_friendly: bool = True
    authenticity: bool = True
    structure_guide: bool = True
    seo: bool = True
    emoji: bool = False

    def active_fragments(self) -> list[str]:
        """켜진 규칙의 프롬프트 조각 목록."""
        return [_FRAGMENTS[key] for key in _FRAGMENTS if getattr(self, key, False)]
