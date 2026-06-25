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
from autoblog.publish.emphasis import (
    EMPHASIS_INSTRUCTION,
    EmphasisConfig,
    EmphasisStyle,
    StyledSpan,
    apply_density,
    assign_emphasis,
    load_emphasis_config,
    parse_emphasis_markup,
)


class DraftRequest(BaseModel):
    fact_card: FactCard
    experience_memo: str
    base_prompt: str | None = None  # None이면 config/prompts/default.md 사용
    rules: CommonRules | None = None  # 선택적 추가 규칙
    style: StyleProfile | None = None
    guidelines: Guidelines | None = None
    photo_count: int | None = None
    postprocess: bool = True  # 결정적 포맷 규칙 후처리 강제
    # 강조(서식) — 켜면 LLM이 <<role:text>> 마킹 → 순환/고정 매핑 배정
    emphasis: bool = False
    # 구조 마커 — 켜면 LLM이 [구분선]/[인용구]…[/인용구] 마커를 알아서 삽입(plan에서 블록으로 변환)
    structure: bool = False
    # 스티커 — 보유 상황 라벨을 주면 LLM이 [스티커:상황] 마커를 그 어휘 안에서만 emit
    sticker_labels: list[str] = Field(default_factory=list)
    emphasis_config: EmphasisConfig | None = None  # None이면 config/emphasis.yaml
    power_shortcuts: dict[int, EmphasisStyle] | None = None  # None이면 내장 기본 스타일


class DraftResult(BaseModel):
    text: str
    checklist: list[CheckItem] = Field(default_factory=list)
    emphases: list[StyledSpan] = Field(default_factory=list)
    debug: dict = Field(default_factory=dict)  # {system, user, raw, model} — 프롬프트/원본 출력 확인용

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checklist)


def build_prompt(req: DraftRequest) -> tuple[str, str]:
    """초안 요청 → (system, user) 프롬프트 조립. LLM 호출은 안 함.

    generate_draft가 쓰는 것과 동일한 조립 로직. 외부 챗봇에 붙여넣을 프롬프트
    내보내기에도 재사용한다(같은 지시문이 들어가도록 단일 출처 유지).
    """
    base = req.base_prompt or load_base_prompt()
    system = build_system_prompt(base, req.style, req.guidelines, req.rules)
    if req.emphasis:
        system = f"{system}\n\n{EMPHASIS_INSTRUCTION}"
    if req.structure:
        from autoblog.publish.plan import STRUCTURE_INSTRUCTION  # 지연 임포트(순환 회피)

        system = f"{system}\n\n{STRUCTURE_INSTRUCTION}"
    if req.sticker_labels:
        from autoblog.publish.stickers import build_sticker_instruction

        instr = build_sticker_instruction(req.sticker_labels)
        if instr:
            system = f"{system}\n\n{instr}"
    user = build_user_prompt(req.fact_card, req.experience_memo)
    return system, user


def generate_draft(req: DraftRequest, model: str | None = None) -> DraftResult:
    """초안 생성 후, 강조 마킹 배정·포맷 후처리·가이드라인 대조를 수행."""
    from autoblog.publish.emphasis import DEFAULT_STYLES, load_default_power_shortcuts

    system, user = build_prompt(req)
    raw = chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=model,
    ).strip()
    text = raw
    debug = {"system": system, "user": user, "raw": raw, "model": model or ""}

    # 강조 마킹 추출(포맷 후처리 전에 — 줄바꿈이 <<>>를 깨지 않도록)
    emphases: list[StyledSpan] = []
    if req.emphasis:
        text, requests = parse_emphasis_markup(text)
        # 우선순위: 요청 지정 > 프로젝트 프리셋(config/power_shortcuts.json) > 내장 기본
        presets = req.power_shortcuts or load_default_power_shortcuts() or DEFAULT_STYLES
        config = req.emphasis_config or load_emphasis_config()
        requests = apply_density(text, requests, config)  # 밀도 규칙으로 과한 강조 솎기
        emphases = assign_emphasis(requests, presets, config)
        if req.postprocess:  # 강조 텍스트도 본문과 같은 문자 규칙으로 정규화(매칭 유지)
            for span in emphases:
                span.text = enforce_format(span.text, wrap=False)

    if req.postprocess:
        text = enforce_format(text)

    checklist: list[CheckItem] = []
    if req.guidelines and not req.guidelines.is_empty():
        photo_count = req.photo_count
        if photo_count is None and req.fact_card.photos:
            photo_count = len(req.fact_card.photos)
        checklist = check_guidelines(text, req.guidelines, photo_count)
    return DraftResult(text=text, checklist=checklist, emphases=emphases, debug=debug)
