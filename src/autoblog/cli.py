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
def doctor():
    """환경 점검 — API 키/Ollama 설정 여부."""
    env = load_env()
    typer.echo(f"네이버 검색 API : {'OK' if env.has_naver_api else '미설정 (.env)'}")
    typer.echo(f"Ollama host    : {env.ollama_host}")


if __name__ == "__main__":
    app()
