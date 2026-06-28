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


def build_user_prompt(card: FactCard, experience_memo: str, template_text: str | None = None) -> str:
    """재료(경험 메모=주연, 사실 카드=조연) → 사용자 프롬프트.

    재료 구분용 머리말은 모델이 본문에 인용하지 않도록 명시한다(라벨 누수 방지).
    """
    facts = render_fact_card(card)
    parts = [
        "다음은 글을 쓰기 위한 재료입니다. 이 재료의 머리말·항목 이름(예: '나의 경험', "
        "'참고 정보', '방문자 키워드' 등)을 본문에 절대 언급하거나 인용하지 마세요. "
        "재료에 없는 사실은 지어내지 마세요.",
        "# 나의 경험 (이 내용을 글의 중심으로 삼으세요)\n" + experience_memo.strip(),
        "# 참고 정보 (필요한 것만 자연스럽게 녹이세요)\n" + facts,
    ]
    if card.photos:
        from autoblog.collect.photos import photo_summary

        labels = sorted({p.label for p in card.photos})
        n = len(card.photos)
        parts.append(
            "# 사진 구성 (분류 결과)\n"
            f"보유 사진: {photo_summary(card.photos)} (총 {n}장)\n"
            f"이 {n}장을 한 장도 빠짐없이 모두 본문에 배치하세요. 사진 수만큼 마커를 넣어야 합니다"
            f"(마커가 모자라면 남은 사진이 글 끝에 몰려 들어갑니다).\n"
            "본문 흐름에 맞는 위치에 [사진:라벨] 을 한 줄로 넣어 그 내용에 어울리는 사진을 배치하세요"
            f"(라벨은 보유 사진의 분류명: {', '.join(labels)}).\n"
            "예: 음식 묘사 문단 뒤엔 [사진:음식], 가게 첫인상 문단 뒤엔 [사진:외관]. "
            "라벨을 모르겠으면 그냥 [사진] 으로 두면 됩니다. 같은 라벨 사진이 여러 장이면 그만큼 마커를 반복하세요."
        )
        captioned = [p for p in card.photos if p.caption]
        if captioned:
            parts.append(
                "# 사진 내용 (각 사진이 구체적으로 무엇인지 — 이 설명에 맞는 문맥에 배치하세요)\n"
                + "\n".join(f"- {p.caption} (라벨: {p.label})" for p in captioned)
                + "\n사진 속 대상을 본문에서 정확히 언급하되, 이 목록의 형식 자체는 본문에 옮기지 마세요."
            )
    if template_text and template_text.strip():
        parts.append(
            "# 사용 템플릿\n"
            "다음 템플릿은 최종 글의 구조입니다. 템플릿의 사진 마커와 제목 위치를 유지하며, "
            "실제 블로그 제목과 본문 내용으로 자연스럽게 채워주세요. 템플릿의 레이블은 그대로 복사하지 말고 "
            "실제 글 제목/본문으로 바꾸세요.\n"
            + template_text.strip()
        )
    parts.append("위 경험을 중심으로 네이버 블로그 후기 글을 제목과 본문으로 작성하세요.")
    return "\n\n".join(parts)
