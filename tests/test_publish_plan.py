from autoblog.collect.fact_card import PhotoItem
from autoblog.draft.generate import DraftResult
from autoblog.publish.editor import selectors_ready
from autoblog.publish.emphasis import EmphasisStyle, StyledSpan
from autoblog.publish.plan import (
    HashtagStyle,
    RoleStyle,
    StructureStyles,
    build_publish_plan,
)


def test_build_plan_title_and_blocks():
    draft = DraftResult(
        text="수지골 추어탕 후기\n\n비 오는 날 갔어요.\n[사진]\n추어탕이 진했어요.",
    )
    photos = [PhotoItem(path="food.jpg", label="음식")]
    plan = build_publish_plan(draft, photos)

    assert plan.title == "수지골 추어탕 후기"
    kinds = [b.kind for b in plan.blocks]
    assert kinds == ["text", "image", "text"]
    assert plan.blocks[1].image_path == "food.jpg"
    assert "비 오는 날" in plan.blocks[0].text
    assert "추어탕이 진했어요" in plan.blocks[2].text


def test_build_plan_photo_label_matching():
    # 외관 문단 뒤 [사진:외관], 음식 문단 뒤 [사진:음식] — 업로드 순서(음식 먼저)와 무관하게 라벨로 매칭
    draft = DraftResult(text="제목\n\n외관이 멋졌어요.\n[사진:외관]\n파스타가 맛있었어요.\n[사진:음식]")
    photos = [PhotoItem(path="food.jpg", label="음식"), PhotoItem(path="exterior.jpg", label="외관")]
    plan = build_publish_plan(draft, photos)
    imgs = [b for b in plan.blocks if b.kind == "image"]
    assert [b.image_path for b in imgs] == ["exterior.jpg", "food.jpg"]


def test_build_plan_photo_label_fallback_and_leftover():
    # 라벨 없는 [사진]은 남은 순서대로, 매칭 안 된 사진은 끝에 첨부
    draft = DraftResult(text="제목\n\n본문.\n[사진:메뉴판]\n다음.\n[사진]")
    photos = [PhotoItem(path="a.jpg", label="음식"), PhotoItem(path="b.jpg", label="외관")]
    plan = build_publish_plan(draft, photos)
    imgs = [b.image_path for b in plan.blocks if b.kind == "image"]
    # [사진:메뉴판] 매칭 실패 → 남은 첫 사진(a), [사진] → 남은 사진(b)
    assert imgs == ["a.jpg", "b.jpg"]


def test_build_plan_distributes_emphasis():
    span = StyledSpan(text="13,000원", preset_id=20, style=EmphasisStyle(text_color="#C2410C"))
    draft = DraftResult(text="제목\n\n추어탕은 13,000원이었어요.", emphases=[span])
    plan = build_publish_plan(draft)
    text_block = next(b for b in plan.blocks if b.kind == "text")
    assert text_block.emphases == [span]  # 해당 텍스트 블록에 배분


def test_build_plan_leftover_photos_spread_across_body():
    # 마커가 부족해도 남은 사진은 본문 텍스트 블록들 사이에 분산(끝에 몰지 않음)
    draft = DraftResult(text="제목\n\n첫 문단.\n[구분선]\n둘째 문단.")
    photos = [PhotoItem(path="a.jpg", label="외관"), PhotoItem(path="b.jpg", label="음식")]
    plan = build_publish_plan(draft, photos)
    kinds = [b.kind for b in plan.blocks]
    # 두 텍스트 블록 각각 뒤에 사진이 분산됨 (끝에 [..image, image]로 몰리지 않음)
    assert kinds == ["text", "image", "divider", "text", "image"]
    assert [b.image_path for b in plan.blocks if b.kind == "image"] == ["a.jpg", "b.jpg"]


def test_build_plan_leftover_photos_no_text_appended():
    # 본문 텍스트 블록이 없으면 남은 사진은 그대로 첨부
    draft = DraftResult(text="제목\n\n[구분선]")
    photos = [PhotoItem(path="a.jpg", label="외관")]
    plan = build_publish_plan(draft, photos)
    assert [b.image_path for b in plan.blocks if b.kind == "image"] == ["a.jpg"]


def test_build_plan_divider_and_quote():
    draft = DraftResult(text=(
        "제목\n\n첫 문단이에요.\n[구분선]\n[인용구:3]\n인상 깊은 한마디\n[/인용구]\n마지막 문단."
    ))
    plan = build_publish_plan(draft)
    kinds = [(b.kind, b.variant) for b in plan.blocks]
    assert ("divider", 1) in kinds
    quote = next(b for b in plan.blocks if b.kind == "quote")
    assert quote.variant == 3
    assert quote.text == "인상 깊은 한마디"
    # 텍스트 블록은 구분선/인용구 기준으로 분리
    texts = [b.text for b in plan.blocks if b.kind == "text"]
    assert "첫 문단이에요." in texts and "마지막 문단." in texts


