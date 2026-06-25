"""포맷 후처리 — 결정적 규칙 강제 (기획서 §4.3 / stage 3).

모델이 베이스 프롬프트의 기계적 규칙을 어겨도 코드로 보정한다:
- 느낌표(!) → .ᐟ
- 물결표(~) → -
- 줄 앞 글머리 기호(•,*,▶,→,✓,✅,- ) 제거
- 마크다운 헤더(#) 마커 제거
- 명시적으로 금지된 흔한 이모지 제거
줄바꿈 스타일(한 줄 짧은 절) 등 의미 의존 규칙은 모델 몫으로 남긴다.
"""

from __future__ import annotations

import re

_HEADER_RE = re.compile(r"^[ \t]*#{1,6}[ \t]*", re.MULTILINE)
_BULLET_RE = re.compile(r"^[ \t]*[•*▶→✓✅][ \t]+", re.MULTILINE)
_DASH_BULLET_RE = re.compile(r"^[ \t]*-[ \t]+", re.MULTILINE)
# 베이스 프롬프트가 명시적으로 금지한 흔한 이모지(허용 목록 밖)
_FORBIDDEN_EMOJI = "💖💕❤️🔥😍🤤😋💯😊😄😁🥰😘"
# 물결표(~)를 포함한 허용 이모지 — 치환 전 보호한다
_TILDE_EMOJI = "(๑´~ˋ๑)"
_TILDE_SENTINEL = "TILDE_EMOJI"


def enforce_format(text: str) -> str:
    """결정적 포맷 규칙을 강제 적용."""
    text = _HEADER_RE.sub("", text)  # 마크다운 헤더 마커 제거
    text = _BULLET_RE.sub("", text)  # 글머리 기호 제거
    text = _DASH_BULLET_RE.sub("", text)  # 줄 앞 '- ' 제거
    text = text.replace("!", ".ᐟ")  # 느낌표 치환
    text = text.replace(_TILDE_EMOJI, _TILDE_SENTINEL)  # 허용 이모지 보호
    text = re.sub(r"~+", "-", text)  # 물결표 치환
    text = text.replace(_TILDE_SENTINEL, _TILDE_EMOJI)
    for ch in _FORBIDDEN_EMOJI:
        text = text.replace(ch, "")
    # 치환으로 생긴 줄 끝 공백 정리
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()
