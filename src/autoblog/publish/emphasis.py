"""서식/강조 로직 (기획서 §6.1).

강조 스타일을 두 방식으로 배정한다:
- 순환 풀(돌려쓰기): 여러 스타일을 묶어 핵심 문장마다 번갈아 적용 → 리듬, 단조로움 방지.
  인덱스 순환이라 연속 중복을 자연히 회피한다.
- 고정 매핑(용도별): 특정 의미(가격·가게명 등)엔 항상 같은 스타일 → 일관성.

스타일 출처:
- 파워 단축키(크롬 확장)의 JSON export를 import → 1~24번 프리셋.
- 또는 프로그램 내장 기본 스타일(확장 없이 동작).
"""

from __future__ import annotations

import re

import yaml
from pydantic import BaseModel, Field

from autoblog.config import CONFIG_DIR


class EmphasisStyle(BaseModel):
    """글자색·배경·글꼴·크기 등 강조 스타일 한 개."""

    text_color: str | None = None  # "#E53935"
    background_color: str | None = None
    font_family: str | None = None
    font_size: str | None = None  # "16" 또는 "16px"
    bold: bool = False

    def is_empty(self) -> bool:
        return not any(
            [self.text_color, self.background_color, self.font_family, self.font_size, self.bold]
        )


# 파워 단축키 export에서 쓰일 법한 키 별칭(형식 변동 흡수)
_TEXT_KEYS = ("textColor", "text_color", "color", "fontColor")
_BG_KEYS = ("backgroundColor", "background_color", "bgColor", "bg")
_FONT_KEYS = ("fontFamily", "font_family", "font")
_SIZE_KEYS = ("fontSize", "font_size", "size")


