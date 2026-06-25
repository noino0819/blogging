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
    plan = build_publish_plan(draft, photos=card.photos, picker=picker)
    return PipelineResult(card=card, draft=draft, plan=plan)
