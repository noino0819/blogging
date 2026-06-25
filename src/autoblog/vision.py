"""Vision LLM 연동 (기획서 §3.2, §5).

이미지형 상품 상세설명/사진을 로컬 Vision 모델(Ollama)로 이해해 구조화한다.
일반 OCR(Tesseract) 대신 Vision LLM을 쓰는 이유: 이미지 맥락을 이해해
재질·크기·사용법·주의사항 등으로 정리하기 위함.

모델명은 코드에 박지 않고 config/models.yaml(프리셋 vision)에서 읽는다.
세로로 긴 상세 이미지는 조각으로 분할해 OCR 품질을 높인 뒤 결과를 합친다.
"""

from __future__ import annotations

import base64
import json

import requests
from pydantic import BaseModel

from autoblog.collect.fact_card import ProductSpec
from autoblog.config import load_env, load_models_config


class VisionUnavailable(RuntimeError):
    """Vision 모델이 연동되지 않았거나(미설치/서버다운) 사용할 수 없을 때."""


def default_vision_model() -> str:
    """현재 적용된 vision 모델명(독립 선택 우선)."""
    return load_models_config().effective().vision


def _encode_image(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _split_tall_image(path: str, max_aspect: float = 2.0) -> list[bytes]:
    """세로로 긴 이미지를 가로폭 기준 조각으로 분할 → 각 조각 PNG bytes.

    상세설명 이미지는 보통 매우 길어(세로 수천 px) 모델 입력 해상도에서
    글자가 뭉개진다. height/width > max_aspect면 max_aspect 비율 높이로 자른다.
    """
    from io import BytesIO

    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    if h <= w * max_aspect:
        buf = BytesIO()
        img.save(buf, format="PNG")
        return [buf.getvalue()]

    tile_h = int(w * max_aspect)
    tiles: list[bytes] = []
    for top in range(0, h, tile_h):
        crop = img.crop((0, top, w, min(top + tile_h, h)))
        buf = BytesIO()
        crop.save(buf, format="PNG")
        tiles.append(buf.getvalue())
    return tiles


def _ollama_vision(prompt: str, images: list[bytes], model: str) -> str:
    """Ollama chat API에 이미지+프롬프트 → 응답 텍스트(JSON 강제)."""
    env = load_env()
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [_encode_image(b) for b in images],
            }
        ],
    }
    try:
        resp = requests.post(f"{env.ollama_host}/api/chat", json=payload, timeout=300)
    except requests.RequestException as exc:
        raise VisionUnavailable(f"Ollama 연결 실패({env.ollama_host}): {exc}") from exc
    if resp.status_code == 404:
        raise VisionUnavailable(f"모델 미설치: {model} (ollama pull {model})")
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


class ProductDetail(BaseModel):
    """상세 이미지 Vision 추출 결과."""

    text: str = ""  # 이미지에 적힌 문구 전사(마케팅 카피·후기 포함)
    selling_points: list[str] = []  # 핵심 셀링포인트/특징
    specs: list[ProductSpec] = []  # 재질/크기 등 스펙(있을 때만)


_DETAIL_PROMPT = (
    "이 상품 상세설명 이미지를 분석해 JSON으로만 답하세요. 형식:\n"
    '{"text":"이미지에 적힌 한국어 문구를 빠짐없이 그대로 전사",'
    '"selling_points":["핵심 셀링포인트/특징을 짧게"],'
    '"specs":[{"key":"재질","value":"..."}]}\n'
    "text에는 마케팅 카피·후기·문구를 그대로 옮기고, specs는 재질·크기·구성·사용법·"
    "주의사항·원산지 등 사실 스펙이 명시된 경우만 채우세요. 없으면 빈 배열. 추측 금지."
)


def _detail_prompt(context: str | None) -> str:
    if not context:
        return _DETAIL_PROMPT
    return f"참고 상품명/분류: {context}. 이 맥락에 맞춰 해석하세요.\n" + _DETAIL_PROMPT


def extract_product_detail(
    image_paths: list[str], model: str | None = None, context: str | None = None
) -> ProductDetail:
    """이미지형 상세설명 → 전사 텍스트 + 셀링포인트 + 스펙.

    context: 상품명/카테고리. 모델이 이미지를 오인식하지 않도록 함께 제공한다.
    긴 이미지는 분할해 조각별로 처리하고, 텍스트는 이어붙이고 포인트/스펙은 중복 제거 병합.
    """
    model = model or default_vision_model()
    prompt = _detail_prompt(context)
    texts: list[str] = []
    points: list[str] = []
    specs: dict[str, str] = {}
    for path in image_paths:
        for tile in _split_tall_image(path):
            detail = _parse_detail(_ollama_vision(prompt, [tile], model))
            if detail.text:
                texts.append(detail.text)
            for pt in detail.selling_points:
                if pt and pt not in points:
                    points.append(pt)
            for spec in detail.specs:
                if spec.key not in specs:
                    specs[spec.key] = spec.value
    return ProductDetail(
        text="\n".join(texts),
        selling_points=points,
        specs=[ProductSpec(key=k, value=v) for k, v in specs.items()],
    )


def _parse_detail(content: str) -> ProductDetail:
    """모델 JSON 응답 → ProductDetail(안전 파싱)."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return ProductDetail()
    if not isinstance(data, dict):
        return ProductDetail()
    text = data.get("text")
    points = data.get("selling_points")
    return ProductDetail(
        text=str(text).strip() if isinstance(text, str) else "",
        selling_points=[str(p).strip() for p in points if p] if isinstance(points, list) else [],
        specs=_parse_specs(data.get("specs")),
    )


def _parse_specs(items) -> list[ProductSpec]:
    """specs 배열 → ProductSpec 목록(값이 리스트면 콤마로 합침)."""
    if not isinstance(items, list):
        return []
    out: list[ProductSpec] = []
    for it in items:
        if isinstance(it, dict) and it.get("key") and it.get("value"):
            value = it["value"]
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            out.append(ProductSpec(key=str(it["key"]), value=str(value).strip()))
    return out


def classify_photos(
    image_paths: list[str], model: str | None = None
) -> dict[str, str]:
    """입력 사진 자동 분류 → {이미지경로: 분류라벨}.

    라벨 예: 음식, 메뉴판, 외관, 내부, 영수증, 상품, 기타.
    """
    model = model or default_vision_model()
    labels = ["음식", "메뉴판", "외관", "내부", "영수증", "상품", "기타"]
    prompt = (
        "이 사진을 다음 중 하나로 분류해 JSON으로만 답하세요: "
        f"{', '.join(labels)}. 형식: " + '{"label":"음식"}'
    )
    result: dict[str, str] = {}
    for path in image_paths:
        content = _ollama_vision(prompt, _split_tall_image(path), model)
        try:
            label = json.loads(content).get("label", "기타")
        except json.JSONDecodeError:
            label = "기타"
        result[path] = label if label in labels else "기타"
    return result