def _first(d: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = d.get(k)
        if v:
            return str(v)
    return None


def parse_style(entry: dict) -> EmphasisStyle:
    """파워 단축키 항목 dict → EmphasisStyle (키 이름 변동에 관대)."""
    return EmphasisStyle(
        text_color=_first(entry, _TEXT_KEYS),
        background_color=_first(entry, _BG_KEYS),
        font_family=_first(entry, _FONT_KEYS),
        font_size=_first(entry, _SIZE_KEYS),
        bold=bool(entry.get("bold") or entry.get("fontWeight") == "bold"),
    )


def _is_flat_export(data) -> bool:
    """실제 파워 단축키 export(평면 suffix 형식)인지 판별."""
    return isinstance(data, dict) and any(
        k in data for k in ("hasInitialized", "textColor1", "actions1", "formatActions1")
    )


def _load_flat(data: dict, slots: int = 24) -> dict[int, EmphasisStyle]:
    """평면 형식(textColor1, actions1, editorMode1 …) → {번호: EmphasisStyle}.

    각 단축키의 활성 속성은 editorMode에 따라 formatActions/actions로 결정한다.
    값이 있어도 actions에 없으면 미적용(사용자가 끈 속성). insert 모드(인용/구분선)는 제외.
    """
    result: dict[int, EmphasisStyle] = {}
    for n in range(1, slots + 1):
        mode = data.get(f"editorMode{n}", "format")
        if mode == "insert":
            continue  # 삽입형(인용/구분선)은 텍스트 강조가 아님
        actions = set(data.get(f"formatActions{n}") or data.get(f"actions{n}") or [])
        size = data.get(f"fontSize{n}")
        style = EmphasisStyle(
            text_color=data.get(f"textColor{n}") if "textColor" in actions else None,
            background_color=(data.get(f"backgroundColor{n}") or None)
            if "backgroundColor" in actions
            else None,
            font_family=data.get(f"fontFamily{n}") if "fontFamily" in actions else None,
            font_size=str(size) if "fontSize" in actions and size else None,
        )
        if not style.is_empty():
            result[n] = style
    return result


def load_power_shortcuts(data) -> dict[int, EmphasisStyle]:
    """파워 단축키 JSON(export) → {단축키번호: EmphasisStyle}.

    실제 export는 평면 suffix 형식(textColor1, actions1, editorMode1 …).
    호환을 위해 list([{...}]) / dict({"1": {...}} / {"shortcuts": [...]}) 형식도 수용.
    """
    if _is_flat_export(data):
        return _load_flat(data)

    items: dict[int, dict] = {}
    if isinstance(data, dict) and "shortcuts" in data:
        data = data["shortcuts"]
    if isinstance(data, list):
        for i, entry in enumerate(data, start=1):
            if isinstance(entry, dict):
                num = int(entry.get("number") or entry.get("index") or i)
                items[num] = entry
    elif isinstance(data, dict):
        for k, entry in data.items():
            if isinstance(entry, dict) and str(k).isdigit():
                items[int(k)] = entry
    return {num: parse_style(entry) for num, entry in items.items()}


# 확장 프로그램 없이 동작하는 내장 기본 스타일
DEFAULT_STYLES: dict[int, EmphasisStyle] = {
    1: EmphasisStyle(text_color="#E53935"),  # 빨강
    2: EmphasisStyle(text_color="#1E88E5"),  # 파랑
    3: EmphasisStyle(background_color="#FFF59D"),  # 노란 형광
    4: EmphasisStyle(text_color="#43A047", bold=True),  # 초록 볼드
    5: EmphasisStyle(background_color="#FFCDD2"),  # 분홍 배경
    6: EmphasisStyle(text_color="#000000", bold=True),  # 검정 볼드
    7: EmphasisStyle(text_color="#FB8C00", bold=True),  # 주황 볼드(가격용)
}


class CyclingPool:
    """순환 풀 — preset_ids를 순서대로 돌려쓰며 연속 중복을 회피."""

    def __init__(self, preset_ids: list[int]):
        self.preset_ids = list(preset_ids)
        self._idx = 0
        self._last: int | None = None

    def next(self) -> int | None:
        if not self.preset_ids:
            return None
        pid = self.preset_ids[self._idx % len(self.preset_ids)]
        self._idx += 1
        # 풀 크기가 2 이상이면 인덱스 순환만으로 연속 중복이 없지만,
        # 직전과 같으면(중복 풀 등) 한 칸 더 진행해 회피한다.
        if pid == self._last and len(set(self.preset_ids)) > 1:
            pid = self.preset_ids[self._idx % len(self.preset_ids)]
            self._idx += 1
        self._last = pid
        return pid


class EmphasisConfig(BaseModel):
    """강조 배정 규칙 (사용자 입력 가능: config/emphasis.yaml)."""

    cycling_pool: list[int] = Field(default_factory=list)  # 예: [1, 3, 5]
    fixed_map: dict[str, int] = Field(default_factory=dict)  # 예: {"price": 7, "name": 4}
    max_per_paragraph: int | None = None  # (옵션) 문단당 강조 개수 상한
    min_sentence_gap: int | None = None  # (옵션) 강조 간 최소 문장 간격


_EMPHASIS_CONFIG_PATH = CONFIG_DIR / "emphasis.yaml"


def load_emphasis_config(path=None) -> EmphasisConfig:
    """강조 설정 로드(사용자 편집 파일). 없으면 빈 기본값."""
    path = path or _EMPHASIS_CONFIG_PATH
    try:
        data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except FileNotFoundError:
        return EmphasisConfig()
    return EmphasisConfig(**data)


# 초안 강조 마킹: <<role:강조할 텍스트>>  (예: <<price:13,000원>>, <<name:가게명>>, <<cycle:문장>>)
EMPHASIS_INSTRUCTION = (
    "[강조 표시]\n"
    "특별히 강조할 부분만 다음처럼 감싸세요. 일반 문장은 감싸지 마세요.\n"
    "- 핵심 문장·감상: <<cycle:문장>>\n"
    "- 가격: <<price:13,000원>>\n"
    "- 가게명/상품명: <<name:가게이름>>\n"
    "강조는 문단당 1~2개로 절제하고, 감싼 텍스트는 본문에 그대로 보이게 자연스러운 문장이어야 합니다."
)

_MARKUP_RE = re.compile(r"<<(\w+):(.*?)>>", re.DOTALL)


def parse_emphasis_markup(text: str) -> tuple[str, list[EmphasisRequest]]:
    """<<role:text>> 마킹 제거 → (깨끗한 본문, 강조 요청 목록).

    각 요청의 start는 깨끗한 본문에서의 시작 위치(밀도 규칙용).
    """
    requests: list[EmphasisRequest] = []
    out: list[str] = []
    idx = 0
    clean_len = 0
    for m in _MARKUP_RE.finditer(text):
        prefix = text[idx : m.start()]
        out.append(prefix)
        clean_len += len(prefix)
        inner = m.group(2)
        requests.append(EmphasisRequest(text=inner, role=m.group(1), start=clean_len))
        out.append(inner)
        clean_len += len(inner)
        idx = m.end()
    out.append(text[idx:])
    return "".join(out), requests


def apply_density(
    clean_text: str, requests: list[EmphasisRequest], config: EmphasisConfig
) -> list[EmphasisRequest]:
    """밀도 규칙 적용 — 문단당 최대 개수 / 강조 간 최소 문장 간격으로 과한 강조 솎기.

    위치(start)가 없는 요청은 그대로 유지한다. 본문 앞쪽(먼저 나온) 강조를 우선 유지.
    """
    max_p = config.max_per_paragraph
    min_gap = config.min_sentence_gap
    if not max_p and not min_gap:
        return requests

    # 문단 경계(빈 줄 기준), 문장 끝 위치(.ᐟ . ! ? 줄바꿈)
    para_bounds: list[tuple[int, int]] = []
    s = 0
    for m in re.finditer(r"\n\s*\n", clean_text):
        para_bounds.append((s, m.start()))
        s = m.end()
    para_bounds.append((s, len(clean_text)))
    sent_ends = [m.end() for m in re.finditer(r"\.ᐟ|[.!?\n]", clean_text)]

    def para_index(pos: int) -> int:
        for i, (a, b) in enumerate(para_bounds):
            if a <= pos <= b:
                return i
        return len(para_bounds) - 1

    def sentence_index(pos: int) -> int:
        return sum(1 for e in sent_ends if e <= pos)

    per_para: dict[int, int] = {}
    last_sent: dict[int, int] = {}
    kept: list[EmphasisRequest] = []
    for r in sorted(requests, key=lambda x: x.start if x.start >= 0 else 0):
        if r.start < 0:
            kept.append(r)
            continue
        pi, si = para_index(r.start), sentence_index(r.start)
        if max_p and per_para.get(pi, 0) >= max_p:
            continue
        if min_gap and pi in last_sent and si - last_sent[pi] < min_gap:
            continue
        kept.append(r)
        per_para[pi] = per_para.get(pi, 0) + 1
        last_sent[pi] = si
    return kept


class EmphasisRequest(BaseModel):
    """초안에서 추출된 강조 대상 한 건.

    role: 'cycle'(핵심 문장·감상 → 순환 풀) 또는 고정 매핑 키('price','name' 등).
    start: 깨끗한 본문에서의 시작 위치(밀도 규칙용). 미상이면 -1.
    """

    text: str
    role: str = "cycle"
    start: int = -1


class StyledSpan(BaseModel):
    text: str
    preset_id: int | None
    style: EmphasisStyle


def assign_emphasis(
    requests: list[EmphasisRequest],
    presets: dict[int, EmphasisStyle],
    config: EmphasisConfig,
) -> list[StyledSpan]:
    """강조 요청 목록 → 스타일 배정.

    고정 매핑 키는 항상 같은 프리셋, 그 외('cycle')는 순환 풀에서 번갈아.
    """
    pool = CyclingPool(config.cycling_pool)
    out: list[StyledSpan] = []
    for req in requests:
        if req.role in config.fixed_map:
            pid = config.fixed_map[req.role]
        else:
            pid = pool.next()
        style = presets.get(pid, EmphasisStyle()) if pid is not None else EmphasisStyle()
        out.append(StyledSpan(text=req.text, preset_id=pid, style=style))
    return out
