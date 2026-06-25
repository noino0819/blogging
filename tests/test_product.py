import pytest

from autoblog.collect.fact_card import CardType, Source
from autoblog.collect.product import collect_product, parse_shop_item
from autoblog.vision import VisionUnavailable, extract_product_specs

# 쇼핑 검색 API 실응답 형태 (라이브 캡처 기반)
SHOP_ITEM = {
    "title": "<b>강아지</b> <b>노즈워크</b> 장난감 분리불안 훈련 노즈볼",
    "link": "https://smartstore.naver.com/main/products/2370335571",
    "image": "https://shopping-phinf.pstatic.net/main_1302551/13025510058.28.jpg",
    "lprice": "19900",
    "hprice": "",
    "mallName": "펫프닝",
    "productId": "13025510058",
    "brand": "노즈워크",
    "maker": "",
    "category1": "생활/건강",
    "category2": "반려동물",
    "category3": "강아지 장난감/훈련",
    "category4": "노즈워크",
}


def test_parse_shop_item():
    facts = parse_shop_item(SHOP_ITEM)
    assert facts.name == "강아지 노즈워크 장난감 분리불안 훈련 노즈볼"  # <b> 제거
    assert facts.price == "19,900원"
    assert facts.brand == "노즈워크"
    assert facts.maker is None  # 빈 문자열 → None
    assert facts.category == "생활/건강>반려동물>강아지 장난감/훈련>노즈워크"
    assert facts.mall_name == "펫프닝"
    assert facts.image.startswith("https://")


def test_collect_product_basics(monkeypatch):
    monkeypatch.setattr("autoblog.collect.product.search_product", lambda q, display=5: [parse_shop_item(SHOP_ITEM)])
    card = collect_product("강아지 노즈워크")
    assert card.type == CardType.product
    assert Source.search_api in card.sources
    assert card.product.name.startswith("강아지")
    assert not card.is_fallback


def test_collect_product_vision_unavailable(monkeypatch):
    # 이미지가 있어도 Vision 미연동이면 경고만 남기고 기본정보는 유지
    monkeypatch.setattr("autoblog.collect.product.search_product", lambda q, display=5: [parse_shop_item(SHOP_ITEM)])
    card = collect_product("강아지 노즈워크", detail_images=["/tmp/detail1.jpg"])
    assert card.product.detail_images == ["/tmp/detail1.jpg"]
    assert card.product.specs == []
    assert any("Vision" in w for w in card.warnings)


def test_vision_stub_raises():
    with pytest.raises(VisionUnavailable):
        extract_product_specs(["/tmp/x.jpg"])
