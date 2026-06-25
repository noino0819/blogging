"""게시 플랜 — 초안(DraftResult) → 에디터에 넣을 블록 시퀀스 (순수 변환, 테스트 가능).

본문을 [사진] 마커 기준으로 텍스트/이미지 블록으로 나누고, 강조 span을
해당 텍스트 블록에 배분한다. 이 플랜을 editor가 Smart Editor에 주입한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoblog.collect.fact_card import PhotoItem
from autoblog.draft.generate import DraftResult
from autoblog.publish.emphasis import StyledSpan

PHOTO_MARKER = "[사진]"


class PublishBlock(BaseModel):
    kind: str  # "text" | "image"
    text: str = ""
    emphases: list[StyledSpan] = Field(default_factory=list)
    image_path: str | None = None
    image_label: str = ""


class PublishPlan(BaseModel):
    title: str
    blocks: list[PublishBlock] = Field(default_factory=list)


def build_publish_plan(
    draft: DraftResult, photos: list[PhotoItem] | None = None
) -> PublishPlan:
    """초안 → 게시 플랜. 첫 비어있지 않은 줄을 제목, 나머지를 본문으로 본다."""
    photos = list(photos or [])
    lines = draft.text.split("\n")

    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            title = line.strip()
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()

    segments = body.split(PHOTO_MARKER)
    blocks: list[PublishBlock] = []
    photo_idx = 0
    for i, seg in enumerate(segments):
        seg = seg.strip("\n")
        if seg.strip():
            spans = [e for e in draft.emphases if e.text and e.text in seg]
            blocks.append(PublishBlock(kind="text", text=seg, emphases=spans))
        # 세그먼트 사이마다 사진 한 장 삽입
        if i < len(segments) - 1 and photo_idx < len(photos):
            ph = photos[photo_idx]
            blocks.append(
                PublishBlock(kind="image", image_path=ph.path, image_label=ph.label)
            )
            photo_idx += 1

    # [사진] 마커보다 사진이 많으면 본문 끝에 남은 사진 첨부
    for ph in photos[photo_idx:]:
        blocks.append(PublishBlock(kind="image", image_path=ph.path, image_label=ph.label))

    return PublishPlan(title=title, blocks=blocks)
