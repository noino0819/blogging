"""CLI 엔트리 — 백엔드 단독 실행용.

나중에 Electron 셸이 이 명령들을 자식 프로세스로 호출한다(기획서 §7.1).
"""

from __future__ import annotations

import typer

from autoblog.config import load_env, load_models_config

app = typer.Typer(add_completion=False, help="로컬 LLM 블로그 자동 작성 — 백엔드")


@app.command()
def models(tier: str = typer.Option(None, help="프리셋 키 (예: 8gb). 미지정 시 기본값")):
    """선택된 GPU 티어 프리셋의 vision/text 모델을 출력."""
    cfg = load_models_config()
    preset = cfg.get(tier)
    typer.echo(f"[{preset.label}]")
    typer.echo(f"  vision : {preset.vision}")
    typer.echo(f"  text   : {preset.text}")
    typer.echo(f"  동시로드: {preset.concurrent_load}")


@app.command()
def place(query: str = typer.Argument(..., help="가게명 + 지역 (예: '교대 김밥천국')")):
    """맛집 사실 카드 수집 (검색 API → 스크래핑)."""
    from autoblog.collect.place import collect_place

    card = collect_place(query)
    typer.echo(card.model_dump_json(indent=2, exclude_none=True))


@app.command()
def product(
    query: str = typer.Argument(..., help="상품 검색어 (예: '강아지 노즈워크 장난감')"),
    image: list[str] = typer.Option(
        None, "--image", "-i", help="상세설명 이미지 경로(반복 지정). Vision 전사/추출"
    ),
    text: str = typer.Option(
        None, "--text", "-t", help="상세설명을 텍스트로 직접 입력(Vision 불필요)"
    ),
    vision_main: bool = typer.Option(
        False, "--vision-main", help="쇼핑 API 메인 이미지도 내려받아 Vision 분석"
    ),
):
    """상품 사실 카드 수집 (쇼핑 검색 API + 상세설명 이미지/텍스트)."""
    from autoblog.collect.product import collect_product

    card = collect_product(
        query, detail_images=image or None, detail_text=text, vision_on_main=vision_main
    )
    typer.echo(card.model_dump_json(indent=2, exclude_none=True))


@app.command(name="place-url")
def place_url(
    url: str = typer.Argument(..., help="플레이스 URL (naver.me 단축링크 또는 m.place...)"),
    reviews: bool = typer.Option(True, help="방문자 리뷰(경험 키워드/본문) 수집 여부"),
    review_limit: int = typer.Option(12, help="수집할 리뷰 본문 최대 개수"),
):
    """플레이스 URL → 상세 사실 카드 (메뉴/가격/평점/좌표/영업시간 + 방문자 리뷰). 권장 경로."""
    from autoblog.collect.place import collect_place_from_url

    card = collect_place_from_url(url, with_reviews=reviews, review_limit=review_limit)
    typer.echo(card.model_dump_json(indent=2, exclude_none=True))


@app.command()
def style(
    posts: list[str] = typer.Argument(..., help="과거 글 파일 경로(2~3개)"),
    out: str = typer.Option(None, "--out", "-o", help="추출된 문체 프로파일 저장 경로"),
):
    """과거 글에서 문체 프로파일 추출 (기획서 §4.2)."""
    from autoblog.draft.style import extract_style_profile

    texts = [open(p, encoding="utf-8").read() for p in posts]
    profile = extract_style_profile(texts)
    typer.echo(profile)
    if out:
        open(out, "w", encoding="utf-8").write(profile)
        typer.echo(f"\n저장됨: {out}", err=True)


@app.command()
def classify(images: list[str] = typer.Argument(..., help="분류할 사진 경로(여러 장)")):
    """입력 사진 자동 분류 (음식/메뉴판/외관/내부/영수증/상품/기타)."""
    from autoblog.collect.fact_card import CardType, FactCard
    from autoblog.collect.photos import classify_photos_into, photo_summary

    card = classify_photos_into(FactCard(type=CardType.place), images)
    for p in card.photos:
        typer.echo(f"{p.label}\t{p.path}")
    typer.echo(f"\n요약: {photo_summary(card.photos)}", err=True)
    for w in card.warnings:
        typer.echo(f"경고: {w}", err=True)


