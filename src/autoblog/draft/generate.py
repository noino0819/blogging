"""초안 생성 — 프롬프트 조립 → 텍스트 LLM 호출 (기획서 §4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoblog.collect.fact_card import FactCard
from autoblog.draft.guideline import CheckItem, Guidelines, check_guidelines
from autoblog.draft.postprocess import enforce_format
from autoblog.draft.prompt import build_system_prompt, build_user_prompt
from autoblog.draft.prompts import load_base_prompt
from autoblog.draft.rules import CommonRules
from autoblog.draft.style import StyleProfile
from autoblog.llm import chat


class DraftRequest(BaseModel):
    fact_card: FactCard
    experience_memo: str
    base_prompt: str | None = None  # None이면 config/prompts/default.md 사용
    rules: CommonRules | None = None  # 선택적 추가 규칙
    style: StyleProfile | None = None
    guidelines: Guidelines | None = None
    photo_count: int | None = None
    postprocess: bool = True  # 결정적 포맷 규칙 후처리 강제


class DraftResult(BaseModel):
    text: str
    checklist: list[CheckItem] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checklist)


def generate_draft(req: DraftRequest, model: str | None = None) -> DraftResult:
    """초안 생성 후, 가이드라인이 있으면 체크리스트로 자동 대조."""
    base = req.base_prompt or load_base_prompt()
    system = build_system_prompt(base, req.style, req.guidelines, req.rules)
    user = build_user_prompt(req.fact_card, req.experience_memo)
    text = chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=model,
    ).strip()
    if req.postprocess:
        text = enforce_format(text)

    checklist: list[CheckItem] = []
    if req.guidelines and not req.guidelines.is_empty():
        photo_count = req.photo_count
        if photo_count is None and req.fact_card.photos:
            photo_count = len(req.fact_card.photos)
        checklist = check_guidelines(text, req.guidelines, photo_count)
    return DraftResult(text=text, checklist=checklist)
