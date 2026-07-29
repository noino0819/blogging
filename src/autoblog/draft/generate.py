"""초안 생성 — 프롬프트 조립 → 텍스트 LLM 호출 (기획서 §4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoblog.collect.fact_card import FactCard
from autoblog.draft.guideline import CheckItem, Guidelines, check_exposure, check_guidelines
from autoblog.draft.postprocess import enforce_format
from autoblog.draft.prompt import build_system_prompt, build_user_prompt
from autoblog.draft.prompts import build_selfcheck_instruction, load_base_prompt
from autoblog.draft.rules import CommonRules
from autoblog.draft.style import StyleProfile
from autoblog.draft.variation import build_variation_block
from autoblog.llm import chat
from autoblog.publish.emphasis import (
    EmphasisConfig,
    build_emphasis_instruction,
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
    # 검색으로 교차 확인한 사실(칼로리·영양정보·가격 등) — 수집 API로는 못 얻는 값을
    # '참고 정보'로 흘려보내는 통로. 없으면 기존과 동일(지어내지 않고 생략).
    search_facts: str | None = None
    base_prompt: str | None = None  # None이면 config/prompts/default.md 사용
    rules: CommonRules | None = None  # 선택적 추가 규칙
    style: StyleProfile | None = None
    guidelines: Guidelines | None = None
    photo_count: int | None = None
    postprocess: bool = True  # 결정적 포맷 규칙 후처리 강제
    # 생성 직후 LLM 2차 자가검수 패스 — 시스템 프롬프트 끝의 자가 점검 지시는 생성 중
    # 한 번 읽고 지나가 실제로는 자주 안 지켜진다(특히 느낌표·줄 길이·사진 분산).
    # 같은 점검 목록으로 '검수만' 하는 별도 호출을 한 번 더 돌려 실제로 교정하게 한다.
    selfreview: bool = True
    # 강조(서식) — 켜면 LLM이 <<role:text>> 마킹 → 순환/고정 매핑 배정
    emphasis: bool = False
    # 구조 마커 — 켜면 LLM이 [구분선]/[인용구]…[/인용구] 마커를 알아서 삽입(plan에서 블록으로 변환)
    structure: bool = False
    # 유저가 '서식'에서 고른 구분선/인용구 종류(DIVIDER_META/QUOTE_META 키). 비우면 기본 한 종류.
    # 여러 개면 프롬프트가 그 종류만 나열하고 LLM이 상황에 맞게 [구분선:번호]/[인용구:번호]로 고른다.
    divider_variants: list[str] = Field(default_factory=list)
    quote_variants: list[str] = Field(default_factory=list)
    # 스티커 — 보유 상황 라벨을 주면 LLM이 [스티커:상황] 마커를 그 어휘 안에서만 emit
    sticker_labels: list[str] = Field(default_factory=list)
    # 장소(지도) — 맛집 글에서 켜면 위치 안내 자리에 [지도] 마커를 넣게 안내(plan에서 장소 카드로)
    place: bool = False
    # 불러온 글 in-place 편집 — 동영상은 위치를 못 바꾸므로 [영상] 마커를 문서 순서 그대로
    # 넣게 재료에 못박는다(재업로드 불가 → 순서 고정).
    inplace: bool = False
    template_text: str | None = None
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


def effective_style(req: DraftRequest) -> StyleProfile:
    """요청의 문체를 확정한다 — 문체(profile) 미지정이면 기본 어투 프리셋을 채운다.

    어투는 항상 정확히 하나의 레이어만 적용된다: 유저가 페르소나/프리셋을 고르면 그것이
    어투가 되고(기본어투 미적용), 아무것도 안 고르면 기본 프리셋(발랄 구어체)이 어투다.
    ornaments(카오모지·유행어 변주 + !→.ᐟ 치환)는 그 어투의 설정을 따른다.
    """
    from autoblog.draft.tones import default_tone

    style = req.style or StyleProfile()
    if style.profile:
        return style
    preset = default_tone()
    if preset is None:  # tones.yaml 없음 — 어투 레이어 없이 진행(포맷 규칙만)
        return style
    return style.model_copy(update={"profile": preset.prompt, "ornaments": preset.ornaments})


def build_prompt(req: DraftRequest) -> tuple[str, str]:
    """초안 요청 → (system, user) 프롬프트 조립. LLM 호출은 안 함.

    generate_draft가 쓰는 것과 동일한 조립 로직. 외부 챗봇에 붙여넣을 프롬프트
    내보내기에도 재사용한다(같은 지시문이 들어가도록 단일 출처 유지).
    """
    is_product = req.fact_card.is_product
    base = req.base_prompt or load_base_prompt(card=req.fact_card)
    style = effective_style(req)
    system = build_system_prompt(base, style, req.guidelines, req.rules)
    # 시드 기반 스타일 변주 — 글(재료)마다 카오모지 부분집합·빈도·구조를 다르게 배정해
    # 전 글이 같은 패턴으로 수렴하는 기계 지문을 막는다(같은 재료면 같은 변주 = 재현성).
    # 어투 결합 변주(카오모지·유행어·특수문자)는 꾸밈 어투(ornaments)에서만 — 다른 어투에
    # 주입하면 문체 지시보다 뒤에 붙는 변주 블록이 유저가 고른 문체를 덮어쓴다.
    # 구조 변주(섹션 흐름 등)는 유사문서 방지 목적이라 어떤 어투든 유지한다.
    subject = ""
    if req.fact_card.place:
        subject = req.fact_card.place.name
    elif req.fact_card.product:
        subject = req.fact_card.product.name
    try:
        variation = build_variation_block(
            f"{req.experience_memo}|{subject}", is_product, ornaments=style.ornaments
        )
    except Exception:  # 변주는 부가 기능 — 풀 데이터가 이상해도 초안 생성은 계속돼야 한다
        variation = None
    if variation:
        system = f"{system}\n\n{variation}"
    if req.emphasis:
        system = f"{system}\n\n{build_emphasis_instruction(load_emphasis_config())}"
    if req.structure:
        from autoblog.publish.plan import build_structure_instruction  # 지연 임포트(순환 회피)

        instr = build_structure_instruction(req.divider_variants, req.quote_variants)
        system = f"{system}\n\n{instr}"
    if req.sticker_labels:
        from autoblog.publish.stickers import build_sticker_instruction

        instr = build_sticker_instruction(req.sticker_labels)
        if instr:
            system = f"{system}\n\n{instr}"
    if req.place:
        from autoblog.publish.plan import build_place_instruction  # 지연 임포트(순환 회피)

        # 수집된 가게명을 마커에 박아 초안을 자립시킨다([지도:가게명] — 붙여넣기 경로에서
        # 수집 링크·세션 캐시가 없어도 지도 삽입 가능)
        pname = req.fact_card.place.name if req.fact_card.place else None
        system = f"{system}\n\n{build_place_instruction(pname or None)}"
    # 자가 점검은 항상 맨 끝에(모델이 마지막으로 읽는 최종 게이트) — 맛집·상품 공통.
    system = f"{system}\n\n{_selfcheck_for(req)}"
    user = build_user_prompt(
        req.fact_card, req.experience_memo, req.template_text, inplace=req.inplace,
        search_facts=req.search_facts,
    )
    return system, user


def _selfcheck_for(req: DraftRequest) -> str:
    """요청 상황(상품 여부·어투·사진·스티커)에 맞춘 자가 점검 지시문 — 생성·검수가 같은 목록을 쓴다."""
    imgs = [p for p in req.fact_card.photos if p.media_kind != "video"]
    return build_selfcheck_instruction(
        req.fact_card.is_product,
        ornaments=effective_style(req).ornaments,
        has_photos=bool(imgs),
        has_stickers=bool(req.sticker_labels),
    )


# 검수 결과 검증용 마커 접두사 — 개수가 바뀌면 검수가 마커를 훼손한 것(원본 유지)
_REVIEW_MARKERS = ("[사진", "[영상", "[지도", "[구분선", "[인용구", "[스티커", "<<")


def review_draft_text(raw: str, req: DraftRequest, model: str | None = None) -> str:
    """생성 직후 2차 자가검수 — 같은 점검 목록으로 초안을 다시 읽고 어긴 곳만 고친 전체 글을 받는다.

    결과가 의심스러우면(빈 응답·길이 급감·마커 개수 변화) 원본을 그대로 돌려준다(안전 폴백).
    """
    system = (
        "너는 방금 이 네이버 블로그 초안을 작성한 저자 본인이고, 지금은 제출 직전 검수 단계다. "
        "아래 점검 목록을 한 항목씩 초안과 대조해서, 어긴 부분만 최소한으로 고쳐라.\n"
        "반드시 지켜라:\n"
        "- 글의 내용·구성·문체·분량은 그대로 두고, 규칙을 어긴 문장만 손본다.\n"
        "- 대괄호 마커([사진]·[사진:라벨]·[영상]·[지도]·[구분선]·[인용구]·[/인용구]·[스티커:이름])와 "
        "<<이름:문구>> 강조 마킹은 지우거나 새로 만들지 않는다. 단, '사진 분산' 항목을 어겼으면 "
        "기존 [사진] 마커의 위치를 옮기는 것은 허용된다(개수는 유지).\n"
        "- 설명·주석·머리말 없이, 고친 최종 글 전체만 출력한다(첫 줄 제목부터 끝까지 빠짐없이).\n\n"
        + _selfcheck_for(req)
    )
    fixed = chat(
        [{"role": "system", "content": system}, {"role": "user", "content": raw}], model=model
    ).strip()
    if not fixed or len(fixed) < len(raw) * 0.6:
        return raw
    for m in _REVIEW_MARKERS:
        if raw.count(m) != fixed.count(m):
            return raw
    return fixed


def generate_draft(
    req: DraftRequest, model: str | None = None, *, raw_override: str | None = None
) -> DraftResult:
    """초안 생성 후, 강조 마킹 배정·포맷 후처리·가이드라인 대조를 수행.

    raw_override를 주면 LLM을 호출하지 않고 그 텍스트를 초안으로 써서 마커 파싱·후처리만
    수행한다(외부 챗봇에서 받아온 글을 그대로 가져올 때 사용).
    """
    from autoblog.publish.emphasis import DEFAULT_STYLES, load_default_power_shortcuts

    if raw_override is not None:
        from autoblog.draft.postprocess import extract_final_draft

        # 외부 챗봇 응답: '초안→자가 점검→=====최종본=====' 프로토콜 응답 전체를
        # 붙여넣어도 최종본만 골라낸다(마커 없으면 원문 그대로).
        system, user = "", ""
        raw = extract_final_draft(raw_override).strip()
    else:
        system, user = build_prompt(req)
        raw = chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model,
        ).strip()
    text = raw
    reviewed = ""
    if raw_override is None and req.selfreview:
        try:
            text = review_draft_text(raw, req, model)
        except Exception:  # noqa: BLE001 - 검수는 보조 단계, 실패해도 초안은 그대로 진행
            text = raw
        if text != raw:
            reviewed = text
    # 상품 리뷰: 나열 박스(✅/1️⃣~) 보존 — 판정은 FactCard.is_product 단일 출처
    # (베이스 프롬프트 선택과 같은 기준이어야 지시와 후처리가 어긋나지 않는다).
    is_product = req.fact_card.is_product
    # 어투 치환(!→.ᐟ 등)은 꾸밈 어투에서만 — 프롬프트와 후처리가 같은 어투 기준을 쓴다.
    ornaments = effective_style(req).ornaments
    debug = {"system": system, "user": user, "raw": raw, "model": model or ""}
    if reviewed:  # 2차 자가검수가 실제로 고친 경우 — 디버그에서 원본과 비교 가능하게
        debug["reviewed"] = reviewed

    # 강조 마킹 추출(포맷 후처리 전에 — 줄바꿈이 <<>>를 깨지 않도록)
    emphases: list[StyledSpan] = []
    span_originals: list[str] = []
    if req.emphasis:
        text, requests = parse_emphasis_markup(text)
        # 우선순위: 요청 지정 > 프로젝트 프리셋(config/power_shortcuts.json) > 내장 기본
        presets = req.power_shortcuts or load_default_power_shortcuts() or DEFAULT_STYLES
        config = req.emphasis_config or load_emphasis_config()
        requests = apply_density(text, requests, config)  # 밀도 규칙으로 과한 강조 솎기
        emphases = assign_emphasis(requests, presets, config)
        if req.postprocess:  # 강조 텍스트도 본문과 같은 문자 규칙으로 정규화(매칭 유지)
            span_originals = [span.text for span in emphases]
            for span in emphases:
                span.text = enforce_format(span.text, wrap=False, ornaments=ornaments)

    if req.postprocess:
        text = enforce_format(text, allow_checklist=is_product, ornaments=ornaments)
        # 본문 쪽이 대괄호 보호로 원형(!/~)을 유지한 구간의 스팬은 정규화를 되돌려야
        # 게시 단계의 스팬-본문 매칭이 산다(스팬만 치환되면 강조가 조용히 탈락).
        for span, orig in zip(emphases, span_originals):
            if span.text != orig and span.text not in text and orig in text:
                span.text = orig

    # 노출 기본기(제목 길이·해시태그 개수)는 가이드라인 입력과 무관하게 항상 검사한다.
    checklist: list[CheckItem] = check_exposure(text)
    if req.guidelines and not req.guidelines.is_empty():
        photo_count = req.photo_count
        if photo_count is None and req.fact_card.photos:
            photo_count = len(req.fact_card.photos)
        checklist += check_guidelines(text, req.guidelines, photo_count)
    return DraftResult(text=text, checklist=checklist, emphases=emphases, debug=debug)
