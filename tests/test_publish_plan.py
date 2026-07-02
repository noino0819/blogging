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


def test_build_plan_video_marker_matches_only_video():
    # [사진]은 영상을 집지 않고, [영상]은 영상만 집는다(media_kind로 분리)
    draft = DraftResult(text="제목\n\n매장 외관.\n[사진]\n분위기 영상.\n[영상]")
    photos = [
        PhotoItem(path="ext.jpg", label="외관", media_kind="image"),
        PhotoItem(path="clip.mp4", label="기타", media_kind="video"),
    ]
    plan = build_publish_plan(draft, photos)
    kinds = [b.kind for b in plan.blocks]
    assert kinds == ["text", "image", "text", "video"]
    assert plan.blocks[1].image_path == "ext.jpg"
    assert plan.blocks[3].kind == "video" and plan.blocks[3].image_path == "clip.mp4"


def test_build_plan_video_label_used_as_block_label():
    # 캡션이 있으면 영상 블록 라벨(=업로더 제목)로 쓰인다
    draft = DraftResult(text="제목\n\n본문.\n[영상]")
    photos = [PhotoItem(path="clip.mp4", caption="조리 과정", media_kind="video")]
    plan = build_publish_plan(draft, photos)
    vid = next(b for b in plan.blocks if b.kind == "video")
    assert vid.image_label == "조리 과정"


def test_build_plan_leftover_video_spread_as_video_block():
    # [영상] 마커가 없어도 남은 영상은 본문에 분산되며 kind='video'로 생성(image로 새지 않음)
    draft = DraftResult(text="제목\n\n첫 문단.\n[구분선]\n둘째 문단.")
    photos = [
        PhotoItem(path="a.jpg", label="외관", media_kind="image"),
        PhotoItem(path="v.mp4", label="기타", media_kind="video"),
    ]
    plan = build_publish_plan(draft, photos)
    kinds = [b.kind for b in plan.blocks]
    assert kinds == ["text", "image", "divider", "text", "video"]
    assert plan.blocks[4].image_path == "v.mp4"


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
    assert quote.align == "center"  # 말풍선(3)은 가운데정렬
    # 텍스트 블록은 구분선/인용구 기준으로 분리
    texts = [b.text for b in plan.blocks if b.kind == "text"]
    assert "첫 문단이에요." in texts and "마지막 문단." in texts


def test_quote_align_follows_variant():
    # 왼쪽줄(2)·밑줄형(4)은 에디터 기본이 왼쪽정렬 → align 없음. 나머지는 가운데정렬.
    for variant, expected in ((1, "center"), (2, None), (3, "center"),
                              (4, None), (5, "center"), (6, "center")):
        plan = build_publish_plan(
            DraftResult(text=f"제목\n\n글\n[인용구:{variant}]\n한마디\n[/인용구]")
        )
        quote = next(b for b in plan.blocks if b.kind == "quote")
        assert quote.align == expected, f"variant={variant}"


def test_build_plan_divider_variant():
    plan = build_publish_plan(DraftResult(text="제목\n\n글\n[구분선:5]\n끝"))
    div = next(b for b in plan.blocks if b.kind == "divider")
    assert div.variant == 5


def test_build_plan_sticker_marker_resolved():
    from autoblog.publish.stickers import Sticker, StickerCatalog, StickerPicker

    cat = StickerCatalog(
        stickers=[Sticker(pack="ogq_a", index=3, tags=["맛있음"])], favorites=["ogq_a:3"]
    )
    picker = StickerPicker(cat)  # 즐겨찾기-온리 기본 → 즐겨찾기한 스티커만 게시에 쓰임
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


def _filler_picker():
    from autoblog.publish.stickers import Sticker, StickerCatalog, StickerPicker

    cat = StickerCatalog(
        stickers=[
            Sticker(pack="ogq_a", index=1, tags=["기쁨"]),
            Sticker(pack="ogq_a", index=2, tags=["신남"]),
        ],
        favorites=["ogq_a:1", "ogq_a:2"],
    )
    return StickerPicker(cat)


