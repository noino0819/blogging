"""설정 로딩 — 모델 프리셋, 환경변수.

모델명은 코드에 박지 않고 config/models.yaml에서 읽는다(기획서 §5).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

# 레포 루트 = 이 파일 기준 ../../.. (src/autoblog/config.py → repo)
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

load_dotenv(REPO_ROOT / ".env")


def provider_for_model(model: str) -> str:
    """모델명으로 텍스트 생성 제공자 판별. 그 외(로컬)는 'ollama'.

    라우팅의 단일 출처 — llm.provider_for도 이걸 쓴다.
    """
    m = (model or "").lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    return "ollama"


class ModelPreset(BaseModel):
    label: str
    vision: str
    text: str
    note: str = ""
    concurrent_load: bool = False
    # 텍스트 생성 라우팅: "ollama"(로컬) | "anthropic"(Claude) | "openai"(GPT) | "gemini"(Gemini)
    provider: str = "ollama"


class Selection(BaseModel):
    """사용자가 실제로 고른 모델 — 텍스트/비전 독립 선택. None이면 프리셋 폴백."""

    text: str | None = None
    vision: str | None = None


class ResolvedModels(BaseModel):
    """현재 실제로 쓰이는 모델 — 선택(selection) 우선, 없으면 기본 프리셋 폴백."""

    text: str
    vision: str
    provider: str  # 텍스트 제공자(model명에서 도출)
    concurrent_load: bool = False
    note: str = ""
    label: str = ""


class CaptionConfig(BaseModel):
    """사진 '✨ AI 자동 추천'(온디맨드 맥락 캡션) 멀티모달 모델. 비우면 자동 추천 비활성."""

    model: str = ""


class ModelsConfig(BaseModel):
    presets: dict[str, ModelPreset]
    default: str
    # 텍스트/비전을 프리셋과 무관하게 독립 선택(설정 시 프리셋보다 우선)
    selection: Selection = Selection()
    # 사진 자동 추천(온디맨드)에 쓰는 멀티모달 모델 — Gemini Flash 권장
    caption: CaptionConfig = CaptionConfig()

    def get(self, tier: str | None = None) -> ModelPreset:
        key = tier or self.default
        if key not in self.presets:
            raise KeyError(f"알 수 없는 프리셋: {key!r} (가능: {list(self.presets)})")
        return self.presets[key]

    def effective(self) -> ResolvedModels:
        """실제 적용되는 텍스트/비전 모델. selection이 있으면 그게 우선."""
        base = self.presets.get(self.default)
        text = self.selection.text or (base.text if base else "")
        vision = self.selection.vision or (base.vision if base else "")
        return ResolvedModels(
            text=text,
            vision=vision,
            provider=provider_for_model(text),
            concurrent_load=base.concurrent_load if base else False,
            note=base.note if base else "",
            label=base.label if base else "",
        )


@lru_cache
def load_models_config(path: Path | None = None) -> ModelsConfig:
    path = path or CONFIG_DIR / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ModelsConfig(**data)


class Env(BaseModel):
    naver_client_id: str | None = None
    naver_client_secret: str | None = None
    naver_blog_id: str | None = None  # 게시 대상 블로그 ID (한 번 받아 .env에 저장)
    ollama_host: str = "http://127.0.0.1:11434"
    anthropic_api_key: str | None = None  # Claude API 키(.env ANTHROPIC_API_KEY)
    openai_api_key: str | None = None  # OpenAI(GPT) API 키(.env OPENAI_API_KEY)
    gemini_api_key: str | None = None  # Google Gemini API 키(.env GEMINI_API_KEY)

    @property
    def has_naver_api(self) -> bool:
        return bool(self.naver_client_id and self.naver_client_secret)


@lru_cache
def load_env() -> Env:
    return Env(
        naver_client_id=os.getenv("NAVER_CLIENT_ID"),
        naver_client_secret=os.getenv("NAVER_CLIENT_SECRET"),
        naver_blog_id=os.getenv("NAVER_BLOG_ID"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
    )


def save_env_value(key: str, value: str, path: Path | None = None) -> None:
    """`.env`에 키=값을 추가/갱신(한 번 받은 설정을 영속화). 캐시도 무효화."""
    path = path or (REPO_ROOT / ".env")
    lines: list[str] = []
    found = False
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value
    load_env.cache_clear()


# 사진 카테고리 기본값(파일 없을 때 폴백). config/photo_categories.yaml 로 덮어쓸 수 있음.
DEFAULT_PHOTO_CATEGORIES: dict[str, list[str]] = {
    "place": ["음식", "메뉴판", "외관", "내부", "영수증", "협찬", "기타"],
    "product": ["제품컷", "상세페이지", "패키지", "사용샷", "협찬", "기타"],
}


@lru_cache
def load_photo_categories(path: Path | None = None) -> dict[str, list[str]]:
    """리뷰 타입별 사진 카테고리 프리셋(사용자 편집 파일). 없으면 기본값."""
    path = path or CONFIG_DIR / "photo_categories.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {k: list(v) for k, v in DEFAULT_PHOTO_CATEGORIES.items()}
    out: dict[str, list[str]] = {}
    if isinstance(data, dict):
        for key, vals in data.items():
            if isinstance(vals, list):
                out[str(key)] = [str(v).strip() for v in vals if str(v).strip()]
    return out or {k: list(v) for k, v in DEFAULT_PHOTO_CATEGORIES.items()}
