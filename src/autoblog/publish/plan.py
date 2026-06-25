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

PHOTO_MARKER = "[사진]"
QUOTE_CLOSE = "[/인용구]"
# [구분선] / [구분선:2], [인용구] / [인용구:3] — 종류(variant) 선택 가능
_DIVIDER_RE = re.compile(r"^\[구분선(?::(\d+))?\]$")
_QUOTE_OPEN_RE = re.compile(r"^\[인용구(?::(\d+))?\]$")

# 초안 구조 마커: 구분선 [구분선], 인용 블록 [인용구]…[/인용구]
# (EMPHASIS_INSTRUCTION과 같은 추가 레이어. generate_draft(structure=True)에서 시스템 프롬프트에 덧붙임)
STRUCTURE_INSTRUCTION = (
    "[구조 마커]\n"
    "가독성을 위해 아래 마커를 절제해서 사용하세요. 마커는 반드시 그 줄에 단독으로 두세요.\n"
    "- 구분선: 화제가 크게 바뀌는 지점에 [구분선] 을 한 줄로 넣으세요. 글 전체에서 1~3개면 충분합니다.\n"
    "- 인용구: 특히 강조하고 싶은 핵심 한두 문장을 [인용구] 와 [/인용구] 로 감싸세요. "
    "한 블록에 1~2문장만, 글 전체에서 1~2개로 절제하세요.\n"
    "이 마커는 화면에 글자로 보이지 않고 서식으로 바뀌니, 본문 문장 안에 섞지 말고 꼭 필요한 곳에만 쓰세요."
)


class PublishBlock(BaseModel):
    kind: str  # "text" | "image" | "divider" | "quote"
    text: str = ""
    emphases: list[StyledSpan] = Field(default_factory=list)
    image_path: str | None = None
    image_label: str = ""
    variant: int = 1  # 구분선/인용구 종류(1=기본)


class PublishPlan(BaseModel):
    title: str
    blocks: list[PublishBlock] = Field(default_factory=list)


def build_publish_plan(
    draft: DraftResult, photos: list[PhotoItem] | None = None
) -> PublishPlan:
    """초안 → 게시 플랜 (줄 단위 마커 파싱).

    첫 비어있지 않은 줄=제목. 본문에서 마커를 블록으로 분리:
    - [사진]      → 이미지(photos 순서대로)
    - [구분선]    → 구분선
    - [인용구]…[/인용구] → 인용 블록
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
    photo_idx = 0

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
        if div_m:
            flush_text()
            blocks.append(PublishBlock(kind="divider", variant=int(div_m.group(1) or 1)))
        elif quote_m:
            flush_text()
            in_quote = True
            quote_variant = int(quote_m.group(1) or 1)
        elif s == PHOTO_MARKER:
            flush_text()
            if photo_idx < len(photos):
                ph = photos[photo_idx]
                blocks.append(PublishBlock(kind="image", image_path=ph.path, image_label=ph.label))
                photo_idx += 1
        else:
            text_buf.append(line)
    flush_text()
    if in_quote and quote_buf:  # 닫힘 누락 방어
        blocks.append(
            PublishBlock(kind="quote", text="\n".join(quote_buf).strip(), variant=quote_variant)
        )

    # [사진] 마커보다 사진이 많으면 본문 끝에 남은 사진 첨부
    for ph in photos[photo_idx:]:
        blocks.append(PublishBlock(kind="image", image_path=ph.path, image_label=ph.label))

    return PublishPlan(title=title, blocks=blocks)
