"""엔드투엔드 오케스트레이션: 수집 → 초안(마커 자동) → 게시 플랜 (기획서 §7 통합).

CLI `post` 명령이 이 흐름을 호출한다. 게시(BlogPublisher)는 부수효과(브라우저)라 분리:
여기서는 사실카드·초안·게시플랜까지 조립하고, 실제 주입/발행은 CLI에서 BlogPublisher가 맡는다.

스티커 배선: stickers=True면 카탈로그의 상황 라벨을 초안에 주입(LLM이 [스티커:상황] emit)하고,
같은 카탈로그로 StickerPicker를 만들어 플랜이 마커를 (팩,인덱스)로 해석한다.
"""

from __future__ import annotations

from pydantic import BaseModel

from autoblog.collect.fact_card import CardType, FactCard
from autoblog.draft.generate import DraftRequest, DraftResult, generate_draft
from autoblog.draft.rules import CommonRules
from autoblog.draft.style import StyleProfile
from autoblog.publish.plan import PublishPlan, build_publish_plan
from autoblog.publish.stickers import StickerCatalog, StickerPicker


class PipelineResult(BaseModel):
    card: FactCard
    draft: DraftResult
    plan: PublishPlan


def collect_card(
    place_url: str | None = None,
    product: str | None = None,
    photos: list[str] | None = None,
) -> FactCard:
    """수집: 플레이스 URL 또는 상품 검색어 → 사실 카드. 사진 있으면 분류해 카드에 채움."""
    if place_url:
        from autoblog.collect.place import collect_place_from_url

        card = collect_place_from_url(place_url)
    elif product:
        from autoblog.collect.product import collect_product

        card = collect_product(product)
    else:
        card = FactCard(type=CardType.place)
    if photos:
        from autoblog.collect.photos import classify_photos_into

        classify_photos_into(card, photos)
    return card


def build_export_prompt(
    memo: str,
    *,
    card: FactCard | None = None,
    place_url: str | None = None,
    product: str | None = None,
    photos: list[str] | None = None,
    style: StyleProfile | None = None,
    rules: CommonRules | None = None,
    base_prompt: str | None = None,
    emphasis: bool = False,
    structure: bool = False,
    stickers: bool = False,
    sticker_catalog: StickerCatalog | None = None,
) -> str:
    """수집(선택)→프롬프트 조립까지만 하고, 다른 챗봇에 붙여넣을 단일 텍스트로 반환.

    run_pipeline과 동일한 지시문(강조/구조/스티커/규칙)을 넣되 LLM은 호출하지 않는다.
    system을 지시문으로, user를 입력 자료로 묶어 그대로 복사-붙여넣기 가능하게 만든다.
    """
    from autoblog.draft.generate import build_prompt

    if card is None:
        try:
            card = collect_card(place_url, product, photos)
        except Exception:  # noqa: BLE001 — 수집 실패해도 내보내기는 메모만으로 진행
            card = collect_card(photos=photos) if photos else FactCard(type=CardType.place)
    labels: list[str] = []
    if stickers:
        if sticker_catalog is None:
            from autoblog.publish.stickers import load_sticker_catalog

            sticker_catalog = load_sticker_catalog()
        labels = sticker_catalog.labels()
    req = DraftRequest(
        fact_card=card,
        experience_memo=memo,
        base_prompt=base_prompt,
        style=style,
        rules=rules,
        emphasis=emphasis,
        structure=structure,
        sticker_labels=labels,
    )
    system, user = build_prompt(req)
    return (
        "# 지시문 (이 규칙대로 블로그 글을 써줘)\n\n"
        f"{system}\n\n"
        "---\n\n"
        "# 입력 자료\n\n"
        f"{user}\n\n"
        "---\n\n"
        "위 지시문을 지켜서 네이버 블로그 글 본문을 완성해줘."
    )


def plan_from_text(
    text: str,
    *,
    photos: list[str] | None = None,
    emphasis: bool = False,
    structure: bool = False,
    stickers: bool = False,
    sticker_catalog: StickerCatalog | None = None,
    consistent_pack: bool = False,
    divider_variant: int = 1,
    quote_variant: int = 1,
) -> PipelineResult:
    """외부 챗봇에서 받아온 초안 텍스트 → 마커 파싱·후처리 → 게시 플랜.

    수집·LLM 호출 없이 run_pipeline의 후반부(초안→플랜)만 재현한다. 선택한 사진은
    플랜에 이미지 블록으로 배치된다.
    """
    catalog = None
    labels: list[str] = []
    if stickers:
        if sticker_catalog is None:
            from autoblog.publish.stickers import load_sticker_catalog

            sticker_catalog = load_sticker_catalog()
        catalog = sticker_catalog
        labels = catalog.labels()
    card = FactCard(type=CardType.place)
    if photos:
        from autoblog.collect.photos import classify_photos_into

        classify_photos_into(card, photos)
    req = DraftRequest(
        fact_card=card,
        experience_memo="",
        emphasis=emphasis,
        structure=structure,
        sticker_labels=labels,
    )
    draft = generate_draft(req, raw_override=text)
    picker = (
        StickerPicker(catalog, consistent=consistent_pack) if (catalog and labels) else None
    )
    plan = build_publish_plan(
        draft, photos=card.photos, picker=picker,
        divider_variant=divider_variant, quote_variant_default=quote_variant,
    )
    return PipelineResult(card=card, draft=draft, plan=plan)


def run_pipeline(
    memo: str,
    *,
    card: FactCard | None = None,
    place_url: str | None = None,
    product: str | None = None,
    photos: list[str] | None = None,
    style: StyleProfile | None = None,
    rules: CommonRules | None = None,
    base_prompt: str | None = None,
    emphasis: bool = False,
    structure: bool = False,
    stickers: bool = False,
    sticker_catalog: StickerCatalog | None = None,
    consistent_pack: bool = False,
    divider_variant: int = 1,
    quote_variant: int = 1,
    model: str | None = None,
) -> PipelineResult:
    """수집→초안(강조/구조/스티커 마커 자동)→게시 플랜까지 한 번에 조립.

    card를 직접 주면 수집을 건너뛴다(테스트/재사용). stickers=True면 카탈로그 라벨을
    초안에 주입하고 같은 카탈로그로 picker를 만들어 플랜에서 스티커를 해석한다.
    """
    if card is None:
        card = collect_card(place_url, product, photos)

    catalog = None
    labels: list[str] = []
    if stickers:
        if sticker_catalog is None:
            from autoblog.publish.stickers import load_sticker_catalog

            sticker_catalog = load_sticker_catalog()
        catalog = sticker_catalog
        labels = catalog.labels()

    req = DraftRequest(
        fact_card=card,
        experience_memo=memo,
        base_prompt=base_prompt,
        style=style,
        rules=rules,
        emphasis=emphasis,
        structure=structure,
        sticker_labels=labels,
    )
    draft = generate_draft(req, model=model)

    picker = (
        StickerPicker(catalog, consistent=consistent_pack) if (catalog and labels) else None
    )
    plan = build_publish_plan(
        draft, photos=card.photos, picker=picker,
        divider_variant=divider_variant, quote_variant_default=quote_variant,
    )
    return PipelineResult(card=card, draft=draft, plan=plan)
