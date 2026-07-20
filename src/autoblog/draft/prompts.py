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

    path를 명시하지 않고 card가 상품 카드(FactCard.is_product — 타입 또는 상품 데이터)면
    product.md를 쓴다. product.md가 없으면 default.md로 폴백한다(맛집·상품 공용).
    공통 문체 규칙(common_style.md)은 자동 선택 경로에서만 이어 붙인다 — path를
    직접 지정한 커스텀 프롬프트(CLI --prompt-file 등)는 그 파일 그대로가 베이스다.
    """
    explicit_path = path is not None
    if path is None and card is not None and PRODUCT_PROMPT_PATH.exists():
        if getattr(card, "is_product", False):
            path = PRODUCT_PROMPT_PATH
    text = _strip_meta(Path(path or DEFAULT_PROMPT_PATH).read_text(encoding="utf-8"))
    if not explicit_path and COMMON_STYLE_PROMPT_PATH.exists():
        # 공통 문체 규칙(맛집·상품 공용, 단일 출처)
        common = _strip_meta(COMMON_STYLE_PROMPT_PATH.read_text(encoding="utf-8"))
        if common:
            text = f"{text}\n\n{common}"
    return text


# 맛집·상품 공통 자가 점검 — 시스템 프롬프트 맨 끝에 항상 붙인다(단일 출처).
# 가장 자주 어기는 기계적 규칙만 짧게 추렸다. 외부 챗봇에 붙여넣어 쓰는 경로는
# enforce_format 후처리를 안 거치므로, 모델이 스스로 점검·수정하게 만드는 게 핵심.
# 나열 박스 예외는 상품 리뷰에만 있는 개념이라 is_product일 때만 언급한다
# (맛집 글에 예외를 언급하면 허용되는 것으로 오독할 수 있음).


def build_selfcheck_instruction(is_product: bool = False, ornaments: bool = True) -> str:
    """자가 점검 지시문(시스템 프롬프트 맨 끝에 붙이는 블록).

    is_product=True(상품 리뷰)면 나열 박스(1️⃣~·✅) 예외 문구를 함께 넣는다.
    ornaments=False(발랄체가 아닌 어투)면 어투 결합 항목(느낌표→.ᐟ 치환, 이모지 허용
    목록)을 뺀다 — 그 어투에는 해당 규칙이 없고, 기준은 [추가 문체 지시]가 정한다.
    """
    box_note = " (요약 박스 1️⃣~·추천 체크리스트 ✅ 한 줄은 예외)" if is_product else ""
    bullet_note = " (요약 박스·추천 체크리스트만 예외)" if is_product else ""
    items = [
        "줄 길이 — 본문에 30자를 넘는 줄이 하나도 없는가? 넘으면 쉼표나 연결어미(~는데, "
        f"~거든요, ~어서 등) 뒤에서 끊어 두세 줄로 나눠.{box_note}",
        "한 줄 한 절 — 한 줄에 문장을 두 개 이어 붙이지 않았는가? 줄 중간에 마침표가 있으면 거기서 줄바꿈해.",
    ]
    if ornaments:
        items.append("느낌표 — 본문에 ! 가 하나도 없는가? 있으면 전부 .ᐟ 로 바꿔.")
    items.append(f"나열 기호 — 본문 줄 앞에 •, -, *, ▶, → 를 붙여 나열한 곳이 없는가?{bullet_note}")
    if ornaments:
        items.append("이모지 — 허용 목록 밖 이모지(💖 💕 🔥 😍 🤤 💯 등)를 쓰지 않았는가?")
    items += [
        "검색 제목 — 첫 줄 제목이 20~40자이고, 대표 검색 키워드가 앞 25자 안에 띄어쓰기까지 "
        "그대로 들어가 있는가? 제목에 넣은 숫자·훅은 본문에서 실제로 다뤘는가? (불일치는 낚시로 찍힘)",
        "제목 길이 — 대제목은 16자 안팎(최대 20자), 소제목은 22자 이내로 짧은가? "
        "둘 다 본문보다 큰 글씨라 길면 모바일에서 줄이 쪼개져 답답해진다. (본문 30자 규칙과 별개)",
        "경험 — 정보 나열에 그치지 않고 '내가 직접 써본/다녀온' 1인칭 경험이 글 전체에 살아 있는가?",
        "정보 — 재료에 있는 가격·영업시간·웨이팅 같은 구체 숫자 정보가 본문에서 빠지지 않았는가? "
        "(재료에 없는 숫자를 지어내는 건 금지)",
        "AI 검색 — 재료에 방문·구매·사용 시점이 있으면 본문에 드러냈는가? 가격·웨이팅·주차·"
        "영업시간 문장은 그 대목만 떼어 읽어도 무엇에 대한 정보인지 통하는가?",
        "균형 — 재료에 아쉬운 점이 있었다면 본문에 1개 이상 솔직하게 반영했는가? (없는 단점을 지어내는 건 금지)",
        "문체 — 모든 문장이 문체 지시의 어투(종결어미·이모티콘·꾸밈 문자 기준)를 따르는가? "
        "다른 어투의 말버릇이 섞였으면 문체 지시에 맞게 고쳐.",
        "자연스러움 — 모든 문장을 소리 내어 읽듯 하나씩 검토했는가? 어미가 이중으로 붙거나"
        '("맛있더라궁 같은 기분이더라구요"처럼 꼬인 문장), 경험 메모의 문구가 그대로 섞여 '
        "어색해진 문장이 있으면 뜻은 살리고 자연스러운 한 문장으로 다시 써.",
        "AI 티 — 사람이 말로는 안 할 법한 반듯한 작문체가 없는가? 모든 문단이 비슷한 길이·"
        '구조로 반복되거나, "전반적으로"·"~라고 할 수 있어요" 같은 정리 멘트가 돌아오거나, '
        '대제목·훅이 말맛 없이 밋밋하면("이번 주도 결국 여기로 왔다" 같은) AI 티가 난다. '
        "친구한테 말하듯 리듬을 흐트러뜨려 다시 써.",
    ]
    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))
    return f"""## 제출 전 자가 점검 (반드시 마지막에 수행)

글을 다 썼으면 제출하기 전에 아래를 한 항목씩 직접 검사하고, 어긴 곳이 있으면 그 자리에서 고친 뒤 최종본만 내보내. 이 점검을 생략하지 마.

{numbered}"""
