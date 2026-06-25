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
        None, "--image", "-i", help="상세설명 이미지 경로(반복 지정). Vision 스펙 추출용"
    ),
    vision_main: bool = typer.Option(
        False, "--vision-main", help="쇼핑 API 메인 이미지도 내려받아 Vision 분석"
    ),
):
    """상품 사실 카드 수집 (쇼핑 검색 API 기본정보 + 이미지 Vision 상세)."""
    from autoblog.collect.product import collect_product

    card = collect_product(query, detail_images=image or None, vision_on_main=vision_main)
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
