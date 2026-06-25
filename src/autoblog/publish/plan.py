"""게시 플랜 — 초안(DraftResult) → 에디터에 넣을 블록 시퀀스 (순수 변환, 테스트 가능).

본문을 [사진] 마커 기준으로 텍스트/이미지 블록으로 나누고, 강조 span을
해당 텍스트 블록에 배분한다. 이 플랜을 editor가 Smart Editor에 주입한다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from autoblog.collect.fact_card import PhotoItem
from autoblog.draft.generate import DraftResult
from autoblog.publish.emphasis import StyledSpan
from autoblog.publish.stickers import StickerPicker

PHOTO_MARKER = "[사진]"
# [사진] / [사진:음식] — 라벨로 어떤 사진을 그 자리에 놓을지 지정 가능
_PHOTO_RE = re.compile(r"^\[사진(?::(.+?))?\]$")
QUOTE_CLOSE = "[/인용구]"
# [구분선] / [구분선:2], [인용구] / [인용구:3] — 종류(variant) 선택 가능
_DIVIDER_RE = re.compile(r"^\[구분선(?::(\d+))?\]$")
_QUOTE_OPEN_RE = re.compile(r"^\[인용구(?::(\d+))?\]$")
# [스티커] / [스티커:상황] — picker가 라벨을 (팩,인덱스)로 해석
_STICKER_RE = re.compile(r"^\[스티커(?::(.+?))?\]$")

# 구분선/인용구 종류 메타 — value(에디터 data-value) → (variant 인덱스, 이름, 어느 상황에 쓰면 좋은지)
# 라이브 캡쳐한 모양을 보고 작성. UI에 이름·용도 노출, 초안 LLM에 상황 안내, 마커 [구분선:이름] 해석에 사용.
DIVIDER_META = {
    "default": (1, "기본 가는 선", "가장 무난한 화제 전환. 어디에나 어울림"),
    "line1": (2, "실선", "깔끔하고 또렷한 구분. 단락이 확실히 바뀔 때"),
    "line2": (3, "굵은 짧은 선", "강한 전환·소제목 느낌. 챕터를 크게 나눌 때"),
    "line3": (4, "가운데 꺾인 선", "부드러운 전환. 감성적인 흐름 사이"),
    "line4": (5, "다이아몬드 선", "장식적·포인트. 특별한 구간을 나눌 때"),
    "line5": (6, "점선", "가볍게 끊기. 부연·메모로 살짝 넘어갈 때"),
    "line6": (7, "사선", "캐주얼한 분위기 전환. 가벼운 글에"),
    "line7": (8, "세로선", "짧은 좌우 구분(드물게). 나란히 비교할 때"),
}
QUOTE_META = {
    "default": (1, "기본(큰따옴표)", "핵심 한마디를 가운데 크게. 글의 메시지 강조"),
    "quotation_line": (2, "왼쪽 줄", "짧은 인용·출처 있는 문장. 담백하게"),
    "quotation_bubble": (3, "말풍선", "대화체·후기 코멘트. 말하듯 전할 때"),
    "quotation_underline": (4, "밑줄형", "한 문장 또렷이 강조. 결론·요점"),
    "quotation_postit": (5, "포스트잇", "팁·꿀팁·메모. 알아두면 좋은 정보"),
    "quotation_corner": (6, "모서리", "감성적 인용·마무리 멘트. 여운 남길 때"),
}

# 초안 구조 마커: 구분선 [구분선], 인용 블록 [인용구]…[/인용구]
# (EMPHASIS_INSTRUCTION과 같은 추가 레이어. generate_draft(structure=True)에서 시스템 프롬프트에 덧붙임)
# 14b 모델은 "절제" 위주로 안내하면 마커를 아예 안 단다(라이브 측정: 0/0/0).
# "권장이 아니라 사용 + 예시 + 개수 지정"으로 바꾸니 화제전환 있는 글에서 실제로 emit됨.
STRUCTURE_INSTRUCTION = (
    "[구조 마커] — 아래 마커를 본문에 실제로 넣어 글을 읽기 좋게 나누세요(권장이 아니라 사용).\n"
    "- 화제가 바뀌는 문단 사이에 [구분선] 을 한 줄로 1~2번.\n"
    "- 글 전체를 관통하는 핵심 메시지·감상 '한마디'가 있을 때만 그 한 문장을 [인용구] 와 [/인용구] 로 "
    "감싸세요(없으면 넣지 마세요, 최대 1번).\n"
    "  음식·분위기를 묘사하는 짧은 카피성 문구(예: '겉은 바삭 속은 촉촉')는 인용구로 만들지 말고, "
    '강조하려면 본문 안에서 큰따옴표(" ")로 감싸 쓰세요.\n'
    "예시:\n오늘 다녀온 첫 소감 문단.\n\n[구분선]\n\n[인용구]\n여기는 두 번 세 번 와도 안 질릴 곳\n[/인용구]\n\n다음 문단.\n"
    "마커는 화면에 글자로 안 보이고 서식으로 바뀝니다. 문장 안에 섞지 말고 줄 단독으로 두세요."
)


class PublishBlock(BaseModel):
    kind: str  # "text" | "image" | "divider" | "quote" | "sticker"
    text: str = ""
    emphases: list[StyledSpan] = Field(default_factory=list)
    image_path: str | None = None
    image_label: str = ""
    variant: int = 1  # 구분선/인용구 종류(1=기본)
    sticker_pack: str | None = None  # 스티커 팩 코드(picker 해석 결과)
    sticker_index: int | None = None  # 스티커 data-index


class PublishPlan(BaseModel):
    title: str
    blocks: list[PublishBlock] = Field(default_factory=list)


def build_publish_plan(
    draft: DraftResult,
    photos: list[PhotoItem] | None = None,
    picker: StickerPicker | None = None,
    divider_variant: int = 1,
    quote_variant_default: int = 1,
) -> PublishPlan:
    """초안 → 게시 플랜 (줄 단위 마커 파싱).

    첫 비어있지 않은 줄=제목. 본문에서 마커를 블록으로 분리:
    - [사진]/[사진:라벨] → 이미지(라벨 같은 사진 우선, 없으면 남은 순서대로)
    - [구분선]    → 구분선
    - [인용구]…[/인용구] → 인용 블록
    - [스티커:상황] → picker가 (팩,인덱스)로 해석한 스티커(picker 없거나 미해석이면 무시)
    그 외 줄은 텍스트 문단으로 누적. 강조 span은 해당 텍스트 블록에 배분.
    """
    photos = list(photos or [])
    lines = draft.text.split("\n")

    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            title = line.strip()
            body_start = i + 1
            break
    body_lines = lines[body_start:]

    blocks: list[PublishBlock] = []
    text_buf: list[str] = []
    quote_buf: list[str] = []
    in_quote = False
    quote_variant = 1
    used = [False] * len(photos)  # 사진별 사용 여부(순서 아닌 라벨로 매칭)

    def take_photo(label: str | None) -> PhotoItem | None:
        """라벨이 같은 안 쓴 사진 우선, 없으면 남은 사진 순서대로. 다 쓰면 None."""
        if label:
            for i, ph in enumerate(photos):
                if not used[i] and ph.label == label:
                    used[i] = True
                    return ph
        for i, ph in enumerate(photos):
            if not used[i]:
                used[i] = True
                return ph
        return None

    def flush_text():
        text = "\n".join(text_buf).strip()
        text_buf.clear()
        if text:
            spans = [e for e in draft.emphases if e.text and e.text in text]
            blocks.append(PublishBlock(kind="text", text=text, emphases=spans))

    for line in body_lines:
        s = line.strip()
        if in_quote:
            if s == QUOTE_CLOSE:
                in_quote = False
                qtext = "\n".join(quote_buf).strip()
                quote_buf.clear()
                if qtext:
                    blocks.append(PublishBlock(kind="quote", text=qtext, variant=quote_variant))
            else:
                quote_buf.append(line)
            continue
        div_m = _DIVIDER_RE.match(s)
        quote_m = _QUOTE_OPEN_RE.match(s)
        sticker_m = _STICKER_RE.match(s)
        photo_m = _PHOTO_RE.match(s)
        if div_m:
            flush_text()
            blocks.append(PublishBlock(kind="divider", variant=int(div_m.group(1) or divider_variant)))
        elif sticker_m:
            flush_text()
            chosen = picker.pick(sticker_m.group(1) or "") if picker else None
            if chosen:  # 해석 실패(picker 없음/매칭 없음)면 마커 자체를 버림(본문 누수 방지)
                blocks.append(
                    PublishBlock(
                        kind="sticker", sticker_pack=chosen.pack, sticker_index=chosen.index
                    )
                )
        elif quote_m:
            flush_text()
            in_quote = True
            quote_variant = int(quote_m.group(1) or quote_variant_default)
        elif photo_m:
            flush_text()
            ph = take_photo(photo_m.group(1))
            if ph is not None:
                blocks.append(PublishBlock(kind="image", image_path=ph.path, image_label=ph.label))
        else:
            text_buf.append(line)
    flush_text()
    if in_quote and quote_buf:  # 닫힘 누락 방어
        blocks.append(
            PublishBlock(kind="quote", text="\n".join(quote_buf).strip(), variant=quote_variant)
        )

    # [사진] 마커보다 사진이 많으면 본문 끝에 남은 사진 첨부
    for i, ph in enumerate(photos):
        if not used[i]:
            blocks.append(PublishBlock(kind="image", image_path=ph.path, image_label=ph.label))

    return PublishPlan(title=title, blocks=blocks)
