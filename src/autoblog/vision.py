"""Vision LLM 연동 지점 (기획서 §3.2, §5).

이미지형 상품 상세설명/사진을 로컬 Vision 모델(Ollama)로 이해해 구조화한다.
일반 OCR(Tesseract) 대신 Vision LLM을 쓰는 이유: 이미지 맥락을 이해해
재질·크기·사용법·주의사항 등으로 정리하기 위함.

현재는 Ollama/비전 모델 미설치 상태라 연동 지점만 정의한다. 모델 셋업 후
extract_product_specs / classify_photos 본문을 구현한다.
"""

from __future__ import annotations

from autoblog.collect.fact_card import ProductSpec


class VisionUnavailable(RuntimeError):
    """Vision 모델이 아직 연동되지 않았거나 사용할 수 없을 때."""


def extract_product_specs(image_paths: list[str], model: str | None = None) -> list[ProductSpec]:
    """이미지형 상세설명 → 구조화 스펙(재질/크기/사용법/주의사항 등).

    구현 예정(Ollama 비전 모델):
    1. 세로로 긴 이미지는 조각으로 분할 후 처리하고 결과를 합친다.
    2. 각 조각을 Vision 모델에 넣어 구조화 JSON(키-값)으로 추출.
    3. 중복 키 병합 → ProductSpec 목록.
    """
    raise VisionUnavailable("Ollama 비전 모델 미연동 — 모델 셋업 후 구현 예정")


def classify_photos(image_paths: list[str], model: str | None = None) -> dict[str, list[str]]:
    """입력 사진 자동 분류(음식/메뉴판/외관/내부 등) — 1단계 정보 수집용.

    구현 예정(Ollama 비전 모델).
    """
    raise VisionUnavailable("Ollama 비전 모델 미연동 — 모델 셋업 후 구현 예정")
