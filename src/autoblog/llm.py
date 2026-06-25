"""Ollama 텍스트 LLM 호출 공통 (초안 작성·문체 추출 등).

모델명은 config/models.yaml(프리셋 text)에서 읽는다. 비전은 vision.py 참고.
"""

from __future__ import annotations

import requests

from autoblog.config import load_env, load_models_config


class LLMUnavailable(RuntimeError):
    """텍스트 모델이 연동되지 않았거나(미설치/서버다운) 사용할 수 없을 때."""


def default_text_model() -> str:
    return load_models_config().get().text


def _chat_anthropic(messages: list[dict], model: str, fmt: str | None = None) -> str:
    """Claude API(공식 anthropic SDK)로 텍스트 생성. ANTHROPIC_API_KEY 필요."""
    import anthropic

    env = load_env()
    if not env.anthropic_api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY 미설정 — 설정 탭에서 API 키를 입력하세요")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    if fmt == "json":
        system = (system + "\n\nJSON으로만 답하세요.").strip()
    conv = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m["role"] in ("user", "assistant")
    ]
    client = anthropic.Anthropic(api_key=env.anthropic_api_key)
    try:
        resp = client.messages.create(
            model=model, max_tokens=16000, messages=conv, **({"system": system} if system else {})
        )
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable("ANTHROPIC_API_KEY가 유효하지 않습니다") from exc
    except anthropic.APIError as exc:
        raise LLMUnavailable(f"Claude API 오류: {exc}") from exc
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def chat(
    messages: list[dict],
    model: str | None = None,
    *,
    fmt: str | None = None,
    temperature: float = 0.7,
    timeout: int = 600,
) -> str:
    """텍스트 LLM 호출 → 응답 텍스트.

    messages: [{"role": "system"|"user"|"assistant", "content": "..."}].
    모델명이 claude*면 Claude API(anthropic), 그 외는 Ollama. fmt="json"이면 JSON 응답 강제.
    """
    model = model or default_text_model()
    if model.startswith("claude"):
        return _chat_anthropic(messages, model, fmt=fmt)
    env = load_env()
    payload: dict = {
        "model": model,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": messages,
    }
    if fmt:
        payload["format"] = fmt
    try:
        resp = requests.post(f"{env.ollama_host}/api/chat", json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama 연결 실패({env.ollama_host}): {exc}") from exc
    if resp.status_code == 404:
        raise LLMUnavailable(f"모델 미설치: {model} (ollama pull {model})")
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")
