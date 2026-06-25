from autoblog.collect.link import LinkType, detect_link_type
from autoblog.collect.place import collect_place
from autoblog.config import load_models_config


def test_detect_link_type():
    assert detect_link_type("https://m.place.naver.com/restaurant/123") == LinkType.naver_place
    assert detect_link_type("https://smartstore.naver.com/foo/products/1") == LinkType.product
    assert detect_link_type("https://www.coupang.com/vp/products/1") == LinkType.product
    assert detect_link_type("https://blog.naver.com/someone/1") == LinkType.article
    assert detect_link_type("https://my-restaurant.com") == LinkType.homepage
    assert detect_link_type("not a url") == LinkType.unknown


def test_collect_place_fallback_without_api_key(monkeypatch):
    # API 키 없으면 fallback 카드를 반환해야 함
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    from autoblog import config

    config.load_env.cache_clear()
    card = collect_place("교대 김밥천국")
    assert card.is_fallback is True


def test_models_config_loads_presets():
    cfg = load_models_config()
    preset = cfg.get()  # default
    assert preset.vision
    assert preset.text
    assert "8gb" in cfg.presets
