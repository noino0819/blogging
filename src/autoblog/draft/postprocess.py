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
# 베이스 프롬프트가 금지한 흔한 감정형/장식 이모지(허용 목록 밖)
_FORBIDDEN_EMOJI = "💖💕❤️🔥😍🤤😋💯😊😄😁🥰😘🤩🥳😆👏🙌💪🍀🌟💫🤗😅😂🤣"
# 물결표(~)를 포함한 허용 이모지 — 치환 전 보호한다
_TILDE_EMOJI = "(๑´~ˋ๑)"
_TILDE_SENTINEL = "TILDE_EMOJI"
# 금지 표현 → 완화 표현
_FORBIDDEN_PHRASES = {
    "강력 추천": "추천",
    "강력추천": "추천",
    "강력히 추천": "추천",
    "꼭 가보세요": "한 번 가보셔도 좋을 것 같아요",
    "꼭 가보시길": "가보셔도 좋을 것 같아요",
}

# 줄바꿈: 절 경계로 쓰는 연결어미(이 뒤에서 끊는다)
_CONNECTIVE_RE = re.compile(
    r"(거든요|더라구요|더라고요|는데요|은데요|인데요|지만|는데|어서|아서|면서|으며|니까|라서|구요|고요)(\s+)"
)


def _greedy_wrap(segment: str, max_len: int) -> list[str]:
    """어절(공백) 단위 그리디 줄바꿈.

    짧은 어절(의존명사·단위·조사 결합형, 길이 ≤2: '수','것','원에','시에' 등)이
    줄 맨 앞에 오면 앞말과 분리돼 어색하므로, 그런 어절은 길이를 조금 넘겨도 붙인다.
    """
    out: list[str] = []
    cur = ""
    for word in segment.split(" "):
        too_long = cur and len(cur) + 1 + len(word) > max_len
        if too_long and len(word) > 2:  # 짧은 어절은 끊지 않고 붙임
            out.append(cur)
            cur = word
        else:
            cur = word if not cur else f"{cur} {word}"
    if cur:
        out.append(cur)
    return out


def _wrap_line(line: str, max_len: int) -> list[str]:
    """긴 한 줄을 쉼표·연결어미·공백 기준으로 짧은 절로 분할."""
    if len(line) <= max_len:
        return [line]
    # 쉼표 뒤, 연결어미 뒤에서 1차 분할
    marked = re.sub(r"([,，])\s*", r"\1\n", line)
    marked = _CONNECTIVE_RE.sub(lambda m: m.group(1) + "\n", marked)
    pieces: list[str] = []
    for clause in marked.split("\n"):
        clause = clause.strip()
        if not clause:
            continue
        if len(clause) > max_len:
            pieces.extend(_greedy_wrap(clause, max_len))
        else:
            pieces.append(clause)
    return pieces


def wrap_long_lines(text: str, max_len: int = 30) -> str:
    """긴 줄을 짧은 절 단위로 줄바꿈(SNS 스타일). 빈 줄(문단 간격)은 보존."""
    out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out.append("")
        else:
            out.extend(_wrap_line(line, max_len))
    return "\n".join(out)


def enforce_format(text: str, wrap: bool = True, max_len: int = 30) -> str:
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
    for bad, good in _FORBIDDEN_PHRASES.items():  # 금지 표현 완화
        text = text.replace(bad, good)
    if wrap:
        text = wrap_long_lines(text, max_len)
    # 치환으로 생긴 줄 끝 공백 / 과도한 빈 줄 정리
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