@app.command()
def draft(
    memo: str = typer.Argument(..., help="경험 메모(글의 중심/주연)"),
    place_url: str = typer.Option(None, "--place-url", help="맛집: 플레이스 URL로 사실 카드"),
    product: str = typer.Option(None, "--product", help="상품: 검색어로 사실 카드"),
    photo: list[str] = typer.Option(None, "--photo", "-p", help="입력 사진(분류 후 배치 안내)"),
    tone: str = typer.Option(None, "--tone", help="문체 톤 지시 (예: '친근한 반말로')"),
    style_file: str = typer.Option(
        None, "--style-file", help="문체 프로파일 파일(autoblog style로 추출)"
    ),
    prompt_file: str = typer.Option(
        None, "--prompt-file", help="베이스 프롬프트 파일 경로(기본 config/prompts/default.md)"
    ),
    model: str = typer.Option(None, "--model", help="텍스트 모델 override(기본 프리셋)"),
    emphasis: bool = typer.Option(False, "--emphasis", help="강조(서식) 배정 켜기"),
    shortcuts: str = typer.Option(
        None, "--shortcuts", help="파워 단축키 JSON 경로(미지정 시 내장 기본 스타일)"
    ),
):
    """경험 메모 + 사실 카드 → 경험 중심 블로그 초안 생성."""
    from autoblog.collect.fact_card import CardType, FactCard
    from autoblog.draft.generate import DraftRequest, generate_draft
    from autoblog.draft.prompts import load_base_prompt
    from autoblog.draft.style import StyleProfile

    if place_url:
        from autoblog.collect.place import collect_place_from_url

        card = collect_place_from_url(place_url)
    elif product:
        from autoblog.collect.product import collect_product

        card = collect_product(product)
    else:
        card = FactCard(type=CardType.place)
        typer.echo("(사실 카드 없이 경험 메모만으로 작성)", err=True)

    if photo:
        from autoblog.collect.photos import classify_photos_into

        classify_photos_into(card, photo)

    power_shortcuts = None
    if shortcuts:
        import json

        from autoblog.publish.emphasis import load_power_shortcuts

        power_shortcuts = load_power_shortcuts(json.loads(open(shortcuts, encoding="utf-8").read()))

    req = DraftRequest(
        fact_card=card,
        experience_memo=memo,
        base_prompt=load_base_prompt(prompt_file) if prompt_file else None,
        style=StyleProfile(
            tone=tone,
            profile=open(style_file, encoding="utf-8").read() if style_file else None,
        )
        if (tone or style_file)
        else None,
        emphasis=emphasis,
        power_shortcuts=power_shortcuts,
    )
    result = generate_draft(req, model=model)
    typer.echo(result.text)
    if result.emphases:
        typer.echo("\n--- 강조 배정 ---", err=True)
        for s in result.emphases:
            st = s.style
            desc = st.text_color or st.background_color or "기본"
            typer.echo(f"[{s.preset_id}] {desc}  «{s.text}»", err=True)
    if result.checklist:
        typer.echo("\n--- 가이드라인 체크 ---", err=True)
        for c in result.checklist:
            mark = "O" if c.ok else "X"
            typer.echo(f"[{mark}] {c.item} {c.detail}", err=True)


@app.command()
def doctor():
    """환경 점검 — API 키/Ollama 설정 여부 + 검색 API 라이브 호출."""
    from autoblog.collect.place import ping_search_api

    import requests

    env = load_env()
    typer.echo(f"네이버 검색 API : {'설정됨' if env.has_naver_api else '미설정 (.env)'}")
    ok, msg = ping_search_api()
    typer.echo(f"검색 API 라이브 : {'OK' if ok else msg}")

    cfg = load_models_config()
    vision_model = cfg.get().vision
    try:
        tags = requests.get(f"{env.ollama_host}/api/tags", timeout=3).json()
        installed = {m["name"] for m in tags.get("models", [])}
        typer.echo(f"Ollama         : OK ({env.ollama_host})")
        has_vision = vision_model in installed
        typer.echo(
            f"비전 모델       : {'OK' if has_vision else f'미설치 (ollama pull {vision_model})'} [{vision_model}]"
        )
    except requests.RequestException:
        typer.echo(f"Ollama         : 미실행 ({env.ollama_host}) — ollama serve")


if __name__ == "__main__":
    app()
