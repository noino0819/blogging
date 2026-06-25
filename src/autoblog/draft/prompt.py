"""프롬프트 계층 조립 (기획서 §4.1).

[맨 위] 가이드라인(있을 때만, 최우선) → 문체 프로파일 → 공통 규칙 → 핵심 원칙
재료: 경험 메모(주연) + 사실 카드(조연).
"""

from __future__ import annotations

from autoblog.collect.fact_card import FactCard
from autoblog.draft.guideline import Guidelines
from autoblog.draft.rules import CommonRules
from autoblog.draft.style import StyleProfile


def render_fact_card(card: FactCard) -> str:
    """사실 카드 → 초안 재료용 한국어 사실 요약(조연)."""
    lines: list[str] = []
    if card.place:
        p = card.place
        lines.append(f"가게명: {p.name}")
        if p.category:
            lines.append(f"분류: {p.category}")
        if p.road_address:
            lines.append(f"주소: {p.road_address}")
        if p.business_hours:
            lines.append(f"영업시간: {p.business_hours}")
        if p.phone:
            lines.append(f"전화: {p.phone}")
        if p.rating:
            lines.append(f"평점: {p.rating}")
        if p.description:
            lines.append(f"소개: {p.description}")
        if p.menus:
            menu_str = ", ".join(
                f"{m.name}({m.price})" if m.price else m.name for m in p.menus[:12]
            )
            lines.append(f"메뉴: {menu_str}")
        if p.conveniences:
            lines.append(f"편의시설: {', '.join(p.conveniences)}")
        if p.review_keywords:
            kw = ", ".join(f"{k.name}({k.count})" for k in p.review_keywords[:8])
            lines.append(f"방문자 키워드: {kw}")
        if p.reviews:
            snippet = " / ".join(r.body[:60] for r in p.reviews[:3])
            lines.append(f"방문자 리뷰 일부: {snippet}")
    if card.product:
        pr = card.product
        lines.append(f"상품명: {pr.name}")
        if pr.price:
            lines.append(f"가격: {pr.price}")
        if pr.brand:
            lines.append(f"브랜드: {pr.brand}")
        if pr.category:
            lines.append(f"분류: {pr.category}")
        if pr.selling_points:
            lines.append(f"셀링포인트: {', '.join(pr.selling_points)}")
        if pr.specs:
            spec_str = ", ".join(f"{s.key}: {s.value}" for s in pr.specs)
            lines.append(f"스펙: {spec_str}")
        if pr.detail_text:
            lines.append(f"상세설명: {pr.detail_text}")
    return "\n".join(lines)


def build_system_prompt(
    base_prompt: str,
    style: StyleProfile | None = None,
    guidelines: Guidelines | None = None,
    rules: CommonRules | None = None,
) -> str:
    """계층 순서대로 시스템 프롬프트 조립 (기획서 §4.1).

    [맨 위] 가이드라인(최우선) → 베이스 프롬프트(역할·포맷·문체) →
    추가 규칙(선택) → 추가 문체 지시(선택).
    """
    blocks: list[str] = []

    if guidelines and not guidelines.is_empty():
        blocks.append(guidelines.as_prompt())  # 최우선 제약

    blocks.append(base_prompt)

    if rules:
        fragments = rules.active_fragments()
        if fragments:
            blocks.append("[추가 규칙]\n" + "\n".join(f"- {f}" for f in fragments))

    if style and style.as_prompt():
        blocks.append("[추가 문체 지시]\n" + style.as_prompt())

    return "\n\n".join(blocks)


def build_user_prompt(card: FactCard, experience_memo: str) -> str:
    """재료(경험 메모=주연, 사실 카드=조연) → 사용자 프롬프트.

    재료 구분용 머리말은 모델이 본문에 인용하지 않도록 명시한다(라벨 누수 방지).
    """
    facts = render_fact_card(card)
    return (
        "다음은 글을 쓰기 위한 재료입니다. 이 재료의 머리말·항목 이름(예: '나의 경험', "
        "'참고 정보', '방문자 키워드' 등)을 본문에 절대 언급하거나 인용하지 마세요. "
        "재료에 없는 사실은 지어내지 마세요.\n\n"
        "# 나의 경험 (이 내용을 글의 중심으로 삼으세요)\n"
        f"{experience_memo.strip()}\n\n"
        "# 참고 정보 (필요한 것만 자연스럽게 녹이세요)\n"
        f"{facts}\n\n"
        "위 경험을 중심으로 네이버 블로그 후기 글을 제목과 본문으로 작성하세요."
    )
