"""Ollama 텍스트 LLM 호출 공통 (초안 작성·문체 추출 등).

모델명은 config/models.yaml(프리셋 text)에서 읽는다. 비전은 vision.py 참고.
"""

from __future__ import annotations

import requests

from autoblog.config import load_env, load_models_config, provider_for_model


class LLMUnavailable(RuntimeError):
    """텍스트 모델이 연동되지 않았거나(미설치/서버다운) 사용할 수 없을 때."""


def default_text_model() -> str:
    return load_models_config().effective().text


def provider_for(model: str) -> str:
    """모델명으로 API 제공자 판별(라우팅용). 그 외는 로컬 Ollama."""
    return provider_for_model(model)


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


def _chat_openai(messages: list[dict], model: str, fmt: str | None = None) -> str:
    """OpenAI(GPT) API로 텍스트 생성. OPENAI_API_KEY 필요."""
    try:
        from openai import APIError, AuthenticationError, OpenAI
    except ImportError as exc:
        raise LLMUnavailable("openai 패키지 미설치 — pip install openai") from exc

    env = load_env()
    if not env.openai_api_key:
        raise LLMUnavailable("OPENAI_API_KEY 미설정 — 설정 탭에서 API 키를 입력하세요")
    msgs = list(messages)
    kwargs: dict = {}
    if fmt == "json":
        kwargs["response_format"] = {"type": "json_object"}
        msgs = msgs + [{"role": "system", "content": "JSON으로만 답하세요."}]
    client = OpenAI(api_key=env.openai_api_key)
    try:
        resp = client.chat.completions.create(model=model, messages=msgs, **kwargs)
    except AuthenticationError as exc:
        raise LLMUnavailable("OPENAI_API_KEY가 유효하지 않습니다") from exc
    except APIError as exc:
        raise LLMUnavailable(f"OpenAI API 오류: {exc}") from exc
    return resp.choices[0].message.content or ""


def _chat_gemini(messages: list[dict], model: str, fmt: str | None = None) -> str:
    """Google Gemini API로 텍스트 생성. GEMINI_API_KEY 필요."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as exc:
        raise LLMUnavailable("google-genai 패키지 미설치 — pip install google-genai") from exc

    env = load_env()
    if not env.gemini_api_key:
        raise LLMUnavailable("GEMINI_API_KEY 미설정 — 설정 탭에서 API 키를 입력하세요")
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
        if m["role"] in ("user", "assistant")
    ]
    cfg = types.GenerateContentConfig(
        system_instruction=system or None,
        response_mime_type="application/json" if fmt == "json" else None,
    )
    client = genai.Client(api_key=env.gemini_api_key)
    try:
        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
    except errors.APIError as exc:
        raise LLMUnavailable(f"Gemini API 오류: {exc}") from exc
    return resp.text or ""


def _vision_gemini(prompt: str, images: list[bytes], model: str, *, fmt: str | None = None) -> str:
    """Google Gemini 멀티모달 호출 — 프롬프트 + 이미지 여러 장 한 번에. GEMINI_API_KEY 필요."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as exc:
        raise LLMUnavailable("google-genai 패키지 미설치 — pip install google-genai") from exc

    env = load_env()
    if not env.gemini_api_key:
        raise LLMUnavailable("GEMINI_API_KEY 미설정 — 설정 탭에서 API 키를 입력하세요")
    parts = [types.Part(text=prompt)]
    parts += [types.Part.from_bytes(data=b, mime_type="image/png") for b in images]
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json" if fmt == "json" else None,
    )
    client = genai.Client(api_key=env.gemini_api_key)
    try:
        resp = client.models.generate_content(
            model=model, contents=[types.Content(role="user", parts=parts)], config=cfg
        )
    except errors.APIError as exc:
        raise LLMUnavailable(f"Gemini API 오류: {exc}") from exc
    return resp.text or ""


def vision_chat(prompt: str, images: list[bytes], model: str, *, fmt: str | None = None) -> str:
    """이미지(여러 장)+프롬프트 멀티모달 호출 → 응답 텍스트.

    현재 Gemini만 지원(사진 자동 추천용). 로컬(Ollama) 비전은 vision.py 참고.
    """
    if provider_for(model) == "gemini":
        return _vision_gemini(prompt, images, model, fmt=fmt)
    raise LLMUnavailable(
        f"사진 자동 추천은 Gemini 모델만 지원합니다(현재 caption.model: {model!r}). "
        "config/models.yaml 의 caption.model 을 gemini-* 로 설정하세요."
    )


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
    모델명 접두사로 라우팅(claude→Claude, gpt/o*→GPT, gemini→Gemini, 그 외→Ollama).
    fmt="json"이면 JSON 응답 강제.
    """
    model = model or default_text_model()
    provider = provider_for(model)
    if provider == "anthropic":
        return _chat_anthropic(messages, model, fmt=fmt)
    if provider == "openai":
        return _chat_openai(messages, model, fmt=fmt)
    if provider == "gemini":
        return _chat_gemini(messages, model, fmt=fmt)
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
