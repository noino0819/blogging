"""기본 베이스 프롬프트 로딩 (사용자 편집 가능).

config/prompts/default.md 를 시스템 프롬프트의 기본 베이스로 사용한다.
파일 상단의 메타 안내(제목 + 인용 블록, 첫 '---' 이전)는 모델에 보내지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from autoblog.config import CONFIG_DIR

DEFAULT_PROMPT_PATH = CONFIG_DIR / "prompts" / "default.md"


def load_base_prompt(path: str | Path | None = None) -> str:
    """베이스 프롬프트 텍스트 로드(상단 메타 안내 제거)."""
    text = Path(path or DEFAULT_PROMPT_PATH).read_text(encoding="utf-8")
    marker = "\n---\n"
    idx = text.find(marker)
    if idx != -1:
        text = text[idx + len(marker) :]
    return text.strip()
