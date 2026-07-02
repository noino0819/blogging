"""기본 베이스 프롬프트 로딩 (사용자 편집 가능).

config/prompts/default.md(맛집)·product.md(상품)를 시스템 프롬프트의 베이스로 쓰고,
두 유형이 공유하는 문체 규칙(config/prompts/common_style.md)을 그 뒤에 이어 붙인다
(복붙 중복으로 두 파일이 어긋나던 것을 단일 출처로 통합).
파일 상단의 메타 안내(제목 + 인용 블록, 첫 '---' 이전)는 모델에 보내지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from autoblog.config import CONFIG_DIR

DEFAULT_PROMPT_PATH = CONFIG_DIR / "prompts" / "default.md"
PRODUCT_PROMPT_PATH = CONFIG_DIR / "prompts" / "product.md"
COMMON_STYLE_PROMPT_PATH = CONFIG_DIR / "prompts" / "common_style.md"


def _strip_meta(text: str) -> str:
    """파일 상단 메타 안내(제목 + 인용 블록, 첫 '---' 이전) 제거."""
    marker = "\n---\n"
    idx = text.find(marker)
    if idx != -1:
        text = text[idx + len(marker) :]
    return text.strip()


def load_base_prompt(path: str | Path | None = None, *, card=None) -> str:
    """베이스 프롬프트 텍스트 로드(상단 메타 안내 제거 + 공통 문체 규칙 연결).

    path를 명시하지 않고 card가 상품 카드면 product.md를 쓴다. 선택 기준은
    '카드 타입(상품)'이야 — 스마트스토어 WTM 차단으로 product 데이터를 못 긁어도
    유저가 '상품'으로 고른 카드면 상품 프롬프트가 걸려야 하니까(card.product 유무로
    판단하면 차단된 글은 영영 맛집 프롬프트로 떨어진다). 데이터만 있고 타입이 없어도
    상품으로 인정. product.md가 없으면 default.md로 폴백한다(맛집·상품 공용).
    """
    if path is None and card is not None and PRODUCT_PROMPT_PATH.exists():
        from autoblog.collect.fact_card import CardType

        is_product = (
            getattr(card, "type", None) == CardType.product
            or getattr(card, "product", None) is not None
        )
        if is_product:
            path = PRODUCT_PROMPT_PATH
    text = _strip_meta(Path(path or DEFAULT_PROMPT_PATH).read_text(encoding="utf-8"))
    if COMMON_STYLE_PROMPT_PATH.exists():  # 공통 문체 규칙(맛집·상품 공용, 단일 출처)
        common = _strip_meta(COMMON_STYLE_PROMPT_PATH.read_text(encoding="utf-8"))
        if common:
            text = f"{text}\n\n{common}"
    return text


# 맛집·상품 공통 자가 점검 — 시스템 프롬프트 맨 끝에 항상 붙인다(단일 출처).
# 가장 자주 어기는 기계적 규칙만 짧게 추렸다. 외부 챗봇에 붙여넣어 쓰는 경로는
# enforce_format 후처리를 안 거치므로, 모델이 스스로 점검·수정하게 만드는 게 핵심.
# 나열 박스 예외는 상품 리뷰에만 있는 개념이라 is_product일 때만 언급한다
# (맛집 글에 예외를 언급하면 허용되는 것으로 오독할 수 있음).


def build_selfcheck_instruction(is_product: bool = False) -> str:
    """자가 점검 지시문(시스템 프롬프트 맨 끝에 붙이는 블록).

    is_product=True(상품 리뷰)면 나열 박스(1️⃣~·✅) 예외 문구를 함께 넣는다.
    """
    box_note = " (요약 박스 1️⃣~·추천 체크리스트 ✅ 한 줄은 예외)" if is_product else ""
    bullet_note = " (요약 박스·추천 체크리스트만 예외)" if is_product else ""
    return f"""## 제출 전 자가 점검 (반드시 마지막에 수행)

글을 다 썼으면 제출하기 전에 아래를 한 항목씩 직접 검사하고, 어긴 곳이 있으면 그 자리에서 고친 뒤 최종본만 내보내. 이 점검을 생략하지 마.

1. 줄 길이 — 본문에 30자를 넘는 줄이 하나도 없는가? 넘으면 쉼표나 연결어미(~는데, ~거든요, ~어서 등) 뒤에서 끊어 두세 줄로 나눠.{box_note}
2. 한 줄 한 절 — 한 줄에 문장을 두 개 이어 붙이지 않았는가? 줄 중간에 마침표가 있으면 거기서 줄바꿈해.
3. 느낌표 — 본문에 ! 가 하나도 없는가? 있으면 전부 .ᐟ 로 바꿔.
4. 나열 기호 — 본문 줄 앞에 •, -, *, ▶, → 를 붙여 나열한 곳이 없는가?{bullet_note}
5. 이모지 — 허용 목록 밖 이모지(💖 💕 🔥 😍 🤤 💯 등)를 쓰지 않았는가?
6. 제목 길이 — 대제목은 16자 안팎(최대 20자), 소제목은 22자 이내로 짧은가? 둘 다 본문보다 큰 글씨라 길면 모바일에서 줄이 쪼개져 답답해진다. (본문 30자 규칙과 별개)
7. 경험 — 정보 나열에 그치지 않고 '내가 직접 써본/다녀온' 1인칭 경험이 글 전체에 살아 있는가?
8. 정보 — 재료에 있는 가격·영업시간·웨이팅 같은 구체 숫자 정보가 본문에서 빠지지 않았는가? (재료에 없는 숫자를 지어내는 건 금지)
9. 균형 — 재료에 아쉬운 점이 있었다면 본문에 1개 이상 솔직하게 반영했는가? (없는 단점을 지어내는 건 금지)"""