def test_bare_text_gets_filler_sticker():
    # 옵션(기본 꺼짐)을 켜면: 사진이 앞에 몰려 뒤쪽 문단이 텍스트만 남으면 그 끝에 이모티콘을 채운다.
    # 사진 2장을 앞에서 다 쓰고, 뒤 두 섹션(구분선으로 나뉜 텍스트)은 사진이 없다.
    draft = DraftResult(text="제목\n\n인트로.\n[사진]\n[사진]\n[구분선]\n둘째 섹션.\n[구분선]\n셋째 섹션.")
    photos = [PhotoItem(path="a.jpg", label="음식"), PhotoItem(path="b.jpg", label="음식")]
    plan = build_publish_plan(draft, photos, picker=_filler_picker(), bare_text_sticker=True)
    kinds = [b.kind for b in plan.blocks]
    # 사진 배치·순서는 그대로, 사진 없는 뒤쪽 텍스트 문단에만 스티커가 붙는다
    assert [b.image_path for b in plan.blocks if b.kind == "image"] == ["a.jpg", "b.jpg"]
    assert kinds.count("sticker") >= 1
    # 스티커는 항상 텍스트 문단 바로 뒤에 오고, 사진 옆에는 끼지 않는다
    for i, b in enumerate(plan.blocks):
        if b.kind == "sticker":
            assert plan.blocks[i - 1].kind == "text"


def test_bare_text_skips_header_and_photo_adjacent():
    # 첫 사진 앞(인트로)과 사진에 붙은 문단에는 스티커를 넣지 않는다
    draft = DraftResult(text="제목\n\n인트로 문단.\n[사진]\n사진 옆 문단.")
    photos = [PhotoItem(path="a.jpg", label="음식")]
    plan = build_publish_plan(draft, photos, picker=_filler_picker(), bare_text_sticker=True)
    # 인트로(첫 사진 앞)·사진 바로 뒤 문단 모두 사진과 붙어 있어 스티커 없음
    assert all(b.kind != "sticker" for b in plan.blocks)
    assert [b.kind for b in plan.blocks] == ["text", "image", "text"]


def test_bare_text_no_sticker_without_picker():
    # picker가 없으면(스티커 미설정) 아무것도 넣지 않는다
    draft = DraftResult(text="제목\n\n인트로.\n[사진]\n[구분선]\n뒤 문단.")
    photos = [PhotoItem(path="a.jpg", label="음식")]
    plan = build_publish_plan(draft, photos)  # picker 없음
    assert all(b.kind != "sticker" for b in plan.blocks)


def test_bare_text_disabled():
    # bare_text_sticker=False면 채우지 않는다
    draft = DraftResult(text="제목\n\n인트로.\n[사진]\n[구분선]\n뒤 문단.")
    photos = [PhotoItem(path="a.jpg", label="음식")]
    plan = build_publish_plan(draft, photos, picker=_filler_picker(), bare_text_sticker=False)
    assert all(b.kind != "sticker" for b in plan.blocks)


def test_bare_text_skipped_when_no_photos():
    # 옵션을 켜도, 사진이 아예 없는 글은 대상 아님(허전한 문단 채우기 안 함)
    draft = DraftResult(text="제목\n\n첫 문단.\n[구분선]\n둘째 문단.")
    plan = build_publish_plan(draft, picker=_filler_picker(), bare_text_sticker=True)
    assert all(b.kind != "sticker" for b in plan.blocks)


def _structure_styles():
    return StructureStyles(
        big_title=RoleStyle(font="nanummaruburi", size=30, color="#395D73"),
        subheading=RoleStyle(font="nanumuriddalsongeulssi", size=19, color="#EB7D7D"),
        hashtags=HashtagStyle(font="system", size=11, color="#4383BF", per_line=2, divider="line3"),
    )


