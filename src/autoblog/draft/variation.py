"""시드 기반 스타일 변주 — 글 간 기계 지문 제거 (config/style_pool.yaml).

전 글이 같은 카오모지 세트·같은 빈도·같은 고정 문구로 수렴하면 블로그 전체(나아가
여러 계정)에서 동일 패턴이 반복돼, 네이버 유사문서·스팸 필터가 보는 '타 문서와
중복된 표현 반복' 신호가 된다. 글 재료(경험 메모+대상 이름)로 결정적 시드를 만들어
풀에서 부분집합·개수 상한·구조 변형을 뽑아 '[이번 글 스타일 변주]' 블록으로 주입한다.
같은 재료면 같은 변주(재생성 재현성·테스트 결정성), 글이 다르면 조합이 달라진다.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from autoblog.config import CONFIG_DIR

STYLE_POOL_PATH = CONFIG_DIR / "style_pool.yaml"

# 카테고리 → (표시 이름, 뽑는 개수 범위)
_KAOMOJI_PICKS = [
    ("taste", "맛·만족", (1, 2)),
    ("cheer", "응원·파이팅", (1, 2)),
    ("sad", "아쉬움", (1, 1)),
    ("angry", "불만(필요할 때만)", (0, 1)),
    ("cute", "귀여움·꾸미기", (1, 2)),
]


def load_style_pool(path: str | Path | None = None) -> dict:
    """변주 풀 로드(없거나 깨지면 빈 dict → 변주 블록 생략).

    변주는 부가 기능이라, 유저가 편집하는 yaml의 문법 오류(YAMLError)가
    초안 생성 자체를 죽이면 안 된다.
    """
    import yaml

    try:
        data = yaml.safe_load(Path(path or STYLE_POOL_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _pick(rng: random.Random, items: list, k: int) -> list:
    """중복 없이 k개(부족하면 전부) — 순서도 시드에 따라 섞는다."""
    if not items:
        return []
    k = min(k, len(items))
    return rng.sample(list(items), k)


def build_variation_block(
    seed_text: str, is_product: bool = False, *, pool: dict | None = None
) -> str | None:
    """이번 글에만 적용할 스타일 변주 블록(시스템 프롬프트에 덧붙임).

    seed_text가 같으면 항상 같은 블록을 만든다(md5 기반 — 보안 아닌 분산 용도).
    """
    pool = pool if pool is not None else load_style_pool()
    if not pool:
        return None
    seed = int(hashlib.md5(seed_text.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)

    lines = [
        "[이번 글 스타일 변주] — 아래는 이번 글에만 적용되는 설정이야. "
        "공통 문체 규칙의 이모티콘·유행어·특수문자(〰️·문장 끝 '-') 목록/빈도와 "
        "다르면 이쪽이 우선해. (글마다 조합이 달라야 여러 글이 똑같아 보이지 않아)"
    ]

    # 표정 이모티콘: 카테고리별 부분집합 + 총 개수 상한(0이거나 뽑힌 게 없으면 카오모지 없이)
    kaomoji = pool.get("kaomoji") if isinstance(pool.get("kaomoji"), dict) else {}
    face_quota = rng.choice([0, 2, 3, 3, 4, 4, 5, 6])
    picks: list[tuple[str, list[str]]] = []
    for key, label, (lo, hi) in _KAOMOJI_PICKS:
        items = kaomoji.get(key)
        picked = _pick(rng, list(items) if isinstance(items, list) else [], rng.randint(lo, hi))
        if picked:
            picks.append((label, picked))
    if face_quota and picks:
        lines.append(
            f"- 표정 이모티콘: 이번 글에서는 아래 것만, 글 전체 {face_quota}개 이내로 써"
            "(어울리는 곳이 없으면 덜 써도 돼):"
        )
        for label, picked in picks:
            lines.append(f"  · {label}: {' '.join(picked)}")
    else:
        lines.append(
            "- 표정 이모티콘: 이번 글에서는 카오모지를 쓰지 마"
            "(강조 이모티콘 ✨⭐️👀😎🥹👍🏻는 공통 규칙대로 사용 가능)."
        )

    # 특수문자 빈도 — 하한 없이 상한만(0이면 금지). 글마다 분포가 달라진다.
    wavy = rng.choice([0, 1, 1, 2, 2, 3])
    dash = rng.choice([0, 1, 2, 2, 3, 3])
    lines.append(
        f"- 〰️: 최대 {wavy}회" + ("(이번 글에서는 쓰지 마)" if wavy == 0 else "(안 써도 됨)")
    )
    lines.append(
        f"- 문장 끝 여운 '-': 최대 {dash}회"
        + ("(이번 글에서는 쓰지 마 — 물결표도 '-'로 대체하지 말고 그냥 빼)" if dash == 0 else "")
    )

    # 유행어: 이번 글 후보 2~4개만 노출, 사용 개수 상한(0이면 유행어 없이)
    slang_pool = [
        s
        for s in (pool.get("slang") or [])
        if isinstance(s, dict) and all(k in s for k in ("expr", "meaning", "example"))
    ]
    slang_quota = rng.choice([0, 1, 1, 2, 2, 3])
    if slang_quota and slang_pool:
        candidates = _pick(rng, slang_pool, rng.randint(2, 4))
        lines.append(
            f"- 유행어: 아래 후보 중에서만, 최대 {slang_quota}개"
            "(자연스럽게 녹아들 때만 — 0개여도 됨):"
        )
        for s in candidates:
            lines.append(f"  · \"{s['expr']}\" — {s['meaning']} (예: \"{s['example']}\")")
    else:
        lines.append("- 유행어: 이번 글에서는 유행어·신조어를 쓰지 말고 담백하게 써.")

    # 글 구조 변형
    structures = pool.get("structure_product" if is_product else "structure_place") or []
    if structures:
        lines.append(f"- 섹션 흐름: {rng.choice(structures)} — 재료에 없는 섹션은 건너뛰어.")
    if not is_product:  # '핵심 한마디'는 맛집 구조 전용(상품은 요약 박스가 그 역할)
        quote_positions = pool.get("quote_position") or []
        if quote_positions:
            lines.append(f"- 핵심 한마디 위치: {rng.choice(quote_positions)}")

    if is_product:
        headings = pool.get("checklist_heading") or []
        if headings:
            lines.append(f'- 추천 체크리스트 소제목: "🌟 {rng.choice(headings)}"')
        connectors = pool.get("summary_connector") or []
        if connectors:
            conn = rng.choice(connectors)
            lines.append(f"- 핵심 요약 박스의 소제목-설명 연결 문자: '{conn}'")
    else:
        transitions = pool.get("pick_transition") or []
        if transitions:
            lines.append(
                f'- (여러 곳 소개 글일 때) PICK 리스트 전환 멘트: "{rng.choice(transitions)}" '
                "느낌으로 — 그대로 베끼지 말고 상황에 맞게 바꿔 써."
            )

    return "\n".join(lines)
