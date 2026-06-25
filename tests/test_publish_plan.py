from autoblog.collect.fact_card import PhotoItem
from autoblog.draft.generate import DraftResult
from autoblog.publish.editor import selectors_ready
from autoblog.publish.emphasis import EmphasisStyle, StyledSpan
from autoblog.publish.plan import build_publish_plan


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


def test_build_plan_distributes_emphasis():
    span = StyledSpan(text="13,000원", preset_id=20, style=EmphasisStyle(text_color="#C2410C"))
    draft = DraftResult(text="제목\n\n추어탕은 13,000원이었어요.", emphases=[span])
    plan = build_publish_plan(draft)
    text_block = next(b for b in plan.blocks if b.kind == "text")
    assert text_block.emphases == [span]  # 해당 텍스트 블록에 배분


def test_build_plan_extra_photos_appended():
    draft = DraftResult(text="제목\n\n본문만 있고 사진 마커는 없음")
    photos = [PhotoItem(path="a.jpg", label="외관"), PhotoItem(path="b.jpg", label="음식")]
    plan = build_publish_plan(draft, photos)
    # [사진] 마커가 없으면 본문 뒤에 사진들이 첨부됨
    image_blocks = [b for b in plan.blocks if b.kind == "image"]
    assert [b.image_path for b in image_blocks] == ["a.jpg", "b.jpg"]


def test_selectors_ready():
    # 라이브 분석으로 핵심 셀렉터(제목/본문/저장/발행) 확정됨
    assert selectors_ready() is True
