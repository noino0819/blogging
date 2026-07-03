"""텍스트 LLM 호출 공통 (초안 작성·문체 추출 등).

API 전용 — Claude/GPT/Gemini/NVIDIA 호스티드만 지원한다(로컬 LLM 미지원).
모델명은 config/models.yaml(프리셋 text)에서 읽는다. 비전은 vision.py 참고.
"""

from __future__ import annotations

from autoblog.config import load_env, load_models_config, provider_for_model


class LLMUnavailable(RuntimeError):
    """텍스트 모델이 연동되지 않았거나(키 미설정/패키지 미설치) 사용할 수 없을 때."""


def default_text_model() -> str:
    return load_models_config().effective().text


def provider_for(model: str) -> str:
    """모델명으로 API 제공자 판별(라우팅용)."""
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


def _chat_openai(
    messages: list[dict],
    model: str,
    fmt: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    key_name: str = "OPENAI_API_KEY",
    extra_body: dict | None = None,
) -> str:
    """OpenAI 호환 API로 텍스트 생성 — 기본은 OpenAI(GPT), base_url을 주면 호환 서비스(NVIDIA 등)."""
    try:
        from openai import APIError, AuthenticationError, OpenAI
    except ImportError as exc:
        raise LLMUnavailable("openai 패키지 미설치 — pip install openai") from exc

    env = load_env()
    key = api_key if base_url else env.openai_api_key
    if not key:
        raise LLMUnavailable(f"{key_name} 미설정 — 설정 탭에서 API 키를 입력하세요")
    msgs = list(messages)
    kwargs: dict = {}
    if extra_body:
        kwargs["extra_body"] = extra_body
    if fmt == "json":
        kwargs["response_format"] = {"type": "json_object"}
        # system은 맨 앞에 — qwen 등 일부 챗 템플릿은 중간/끝 system을 거부한다
        msgs = [{"role": "system", "content": "JSON으로만 답하세요."}] + msgs
    client = OpenAI(api_key=key, base_url=base_url)
    try:
        resp = client.chat.completions.create(model=model, messages=msgs, **kwargs)
    except AuthenticationError as exc:
        raise LLMUnavailable(f"{key_name}가 유효하지 않습니다") from exc
    except APIError as exc:
        # 402=무료 크레딧 소진, 429=분당 요청 초과 — 잔여 크레딧 조회 API는 없어서 안내만
        if base_url and getattr(exc, "status_code", None) in (402, 429):
            raise LLMUnavailable(
                "NVIDIA 한도 도달 — 무료 크레딧(1,000회) 소진 또는 분당 40회 초과예요. "
                "잠시 후 재시도하거나 build.nvidia.com 로그인 후 잔여 크레딧을 확인하세요."
            ) from exc
        raise LLMUnavailable(f"{'NVIDIA' if base_url else 'OpenAI'} API 오류: {exc}") from exc
    return resp.choices[0].message.content or ""


def _chat_nvidia(
    messages: list[dict], model: str, fmt: str | None = None, extra_body: dict | None = None
) -> str:
    """NVIDIA 호스티드 모델(build.nvidia.com, OpenAI 호환 API). NVIDIA_API_KEY 필요."""
    return _chat_openai(
        messages,
        model,
        fmt,
        api_key=load_env().nvidia_api_key,
        base_url="https://integrate.api.nvidia.com/v1",
        key_name="NVIDIA_API_KEY",
        extra_body=extra_body,
    )


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


def _vision_nvidia(prompt: str, images: list[bytes], model: str, *, fmt: str | None = None) -> str:
    """NVIDIA 호스티드 VLM(qwen3.5 등) 멀티모달 호출 — OpenAI 호환 image_url 데이터 URL.

    thinking 모드는 끈다 — 캡션/분류엔 불필요하게 느리고, 켜면 간헐적으로
    content가 빈 응답이 온다(검증됨). 그래도 비면 재시도 후 LLMUnavailable.
    """
    import base64

    content: list[dict] = [{"type": "text", "text": prompt}]
    for b in images:
        mime = "jpeg" if b[:3] == b"\xff\xd8\xff" else "png"
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/{mime};base64,{base64.b64encode(b).decode()}"},
        })
    messages = [{"role": "user", "content": content}]
    extra = {"chat_template_kwargs": {"enable_thinking": False}}
    for _ in range(3):
        out = _chat_nvidia(messages, model, fmt=fmt, extra_body=extra)
        if out.strip():
            return out
    raise LLMUnavailable(f"NVIDIA VLM({model})이 빈 응답을 반복 — 잠시 후 다시 시도하세요")


def vision_chat(prompt: str, images: list[bytes], model: str, *, fmt: str | None = None) -> str:
    """이미지(여러 장)+프롬프트 멀티모달 호출 → 응답 텍스트.

    Gemini 또는 NVIDIA 호스티드 VLM(org/model 형식). 비전 기능 래퍼는 vision.py 참고.
    """
    provider = provider_for(model)
    if provider == "gemini":
        return _vision_gemini(prompt, images, model, fmt=fmt)
    if provider == "nvidia":
        return _vision_nvidia(prompt, images, model, fmt=fmt)
    raise LLMUnavailable(
        f"사진 분석은 Gemini/NVIDIA 모델만 지원합니다(현재 모델: {model!r}). "
        "config/models.yaml 에서 gemini-* 또는 qwen/qwen3.5-* 등으로 설정하세요."
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
    모델명 접두사로 라우팅(claude→Claude, gpt/o*→GPT, gemini→Gemini, org/model→NVIDIA).
    API 전용 — 그 외 모델명은 미지원. fmt="json"이면 JSON 응답 강제.
    temperature/timeout은 호환을 위해 받지만 API 경로에서는 사용하지 않는다.
    """
    model = model or default_text_model()
    provider = provider_for(model)
    if provider == "anthropic":
        return _chat_anthropic(messages, model, fmt=fmt)
    if provider == "openai":
        return _chat_openai(messages, model, fmt=fmt)
    if provider == "gemini":
        return _chat_gemini(messages, model, fmt=fmt)
    if provider == "nvidia":
        return _chat_nvidia(messages, model, fmt=fmt)
    raise LLMUnavailable(
        f"텍스트 생성은 API 모델만 지원합니다(현재 model: {model!r}). "
        "config/models.yaml 의 selection.text 를 claude-*/gpt-*/gemini-*/org/model(NVIDIA) 로 설정하세요."
    )
