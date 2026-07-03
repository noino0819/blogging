"""AI 썸네일(thumbnail.py) — 네트워크 없이 크롭·응답 파싱 로직만 검증."""

import base64
from io import BytesIO

import pytest
from PIL import Image

from autoblog.thumbnail import ThumbnailUnavailable, _decode_image, _square_png


def test_square_png_crops_to_1_1(tmp_path):
    p = tmp_path / "wide.png"
    Image.new("RGB", (400, 200), "red").save(p)
    out = Image.open(BytesIO(_square_png(str(p), dim=128)))
    assert out.size == (128, 128)


def test_decode_image_both_response_shapes():
    raw = b"fake-png"
    b64 = base64.b64encode(raw).decode()
    assert _decode_image({"artifacts": [{"base64": b64}]}) == raw  # native
    assert _decode_image({"data": [{"b64_json": b64}]}) == raw  # OpenAI 호환


def test_decode_image_empty_raises():
    with pytest.raises(ThumbnailUnavailable):
        _decode_image({"artifacts": []})
