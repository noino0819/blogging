"""사진 분류 연동 (기획서 §1, §3).

입력 사진을 Vision LLM으로 자동 분류(음식/메뉴판/외관/내부/영수증/상품/기타)해
FactCard.photos에 채운다. 초안 작성 시 본문 사진 배치에 활용한다.
"""

from __future__ import annotations

from collections import Counter

from autoblog.collect.fact_card import FactCard, PhotoItem


def classify_photos_into(card: FactCard, image_paths: list[str], model: str | None = None) -> FactCard:
    """사진들을 분류해 card.photos에 채운다. Vision 미연동 시 '기타'로 채우고 경고."""
    from autoblog.vision import VisionUnavailable, classify_photos

    try:
        labels = classify_photos(image_paths, model=model)
    except VisionUnavailable as exc:
        card.warnings.append(f"사진 분류 생략(Vision 미연동): {exc}")
        labels = {p: "기타" for p in image_paths}
    except Exception as exc:  # noqa: BLE001 - 사진 분류는 보조라 실패해도 진행
        card.warnings.append(f"사진 분류 실패: {exc}")
        labels = {p: "기타" for p in image_paths}

    card.photos = [PhotoItem(path=p, label=labels.get(p, "기타")) for p in image_paths]
    return card


def attach_photos(
    card: FactCard,
    image_paths: list[str],
    meta: dict[str, dict] | None = None,
) -> FactCard:
    """사진을 card.photos에 채운다(Vision 호출 없음).

    meta가 있으면 그 라벨·캡션(사용자 수동 분류 또는 AI 자동 추천 결과)을 쓰고,
    없으면 라벨 '기타'로 둔다. webui는 항상 이 경로로 채워 자동 분류를 돌리지 않는다.
    """
    meta = meta or {}
    card.photos = [
        PhotoItem(
            path=p,
            label=(meta.get(p) or {}).get("label") or "기타",
            caption=(meta.get(p) or {}).get("caption") or "",
        )
        for p in image_paths
    ]
    return card


def photo_summary(photos: list[PhotoItem]) -> str:
    """분류 라벨 분포 요약 (예: '음식 3, 외관 1, 메뉴판 1')."""
    counts = Counter(p.label for p in photos)
    return ", ".join(f"{label} {n}" for label, n in counts.most_common())