def test_structure_styles_header_and_subheading():
    draft = DraftResult(
        text=(
            "혜화 치즈철판카츠 메종아카이\n"
            "친구랑 주말 대학로 데이트 코스\n"
            "혜화맛집 #대학로맛집 #혜화내돈내산 #메종아카이\n\n"
            "인트로 한 줄.\n\n"
            "1. 치즈철판카츠 후기\n"
            "겉은 바삭 속은 촉촉."
        )
    )
    plan = build_publish_plan(draft, structure_styles=_structure_styles())

    # 첫 줄은 제목칸, 본문 대제목은 별도(마루부리30). 13자라 균형 있게 두 줄로 접히고
    # 두 줄 각각 같은 대제목 서식 span이 붙는다.
    assert plan.title == "혜화 치즈철판카츠 메종아카이"
    big = next(b for b in plan.blocks if b.text.replace("\n", " ") == "친구랑 주말 대학로 데이트 코스")
    assert big.text == "친구랑 주말\n대학로 데이트 코스"
    assert len(big.emphases) == 2
    assert all(sp.style.font_family == "nanummaruburi" for sp in big.emphases)
    assert all(sp.style.font_size == "30" for sp in big.emphases)
    assert all(sp.style.text_color == "#395D73" for sp in big.emphases)

    # 해시태그는 2개씩 줄바꿈 + 줄마다 span, 바로 뒤에 가운데 꺾인 선(variant 4)
    tag_block = next(b for b in plan.blocks if "#대학로맛집" in b.text)
    assert tag_block.text == "혜화맛집 #대학로맛집\n#혜화내돈내산 #메종아카이"
    assert len(tag_block.emphases) == 2
    idx = plan.blocks.index(tag_block)
    assert plan.blocks[idx + 1].kind == "divider" and plan.blocks[idx + 1].variant == 4

    # 소제목("1. ...")은 인용구 밑줄형 블록으로 렌더(텍스트 "1. " 자동 번호목록 누수 회피)
    from autoblog.publish.plan import QUOTE_META

    sub = next(b for b in plan.blocks if b.text == "1. 치즈철판카츠 후기")
    assert sub.kind == "quote"
    assert sub.variant == QUOTE_META["quotation_underline"][0]


def test_structure_styles_off_by_default():
    # structure_styles 미지정이면 기존 동작 그대로(대제목 서식 부여 안 함)
    draft = DraftResult(text="제목\n\n짧은 첫 줄\n다음 줄")
    plan = build_publish_plan(draft)
    assert all(not b.emphases for b in plan.blocks if b.kind == "text")


def test_balance_wrap_splits_long_big_title_evenly():
    from autoblog.publish.plan import balance_wrap

    assert balance_wrap("달콤함은 그대로 칼로리는 가볍게") == "달콤함은 그대로\n칼로리는 가볍게"
    # 위/아래 글자 수(공백 제외) 차이가 최소가 되는 어절 경계에서 나뉜다
    top, bot = balance_wrap("바삭바삭 멈출 수 없는 인생 간식").split("\n")
    assert abs(len(top.replace(" ", "")) - len(bot.replace(" ", ""))) <= 1


def test_balance_wrap_leaves_short_prewrapped_or_spaceless():
    from autoblog.publish.plan import balance_wrap

    assert balance_wrap("짧은 대제목") == "짧은 대제목"  # 공백 제외 10자 이하
    assert balance_wrap("이미\n나눈 대제목 길어도") == "이미\n나눈 대제목 길어도"  # 이미 줄바꿈됨
    assert balance_wrap("띄어쓰기없는아주긴한줄짜리대제목") == "띄어쓰기없는아주긴한줄짜리대제목"  # 나눌 공백 없음


def test_big_title_wrapped_with_per_line_spans():
    # 대제목이 길면 두 줄로 접히고, 줄마다 대제목 서식 span이 하나씩(두 줄 다 큰 글씨).
    draft = DraftResult(text="제목칸\n바삭바삭 멈출 수 없는 인생 간식\n본문 첫 문단.")
    plan = build_publish_plan(draft, structure_styles=_structure_styles())
    big = next(b for b in plan.blocks if "바삭바삭" in b.text)
    assert "\n" in big.text
    assert len(big.emphases) == big.text.count("\n") + 1
    assert all(sp.style.font_size == "30" for sp in big.emphases)


def test_sponsor_sticker_prepended_at_top():
    draft = DraftResult(text="제목\n\n본문 첫 줄.\n본문 둘째 줄.")
    ss = StructureStyles(sponsor_sticker="ogq_cp:7")

    # 토글 OFF면 안 들어감
    off = build_publish_plan(draft, structure_styles=ss, sponsor=False)
    assert all(b.kind != "sticker" for b in off.blocks)

    # 토글 ON이면 본문 맨 위 블록이 그 스티커
    on = build_publish_plan(draft, structure_styles=ss, sponsor=True)
    assert on.blocks[0].kind == "sticker"
    assert on.blocks[0].sticker_pack == "ogq_cp"
    assert on.blocks[0].sticker_index == 7

    # ref 형식이 어긋나거나 비면(카탈로그 없음) 토글 ON이어도 안 들어감
    bad = build_publish_plan(draft, structure_styles=StructureStyles(sponsor_sticker="없음"), sponsor=True)
    assert all(b.kind != "sticker" for b in bad.blocks)


