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

from pydantic import BaseModel, Field


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


def load_power_shortcuts(data) -> dict[int, EmphasisStyle]:
    """파워 단축키 JSON(export) → {단축키번호: EmphasisStyle}.

    list( [{...}, ...] ) 또는 dict( {"1": {...}} / {"shortcuts": [...]} ) 모두 수용.
    실제 export 형식이 확정되면 이 함수만 맞추면 된다.
    """
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
    """강조 배정 규칙."""

    cycling_pool: list[int] = Field(default_factory=list)  # 예: [1, 3, 5]
    fixed_map: dict[str, int] = Field(default_factory=dict)  # 예: {"price": 7, "name": 4}
    max_per_paragraph: int | None = None  # (옵션) 문단당 강조 개수 상한
    min_sentence_gap: int | None = None  # (옵션) 강조 간 최소 문장 간격


class EmphasisRequest(BaseModel):
    """초안에서 추출된 강조 대상 한 건.

    role: 'cycle'(핵심 문장·감상 → 순환 풀) 또는 고정 매핑 키('price','name' 등).
    """

    text: str
    role: str = "cycle"


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
