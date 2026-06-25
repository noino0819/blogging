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


def chat(
    messages: list[dict],
    model: str | None = None,
    *,
    fmt: str | None = None,
    temperature: float = 0.7,
    timeout: int = 600,
) -> str:
    """Ollama chat API 호출 → 응답 텍스트.

    messages: [{"role": "system"|"user"|"assistant", "content": "..."}].
    fmt="json"이면 JSON 응답을 강제한다.
    """
    model = model or default_text_model()
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
