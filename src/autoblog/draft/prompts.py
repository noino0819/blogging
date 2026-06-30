"""기본 베이스 프롬프트 로딩 (사용자 편집 가능).

config/prompts/default.md 를 시스템 프롬프트의 기본 베이스로 사용한다.
파일 상단의 메타 안내(제목 + 인용 블록, 첫 '---' 이전)는 모델에 보내지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from autoblog.config import CONFIG_DIR

DEFAULT_PROMPT_PATH = CONFIG_DIR / "prompts" / "default.md"
PRODUCT_PROMPT_PATH = CONFIG_DIR / "prompts" / "product.md"


def load_base_prompt(path: str | Path | None = None, *, card=None) -> str:
    """베이스 프롬프트 텍스트 로드(상단 메타 안내 제거).

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
    text = Path(path or DEFAULT_PROMPT_PATH).read_text(encoding="utf-8")
    marker = "\n---\n"
    idx = text.find(marker)
    if idx != -1:
        text = text[idx + len(marker) :]
    return text.strip()
