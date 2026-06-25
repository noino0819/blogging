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


class ModelPreset(BaseModel):
    label: str
    vision: str
    text: str
    note: str = ""
    concurrent_load: bool = False


class ModelsConfig(BaseModel):
    presets: dict[str, ModelPreset]
    default: str

    def get(self, tier: str | None = None) -> ModelPreset:
        key = tier or self.default
        if key not in self.presets:
            raise KeyError(f"알 수 없는 프리셋: {key!r} (가능: {list(self.presets)})")
        return self.presets[key]


@lru_cache
def load_models_config(path: Path | None = None) -> ModelsConfig:
    path = path or CONFIG_DIR / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ModelsConfig(**data)


class Env(BaseModel):
    naver_client_id: str | None = None
    naver_client_secret: str | None = None
    ollama_host: str = "http://127.0.0.1:11434"

    @property
    def has_naver_api(self) -> bool:
        return bool(self.naver_client_id and self.naver_client_secret)


@lru_cache
def load_env() -> Env:
    return Env(
        naver_client_id=os.getenv("NAVER_CLIENT_ID"),
        naver_client_secret=os.getenv("NAVER_CLIENT_SECRET"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
