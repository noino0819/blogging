"""AI 썸네일 — 대표사진을 Qwen-Image-Edit(NVIDIA 호스티드 API)로 손그림 감성 썸네일로.

드로잉·텍스트 규칙은 config/prompts/thumbnail.md(직접 편집 가능)에서 읽고,
타이틀(가게/제품 이름)을 프롬프트 앞에 끼워 넣는다. 입력 사진은 중앙 1:1 크롭 후
전송해 출력도 1:1(블로그 대표사진 비율)이 되게 한다. NVIDIA_API_KEY 필요(build.nvidia.com).
"""

from __future__ import annotations

import base64
import json
from io import BytesIO

from autoblog.config import CONFIG_DIR, load_env

PROMPT_PATH = CONFIG_DIR / "prompts" / "thumbnail.md"

# ponytail: 호스티드 엔드포인트를 순서대로 시도(네이티브 genai → OpenAI 호환).
# build.nvidia.com 예제 스니펫이 바뀌면 이 목록만 고치면 된다.
_ENDPOINTS = (
    ("https://ai.api.nvidia.com/v1/genai/qwen/qwen-image-edit", "native"),
    ("https://integrate.api.nvidia.com/v1/images/edits", "openai"),
)
_MODEL = "qwen/qwen-image-edit"


class ThumbnailUnavailable(RuntimeError):
    """키 미설정·API 오류 등으로 썸네일을 만들 수 없을 때."""


def load_thumbnail_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _square_png(path: str, dim: int = 1024) -> bytes:
    """중앙 1:1 크롭 + 리사이즈 → PNG bytes. 입력이 1:1이면 출력도 1:1로 나온다."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((dim, dim))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _decode_image(data: dict) -> bytes:
    """응답 JSON → 이미지 bytes. native(artifacts[].base64)·OpenAI(data[].b64_json) 모두 지원."""
    items = data.get("artifacts") or data.get("data") or []
    for it in items:
        if not isinstance(it, dict):
            continue
        b64 = it.get("base64") or it.get("b64_json")
        if b64:
            return base64.b64decode(b64)
    raise ThumbnailUnavailable("응답에 이미지가 없어요: " + json.dumps(data)[:200])


def generate_thumbnail(photo_path: str, title: str = "", extra: str = "") -> bytes:
    """대표사진 1장 + 타이틀 + 방향 요청(extra) → 손그림 감성 썸네일 PNG bytes."""
    import requests

    env = load_env()
    if not env.nvidia_api_key:
        raise ThumbnailUnavailable(
            "NVIDIA_API_KEY 미설정 — build.nvidia.com에서 발급해 모델 탭에 저장하세요"
        )
    prompt = load_thumbnail_prompt()
    if title:
        prompt = f"타이틀(제품이름): {title}\n\n{prompt}"
    if extra:  # 유저가 적은 방향(분위기·포인트 색·문구)은 기본 규칙보다 우선
        prompt = f"{prompt}\n\n[추가 요청 — 아래 내용을 우선 반영]\n{extra}"
    data_url = "data:image/png;base64," + base64.b64encode(_square_png(photo_path)).decode()
    headers = {"Authorization": f"Bearer {env.nvidia_api_key}", "Accept": "application/json"}
    for url, kind in _ENDPOINTS:
        payload: dict = {"prompt": prompt, "image": data_url}
        if kind == "openai":
            payload.update({"model": _MODEL, "n": 1, "response_format": "b64_json"})
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        if resp.status_code == 404:
            continue  # 이 형식의 엔드포인트가 아님 — 다음 후보 시도
        if not resp.ok:
            raise ThumbnailUnavailable(f"NVIDIA API 오류 {resp.status_code}: {resp.text[:300]}")
        return _decode_image(resp.json())
    raise ThumbnailUnavailable("NVIDIA API에서 qwen-image-edit 엔드포인트를 찾지 못했어요")