def test_sponsor_sticker_resolved_by_tag():
    from autoblog.publish.stickers import Sticker, StickerCatalog

    draft = DraftResult(text="제목\n\n본문.")
    cat = StickerCatalog(stickers=[
        Sticker(pack="ogq_z", index=2, tags=["기쁨"]),
        Sticker(pack="ogq_p", index=5, tags=["파트너스"]),
    ])
    ss = StructureStyles(sponsor_sticker="파트너스")  # ref이 아니라 태그 이름

    on = build_publish_plan(draft, structure_styles=ss, sponsor=True, sticker_catalog=cat)
    assert on.blocks[0].kind == "sticker"
    assert (on.blocks[0].sticker_pack, on.blocks[0].sticker_index) == ("ogq_p", 5)

    # 없는 태그면 안 들어감
    miss = build_publish_plan(
        draft, structure_styles=StructureStyles(sponsor_sticker="없는태그"), sponsor=True, sticker_catalog=cat
    )
    assert all(b.kind != "sticker" for b in miss.blocks)


def test_sponsor_sticker_from_catalog_pick():
    # structure_styles에 수동 지정이 없으면 UI에서 고른 catalog.sponsor(ref)를 쓴다
    from autoblog.publish.stickers import Sticker, StickerCatalog

    draft = DraftResult(text="제목\n\n본문.")
    cat = StickerCatalog(
        stickers=[Sticker(pack="ogq_p", index=5, tags=["협찬"])], sponsor="ogq_p:5"
    )
    plan = build_publish_plan(
        draft, structure_styles=StructureStyles(), sponsor=True, sticker_catalog=cat
    )
    assert plan.blocks[0].kind == "sticker"
    assert (plan.blocks[0].sticker_pack, plan.blocks[0].sticker_index) == ("ogq_p", 5)


def test_sponsor_links_spread_in_middle():
    # 문단 사이 구분선이 있어야 텍스트 블록이 여러 개로 나뉜다(실제 글 구조)
    draft = DraftResult(text="제목\n\n첫째.\n[구분선]\n둘째.\n[구분선]\n셋째.\n[구분선]\n넷째.\n[구분선]\n다섯째.")
    links = ["https://coupa.ng/a", "https://coupa.ng/b", "https://coupa.ng/c"]
    plan = build_publish_plan(draft, sponsor_links=links)

    link_blocks = [b for b in plan.blocks if b.kind == "link"]
    assert [b.link_url for b in link_blocks] == links  # 순서·개수 보존

    # 중간중간: 첫 블록·마지막 블록은 본문(링크가 맨 위/맨 끝에 몰리지 않음)
    kinds = [b.kind for b in plan.blocks]
    assert kinds[0] == "text" and kinds[-1] == "text"

    # 공백/빈 줄은 무시
    p2 = build_publish_plan(draft, sponsor_links=["  ", "https://coupa.ng/x", ""])
    assert [b.link_url for b in p2.blocks if b.kind == "link"] == ["https://coupa.ng/x"]


def test_coupang_partners_link_no_raw_url_text():
    # 쿠팡파트너스 링크는 협찬 칸에 넣어도 생 URL 텍스트를 남기지 않는다(카드만).
    # 체험단 캠페인 URL은 크롤러 인식용으로 텍스트 줄을 남긴다.
    draft = DraftResult(text="제목\n\n첫째.\n[구분선]\n둘째.\n[구분선]\n셋째.")
    links = [
        "https://link.coupang.com/a/xyz",
        "https://coupa.ng/abc",
        "https://www.coupang.com/vp/products/123",
        "https://campaign.revu.net/cp/999",
    ]
    plan = build_publish_plan(draft, sponsor_links=links)
    keep = {b.link_url: b.keep_url_text for b in plan.blocks if b.kind == "link"}
    assert keep["https://link.coupang.com/a/xyz"] is False
    assert keep["https://coupa.ng/abc"] is False
    assert keep["https://www.coupang.com/vp/products/123"] is False
    assert keep["https://campaign.revu.net/cp/999"] is True

    # 비협찬 상품 링크는 기존대로 텍스트 줄 제거
    p3 = build_publish_plan(draft, product_links=["https://smartstore.naver.com/x/1"])
    assert all(b.keep_url_text is False for b in p3.blocks if b.kind == "link")


def test_selectors_ready():
    # 라이브 분석으로 핵심 셀렉터(제목/본문/저장/발행) 확정됨
    assert selectors_ready() is True
