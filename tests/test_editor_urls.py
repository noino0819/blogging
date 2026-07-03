"""_original_url_candidates — 에디터 축소본 src → 원본 화질 후보 순서."""

from autoblog.publish.editor import _original_url_candidates


def test_typed_thumbnail_tries_original_first():
    src = "https://postfiles.pstatic.net/MjAy/blog/banner.gif?type=w966"
    assert _original_url_candidates(src) == [
        "https://postfiles.pstatic.net/MjAy/blog/banner.gif",
        "https://postfiles.pstatic.net/MjAy/blog/banner.gif?type=w3840",
        src,
    ]


def test_no_query_src_stays_single():
    src = "https://blogfiles.pstatic.net/MjAy/blog/photo.jpg"
    cands = _original_url_candidates(src)
    assert cands[0] == src  # 이미 원본 — 그대로 1순위


def test_other_params_survive_type_removal():
    src = "https://postfiles.pstatic.net/a/b.png?abc=1&type=w773"
    assert _original_url_candidates(src)[0] == "https://postfiles.pstatic.net/a/b.png?abc=1"