def test_build_plan_divider_variant():
    plan = build_publish_plan(DraftResult(text="제목\n\n글\n[구분선:5]\n끝"))
    div = next(b for b in plan.blocks if b.kind == "divider")
    assert div.variant == 5


def test_build_plan_sticker_marker_resolved():
    from autoblog.publish.stickers import Sticker, StickerCatalog, StickerPicker

    cat = StickerCatalog(stickers=[Sticker(pack="ogq_a", index=3, tags=["맛있음"])])
    picker = StickerPicker(cat)
    draft = DraftResult(text="제목\n\n정말 맛있었어요.\n[스티커:맛있음]\n또 갈래요.")
    plan = build_publish_plan(draft, picker=picker)
    sticker = next(b for b in plan.blocks if b.kind == "sticker")
    assert sticker.sticker_pack == "ogq_a" and sticker.sticker_index == 3
    # 텍스트는 스티커 기준으로 분리
    texts = [b.text for b in plan.blocks if b.kind == "text"]
    assert "정말 맛있었어요." in texts and "또 갈래요." in texts


def test_build_plan_sticker_dropped_without_match():
    # picker 없거나 매칭 실패면 마커는 본문에 누수되지 않고 사라진다
    draft = DraftResult(text="제목\n\n본문\n[스티커:없음]\n끝")
    plan = build_publish_plan(draft)  # picker 없음
    assert all(b.kind != "sticker" for b in plan.blocks)
    assert all("[스티커" not in b.text for b in plan.blocks)


def _structure_styles():
    return StructureStyles(
        big_title=RoleStyle(font="nanummaruburi", size=30, color="#395D73"),
        subheading=RoleStyle(font="nanumuriddalsongeulssi", size=19, color="#EB7D7D"),
        byline=RoleStyle(font="nanumdasisijaghae", size=15, color="#607D8E"),
        hashtags=HashtagStyle(font="system", size=11, color="#4383BF", per_line=2, divider="line3"),
    )


def test_structure_styles_header_and_subheading():
    draft = DraftResult(
        text=(
            "혜화 치즈철판카츠 메종아카이\n"
            "친구랑 주말 대학로 데이트 코스\n"
            "with. 노이노\n"
            "혜화맛집 #대학로맛집 #혜화내돈내산 #메종아카이\n\n"
            "인트로 한 줄.\n\n"
            "1. 치즈철판카츠 후기\n"
            "겉은 바삭 속은 촉촉."
        )
    )
    plan = build_publish_plan(draft, structure_styles=_structure_styles())

    # 첫 줄은 제목칸, 본문 대제목은 별도(마루부리30)
    assert plan.title == "혜화 치즈철판카츠 메종아카이"
    big = next(b for b in plan.blocks if b.text == "친구랑 주말 대학로 데이트 코스")
    assert big.emphases[0].style.font_family == "nanummaruburi"
    assert big.emphases[0].style.font_size == "30"
    assert big.emphases[0].style.text_color == "#395D73"

    # with. 줄은 다시시작해15
    byline = next(b for b in plan.blocks if b.text == "with. 노이노")
    assert byline.emphases[0].style.font_family == "nanumdasisijaghae"

    # 해시태그는 2개씩 줄바꿈 + 줄마다 span, 바로 뒤에 가운데 꺾인 선(variant 4)
    tag_block = next(b for b in plan.blocks if "#대학로맛집" in b.text)
    assert tag_block.text == "혜화맛집 #대학로맛집\n#혜화내돈내산 #메종아카이"
    assert len(tag_block.emphases) == 2
    idx = plan.blocks.index(tag_block)
    assert plan.blocks[idx + 1].kind == "divider" and plan.blocks[idx + 1].variant == 4

    # 소제목 우리딸손글씨19
    sub = next(b for b in plan.blocks if b.text == "1. 치즈철판카츠 후기")
    assert sub.emphases[0].style.font_family == "nanumuriddalsongeulssi"
    assert sub.emphases[0].style.font_size == "19"


def test_structure_styles_off_by_default():
    # structure_styles 미지정이면 기존 동작 그대로(대제목 서식 부여 안 함)
    draft = DraftResult(text="제목\n\n짧은 첫 줄\n다음 줄")
    plan = build_publish_plan(draft)
    assert all(not b.emphases for b in plan.blocks if b.kind == "text")


def test_selectors_ready():
    # 라이브 분석으로 핵심 셀렉터(제목/본문/저장/발행) 확정됨
    assert selectors_ready() is True
