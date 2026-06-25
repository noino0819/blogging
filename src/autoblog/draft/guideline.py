"""가이드라인 — 선택 옵션 레이어 + 체크리스트 자동 대조 (기획서 §2, §4.1).

체험단 글은 별도 유형이 아니라 맛집/상품 글에 가이드라인을 얹은 것.
입력되면 초안 작성 시 '최우선 제약'으로 적용하고, 생성 후 자동 대조로
반려를 예방한다(킬러 기능).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Guidelines(BaseModel):
    """체험단 등 가이드라인 항목 (비어 있으면 무시)."""

    required_keywords: list[str] = Field(default_factory=list)
    required_hashtags: list[str] = Field(default_factory=list)
    emphasis_features: list[str] = Field(default_factory=list)  # 강조할 특징
    forbidden_expressions: list[str] = Field(default_factory=list)  # 금지 표현
    min_chars: int | None = None
    min_photos: int | None = None

    def is_empty(self) -> bool:
        return not any(
            [
                self.required_keywords,
                self.required_hashtags,
                self.emphasis_features,
                self.forbidden_expressions,
                self.min_chars,
                self.min_photos,
            ]
        )

    def as_prompt(self) -> str | None:
        """최우선 제약으로 넣을 가이드라인 지시문."""
        if self.is_empty():
            return None
        lines = ["[가이드라인 — 반드시 지켜야 하는 최우선 제약]"]
        if self.required_keywords:
            lines.append(f"- 필수 키워드(본문에 포함): {', '.join(self.required_keywords)}")
        if self.emphasis_features:
            lines.append(f"- 강조할 특징: {', '.join(self.emphasis_features)}")
        if self.required_hashtags:
            lines.append(f"- 필수 해시태그(끝에): {' '.join(self.required_hashtags)}")
        if self.forbidden_expressions:
            lines.append(f"- 금지 표현(쓰지 말 것): {', '.join(self.forbidden_expressions)}")
        if self.min_chars:
            lines.append(f"- 최소 글자 수: {self.min_chars}자 이상")
        if self.min_photos:
            lines.append(f"- 사진 최소 {self.min_photos}장(본문에 사진 자리 표시)")
        return "\n".join(lines)


class CheckItem(BaseModel):
    item: str
    ok: bool
    detail: str = ""


def check_guidelines(
    draft: str, guidelines: Guidelines, photo_count: int | None = None
) -> list[CheckItem]:
    """초안을 가이드라인과 자동 대조 → 체크리스트(반려 방지)."""
    results: list[CheckItem] = []
    text = draft
    length = len(draft.replace(" ", "").replace("\n", ""))

    for kw in guidelines.required_keywords:
        results.append(CheckItem(item=f"키워드 '{kw}'", ok=kw in text))
    for tag in guidelines.required_hashtags:
        results.append(CheckItem(item=f"해시태그 '{tag}'", ok=tag in text))
    for feat in guidelines.emphasis_features:
        results.append(CheckItem(item=f"강조 '{feat}'", ok=feat in text))
    for bad in guidelines.forbidden_expressions:
        present = bad in text
        results.append(
            CheckItem(item=f"금지어 '{bad}' 미포함", ok=not present, detail="발견됨" if present else "")
        )
    if guidelines.min_chars:
        results.append(
            CheckItem(
                item=f"최소 {guidelines.min_chars}자",
                ok=length >= guidelines.min_chars,
                detail=f"현재 {length}자(공백 제외)",
            )
        )
    if guidelines.min_photos is not None and photo_count is not None:
        results.append(
            CheckItem(
                item=f"사진 {guidelines.min_photos}장 이상",
                ok=photo_count >= guidelines.min_photos,
                detail=f"현재 {photo_count}장",
            )
        )
    return results
