"""스티커 카탈로그 — 불러오기 + 비전 자동 라벨 + 유저 검수 YAML + 상황→스티커 해석.

스티커는 Smart Editor DOM에 의미(감정/상황) 라벨이 없고 (팩코드, 인덱스) 좌표뿐이라
([[smart-editor-publish]]), 다음 4단계로 "상황에 맞는 스티커"를 구현한다:
  1) pull   — 에디터에서 각 스티커를 element 스크린샷으로 떠 모은다(editor.pull_stickers).
  2) label  — 비전 모델(qwen2.5vl)이 이미지를 보고 감정/상황 태그를 자동 생성(검수 옵션).
  3) review — 유저가 config/stickers.yaml에서 태그·즐겨쓰기를 직접 수정(자동 라벨 위 우선).
  4) resolve— 초안의 [스티커:상황] 마커를 (팩,인덱스)로 해석(StickerPicker).

(팩코드, 인덱스)를 안정 키로 **증분 동기화**한다: 다시 불러오면 새 스티커만 추가하고,
기존 태그/검수/즐겨쓰기는 보존하며, 패널에서 사라진 스티커는 stale로 표시(삭제 안 함).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from autoblog.config import CONFIG_DIR, REPO_ROOT

STICKER_CONFIG_PATH = CONFIG_DIR / "stickers.yaml"
STICKER_DATA_DIR = REPO_ROOT / "data" / "stickers"


class Sticker(BaseModel):
    """스티커 1개. (pack, index)가 안정 식별자."""

    pack: str  # 팩 코드(예: ogq_60f7003da4337, clip_001) — 썸네일 URL에서 추출
    index: int  # 팩 내 data-index
    animated: bool = False
    image: str | None = None  # 미리보기 PNG 상대경로(예: data/stickers/<pack>/<index>.png)
    tags: list[str] = Field(default_factory=list)  # 감정/상황 라벨(비전+유저)
    reviewed: bool = False  # 유저가 손봄 → 자동 라벨링이 덮어쓰지 않음
    stale: bool = False  # 재불러오기 시 패널에 더 없음(매핑 보존 위해 남겨둠)

    @property
    def ref(self) -> str:
        return f"{self.pack}:{self.index}"


class StickerCatalog(BaseModel):
    """유저의 스티커 카탈로그(= config/stickers.yaml 직렬화 대상)."""

    stickers: list[Sticker] = Field(default_factory=list)
    favorites: list[str] = Field(default_factory=list)  # 즐겨쓰기 ref("pack:index") 목록

    def by_ref(self) -> dict[str, Sticker]:
        return {s.ref: s for s in self.stickers}

    def labels(self) -> list[str]:
        """유효(비stale) 스티커의 모든 태그 distinct — 초안 지시문에 노출."""
        seen: list[str] = []
        for s in self.stickers:
            if s.stale:
                continue
            for t in s.tags:
                if t and t not in seen:
                    seen.append(t)
        return seen

    def find(self, label: str) -> list[Sticker]:
        """태그에 label을 가진 스티커들(stale 제외). 즐겨쓰기를 앞으로."""
        favs = set(self.favorites)
        hits = [s for s in self.stickers if not s.stale and label in s.tags]
        hits.sort(key=lambda s: s.ref not in favs)  # 즐겨쓰기 우선(False<True)
        return hits


def merge_catalog(existing: StickerCatalog, scraped: list[Sticker]) -> StickerCatalog:
    """라이브 스크랩 결과를 기존 카탈로그에 증분 병합(새 객체 반환).

    - 새 (pack,index): 추가(tags 비어 → 라벨링 대상).
    - 기존: image/animated 갱신, tags/reviewed 보존, stale=False로 복구.
    - 기존에 있었는데 스크랩에 없음: stale=True(유저 매핑/검수 보존 위해 삭제 안 함).
    """
    old = existing.by_ref()
    scraped_refs = {s.ref for s in scraped}
    merged: dict[str, Sticker] = {}
    for sc in scraped:
        prev = old.get(sc.ref)
        if prev:
            merged[sc.ref] = prev.model_copy(
                update={"image": sc.image or prev.image, "animated": sc.animated, "stale": False}
            )
        else:
            merged[sc.ref] = sc
    # 스크랩에 없는 기존 것은 stale로 남긴다
    for ref, s in old.items():
        if ref not in scraped_refs:
            merged[ref] = s.model_copy(update={"stale": True})
    ordered = sorted(merged.values(), key=lambda s: (s.pack, s.index))
    # 사라진(stale) 스티커를 가리키는 즐겨쓰기는 유지(되살아날 수 있음)
    return StickerCatalog(stickers=ordered, favorites=existing.favorites)


class StickerPicker:
    """초안 마커 [스티커:label] → 스티커 해석. 한 글 내 중복 회피 + 팩 통일성 옵션.

    consistent=True면 글 전체에서 한 팩으로 고정(통일감). prefer_pack이 있으면 그 팩 우선.
    label이 빈 문자열이면 즐겨쓰기에서 고른다.
    """

    def __init__(
        self,
        catalog: StickerCatalog,
        prefer_pack: str | None = None,
        consistent: bool = False,
    ):
        self.catalog = catalog
        self.prefer_pack = prefer_pack
        self.consistent = consistent
        self._locked_pack: str | None = prefer_pack
        self._used: list[str] = []  # 이미 쓴 ref(연속 중복 회피)

    def _candidates(self, label: str) -> list[Sticker]:
        if label:
            cands = self.catalog.find(label)
        else:  # 라벨 없는 [스티커] → 즐겨쓰기
            by_ref = self.catalog.by_ref()
            cands = [by_ref[r] for r in self.catalog.favorites if r in by_ref and not by_ref[r].stale]
        pack = self._locked_pack
        if pack:
            same = [s for s in cands if s.pack == pack]
            if same:  # 통일성: 같은 팩 후보가 있으면 그쪽만
                cands = same
        return cands

    def pick(self, label: str) -> Sticker | None:
        """label에 맞는 스티커 1개 선택(없으면 None). 같은 글에서 반복 시 다른 스티커."""
        cands = self._candidates(label.strip())
        if not cands:
            return None
        fresh = [s for s in cands if s.ref not in self._used]
        chosen = (fresh or cands)[0]
        self._used.append(chosen.ref)
        if self.consistent and self._locked_pack is None:
            self._locked_pack = chosen.pack
        return chosen


# --- 초안 지시문 (LLM이 [스티커:상황] 마커 emit) ---
def build_sticker_instruction(labels: list[str]) -> str | None:
    """보유 스티커 상황 라벨 목록 → 초안 지시문(EMPHASIS_INSTRUCTION 패턴).

    LLM이 없는 상황을 지어내지 않도록 실제 보유 라벨만 노출한다. 라벨 없으면 None.
    """
    labels = [str(label).strip() for label in labels if str(label).strip()]
    if not labels:
        return None
    shown = ", ".join(labels[:40])
    return (
        "[스티커]\n"
        "감정/분위기를 살리고 싶은 지점에 아래 상황 중 하나로 [스티커:상황] 을 그 줄에 단독으로 넣으세요.\n"
        f"- 사용 가능한 상황: {shown}\n"
        "목록에 없는 상황은 쓰지 말고, 글 전체에서 2~4개로 절제하세요. 한 문단에 연속으로 넣지 마세요."
    )


# --- YAML IO (유저 검수 파일) ---
def load_sticker_catalog(path: Path | None = None) -> StickerCatalog:
    """카탈로그 로드(config/stickers.yaml). 없으면 빈 카탈로그."""
    path = path or STICKER_CONFIG_PATH
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return StickerCatalog()
    return StickerCatalog(**data)


def save_sticker_catalog(catalog: StickerCatalog, path: Path | None = None) -> None:
    """카탈로그를 YAML로 저장(유저가 열어 검수·수정)."""
    path = path or STICKER_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(catalog.model_dump(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# --- 비전 자동 라벨링 ---
STICKER_LABEL_PROMPT = (
    "이 이미지는 블로그용 스티커(이모티콘) 한 개입니다. "
    "어떤 감정/상황에 쓰면 좋을지 한국어 태그로 JSON만 답하세요. "
    '형식: {"tags":["기쁨","좋아요"],"text":"스티커에 적힌 문구(있으면)"}\n'
    "tags는 2~4개, 감정(기쁨/슬픔/놀람/사랑/화남 등)이나 상황(인사/감사/맛있음/추천/질문/마무리 등) "
    "위주로 짧게. 스티커에 글자가 있으면 그 의미도 반영하세요."
)


def label_sticker(image_path: str, model: str | None = None) -> list[str]:
    """스티커 이미지 1개 → 감정/상황 태그 목록(비전 모델)."""
    from autoblog.vision import _ollama_vision, default_vision_model

    model = model or default_vision_model()
    data = Path(image_path).read_bytes()
    content = _ollama_vision(STICKER_LABEL_PROMPT, [data], model)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    tags = parsed.get("tags") if isinstance(parsed, dict) else None
    out: list[str] = []
    if isinstance(tags, list):
        for t in tags:
            t = str(t).strip()
            if t and t not in out:
                out.append(t)
    text = parsed.get("text") if isinstance(parsed, dict) else None
    if isinstance(text, str) and text.strip() and text.strip() not in out:
        out.append(text.strip())
    return out


def label_catalog(
    catalog: StickerCatalog, model: str | None = None, only_new: bool = True
) -> StickerCatalog:
    """카탈로그의 스티커들에 비전 태그 자동 부여(새 객체 반환).

    only_new=True면 태그가 비었고 검수 안 된 스티커만 라벨링(증분, 검수 보존).
    """
    updated: list[Sticker] = []
    for s in catalog.stickers:
        skip = s.stale or not s.image or (only_new and (s.tags or s.reviewed))
        if skip:
            updated.append(s)
            continue
        img = s.image if Path(s.image).is_absolute() else str(REPO_ROOT / s.image)
        try:
            tags = label_sticker(img, model)
        except Exception:  # noqa: BLE001 - 라벨링 실패해도 카탈로그는 유지
            tags = []
        updated.append(s.model_copy(update={"tags": tags or s.tags}))
    return StickerCatalog(stickers=updated, favorites=catalog.favorites)
