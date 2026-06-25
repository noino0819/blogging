from io import BytesIO

from PIL import Image

from autoblog.collect.fact_card import CardType, Source
from autoblog.collect.product import collect_product, parse_shop_item
from autoblog.vision import VisionUnavailable, _parse_specs, _split_tall_image

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
    # Vision 미연동(서버다운 등)이면 경고만 남기고 기본정보는 유지
    monkeypatch.setattr("autoblog.collect.product.search_product", lambda q, display=5: [parse_shop_item(SHOP_ITEM)])

    def _fail(paths, model=None):
        raise VisionUnavailable("ollama down")

    monkeypatch.setattr("autoblog.vision.extract_product_specs", _fail)
    card = collect_product("강아지 노즈워크", detail_images=["/tmp/detail1.jpg"])
    assert card.product.detail_images == ["/tmp/detail1.jpg"]
    assert card.product.specs == []
    assert any("Vision" in w for w in card.warnings)


def test_parse_specs():
    content = '{"specs":[{"key":"재질","value":"실리콘"},{"key":"크기","value":"20cm"},{"bad":1}]}'
    specs = _parse_specs(content)
    assert [(s.key, s.value) for s in specs] == [("재질", "실리콘"), ("크기", "20cm")]
    assert _parse_specs("not json") == []


def test_parse_specs_list_value():
    # 모델이 값을 배열로 줄 때 콤마로 합쳐 문자열화
    specs = _parse_specs('{"specs":[{"key":"구성","value":["당근 12개","매트 1개"]}]}')
    assert specs[0].key == "구성"
    assert specs[0].value == "당근 12개, 매트 1개"


def _png(w, h):
    buf = BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_split_tall_image(tmp_path):
    # 정사각형 → 1조각
    sq = tmp_path / "sq.png"
    sq.write_bytes(_png(400, 400))
    assert len(_split_tall_image(str(sq))) == 1
    # 매우 긴 이미지(가로400 세로2000, max_aspect=2 → 800px 타일 → 3조각) → 분할
    tall = tmp_path / "tall.png"
    tall.write_bytes(_png(400, 2000))
    assert len(_split_tall_image(str(tall))) == 3
