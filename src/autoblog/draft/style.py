"""사용자 문체 (기획서 §4.2).

두 입력을 지원하고 조합한다:
- 과거 글 학습: 사용자 블로그 글 2~3개 → LLM이 문체 특징을 추출해 프로파일로 저장.
- 직접 설명: "친근한 반말로, 솔직담백하게" 같은 톤 지시.
프로파일(평소 문체) + 톤 지시(이번 글 조정)를 함께 시스템 프롬프트에 넣는다.
"""

from __future__ import annotations

from pydantic import BaseModel

from autoblog.llm import chat


class StyleProfile(BaseModel):
    profile: str | None = None  # 과거 글에서 추출한 평소 문체 특징
    tone: str | None = None  # 이번 글 톤 지시(직접 설명)

    def as_prompt(self) -> str | None:
        parts = []
        if self.profile:
            parts.append(f"[평소 문체 특징]\n{self.profile}")
        if self.tone:
            parts.append(f"[이번 글 톤 지시]\n{self.tone}")
        return "\n".join(parts) if parts else None


_EXTRACT_PROMPT = (
    "다음은 한 블로거의 과거 글들입니다. 이 사람의 문체 특징을 분석해 "
    "한국어로 간결히 정리하세요. 포함할 항목: 문장 길이(짧음/김), 어미 습관, "
    "존댓말/반말, 이모지 사용 정도, 감탄사 빈도, 자주 쓰는 표현·톤. "
    "글의 주제가 아니라 '쓰는 방식'만 묘사하세요. 5~8줄로."
)


def extract_style_profile(past_posts: list[str], model: str | None = None) -> str:
    """과거 글들 → 문체 특징 텍스트(프로파일)."""
    joined = "\n\n---\n\n".join(p.strip() for p in past_posts if p.strip())
    messages = [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": joined},
    ]
    return chat(messages, model=model, temperature=0.2).strip()
