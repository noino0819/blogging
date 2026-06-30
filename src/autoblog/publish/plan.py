"""게시 플랜 — 초안(DraftResult) → 에디터에 넣을 블록 시퀀스 (순수 변환, 테스트 가능).

본문을 [사진] 마커 기준으로 텍스트/이미지 블록으로 나누고, 강조 span을
해당 텍스트 블록에 배분한다. 이 플랜을 editor가 Smart Editor에 주입한다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

import yaml

from autoblog.collect.fact_card import PhotoItem
from autoblog.config import CONFIG_DIR
from autoblog.draft.generate import DraftResult
from autoblog.publish.emphasis import EmphasisStyle, StyledSpan
from autoblog.publish.stickers import StickerPicker

PHOTO_MARKER = "[사진]"
# [사진] / [사진:음식] — 라벨로 어떤 사진을 그 자리에 놓을지 지정 가능
_PHOTO_RE = re.compile(r"^\[사진(?::(.+?))?\]$")
_VIDEO_RE = re.compile(r"^\[영상(?::(.+?))?\]$")  # 동영상 마커(사진과 동일 규칙, media_kind=video만 매칭)
# 협찬 고지 사진 라벨 — 이 라벨이 붙은 사진은 본문 '첫 이미지'로 끌어올린다(최상단 고지).
SPONSOR_PHOTO_LABEL = "협찬"
QUOTE_CLOSE = "[/인용구]"
# [구분선] / [구분선:2], [인용구] / [인용구:3] — 종류(variant) 선택 가능
_DIVIDER_RE = re.compile(r"^\[구분선(?::(\d+))?\]$")
_QUOTE_OPEN_RE = re.compile(r"^\[인용구(?::(\d+))?\]$")
# [스티커] / [스티커:상황] — picker가 라벨을 (팩,인덱스)로 해석
_STICKER_RE = re.compile(r"^\[스티커(?::(.+?))?\]$")
# [지도] / [지도:가게명] — SE 네이티브 '장소' 카드(주소·지도 미리보기)로 삽입.
# 이름 생략 시 build_publish_plan(place_query=)로 받은 수집된 가게명을 쓴다.
_PLACE_RE = re.compile(r"^\[지도(?::\s*(.+?))?\]$")

# 구분선/인용구 종류 메타 — value(에디터 data-value) → (variant 인덱스, 이름, 어느 상황에 쓰면 좋은지)
# 라이브 캡쳐한 모양을 보고 작성. UI에 이름·용도 노출, 초안 LLM에 상황 안내, 마커 [구분선:이름] 해석에 사용.
DIVIDER_META = {
    "default": (1, "기본 가는 선", "가장 무난한 화제 전환. 어디에나 어울림"),
    "line1": (2, "실선", "깔끔하고 또렷한 구분. 단락이 확실히 바뀔 때"),
    "line2": (3, "굵은 짧은 선", "강한 전환·소제목 느낌. 챕터를 크게 나눌 때"),
    "line3": (4, "가운데 꺾인 선", "부드러운 전환. 감성적인 흐름 사이"),
    "line4": (5, "다이아몬드 선", "장식적·포인트. 특별한 구간을 나눌 때"),
    "line5": (6, "점선", "가볍게 끊기. 부연·메모로 살짝 넘어갈 때"),
    "line6": (7, "사선", "캐주얼한 분위기 전환. 가벼운 글에"),
    "line7": (8, "세로선", "짧은 좌우 구분(드물게). 나란히 비교할 때"),
}
QUOTE_META = {
    "default": (1, "기본(큰따옴표)", "감성·감상을 담은 핵심 한마디를 큰따옴표로 가운데 크게. 강조하고 싶은 감상·메시지는 이걸 씀(밑줄형 아님)"),
    "quotation_line": (2, "왼쪽 줄", "남의 말·출처 있는 인용문을 담백하게. 내 감상 아닌 인용"),
    "quotation_bubble": (3, "말풍선", "대화체·혼잣말 코멘트. 말 거는 듯한 한마디"),
    "quotation_underline": (4, "밑줄형", "감상 아닌 정보성 요점·결론을 한 줄로 또박또박 정리(사실·포인트용, 감정 강조 아님)"),
    "quotation_postit": (5, "포스트잇", "본문 흐름 밖 곁다리 팁·꿀팁 메모. '알아두면 좋은' 정보"),
    "quotation_corner": (6, "모서리", "글을 닫는 여운 있는 마무리 멘트"),
}
# 에디터에서 가운데정렬이 기본 모양인 인용구 종류(variant 인덱스). 왼쪽줄(2)·밑줄형(4)은
# 왼쪽정렬이 기본·고정이라 가운데정렬을 주면 미리보기·에디터 둘 다 어긋난다.
_QUOTE_CENTERED_VARIANTS = {1, 3, 5, 6}


def quote_align(variant: int) -> str | None:
    """인용구 종류에 맞는 단락 정렬(가운데형은 center, 왼쪽줄·밑줄형은 None=왼쪽)."""
    return "center" if variant in _QUOTE_CENTERED_VARIANTS else None

# 초안 구조 마커: 구분선 [구분선], 인용 블록 [인용구]…[/인용구]
# (EMPHASIS_INSTRUCTION과 같은 추가 레이어. generate_draft(structure=True)에서 시스템 프롬프트에 덧붙임)
# 14b 모델은 "절제" 위주로 안내하면 마커를 아예 안 단다(라이브 측정: 0/0/0).
# "권장이 아니라 사용 + 예시 + 개수 지정"으로 바꾸니 화제전환 있는 글에서 실제로 emit됨.
def build_structure_instruction(
    divider_keys: list[str] | None = None,
    quote_keys: list[str] | None = None,
) -> str:
    """구조 마커 지시문 — 유저가 '서식'에서 고른 구분선/인용구 종류만 쓰도록 안내.

    divider_keys/quote_keys는 DIVIDER_META/QUOTE_META 키 목록(비우면 기본 한 종류).
    여러 종류를 고르면 종류별 번호·용도를 나열하고 [구분선:번호]/[인용구:번호] 로 상황에 맞게
    고르게 한다(목록 밖 종류·번호 금지). 한 종류면 번호 없이 [구분선]/[인용구] 만 쓰게 한다(종류 자동).
    """
    dkeys = [k for k in (divider_keys or ["default"]) if k in DIVIDER_META] or ["default"]
    qkeys = [k for k in (quote_keys or ["default"]) if k in QUOTE_META] or ["default"]

    def menu(keys, meta, marker):
        return "\n".join(f"  · [{marker}:{meta[k][0]}] {meta[k][1]} — {meta[k][2]}" for k in keys)

    if len(dkeys) == 1:
        divider_line = "- 화제가 바뀌는 문단 사이에 [구분선] 을 한 줄로 1~2번 넣으세요(종류는 자동).\n"
        d_open = "[구분선]"
    else:
        divider_line = (
            "- 화제가 바뀌는 문단 사이에 구분선을 한 줄로 1~2번 넣으세요. "
            "아래 고른 종류 중 상황에 맞는 걸 골라 번호까지 붙이세요(여기 없는 종류·번호는 절대 쓰지 마세요):\n"
            f"{menu(dkeys, DIVIDER_META, '구분선')}\n"
        )
        d_open = f"[구분선:{DIVIDER_META[dkeys[0]][0]}]"

    if len(qkeys) == 1:
        quote_line = (
            "- 글 전체를 관통하는 핵심 메시지·감상 '한마디'가 있을 때만 그 한 문장을 [인용구] 와 [/인용구] 로 "
            "감싸세요(없으면 넣지 마세요, 최대 1번).\n"
        )
        q_open = "[인용구]"
    else:
        quote_line = (
            "- 글 전체를 관통하는 핵심 메시지·감상 '한마디'가 있을 때만 그 한 문장을 인용구로 "
            "감싸세요(없으면 넣지 마세요, 최대 1번). 여는 줄은 아래 고른 종류 중 상황에 맞는 걸 골라 "
            "번호까지 붙이고(여기 없는 종류·번호 금지), 닫는 줄은 [/인용구] 로 두세요:\n"
            f"{menu(qkeys, QUOTE_META, '인용구')}\n"
        )
        q_open = f"[인용구:{QUOTE_META[qkeys[0]][0]}]"

    return (
        "[구조 마커] — 아래 마커를 본문에 실제로 넣어 글을 읽기 좋게 나누세요(권장이 아니라 사용).\n"
        f"{divider_line}"
        f"{quote_line}"
        "  인용구 안의 한마디도 한 줄에 짧은 절 하나씩 2~3줄로 끊어 쓰세요(본문 줄바꿈 규칙 동일).\n"
        "  음식·분위기를 묘사하는 짧은 카피성 문구(예: '겉은 바삭 속은 촉촉')는 인용구로 만들지 말고, "
        '강조하려면 본문 안에서 큰따옴표(" ")로 감싸 쓰세요.\n'
        f"예시:\n오늘 다녀온 첫 소감 문단.\n\n{d_open}\n\n"
        f"{q_open}\n겉은 바삭 속은 촉촉\n두 번 세 번 와도 안 질릴 곳\n[/인용구]\n\n다음 문단.\n"
        "마커는 화면에 글자로 안 보이고 서식으로 바뀝니다. 문장 안에 섞지 말고 줄 단독으로 두세요."
    )


# 기본(한 종류) 지시문 — 종류 미지정 호출·프롬프트 미리보기 등에서 재사용.
STRUCTURE_INSTRUCTION = build_structure_instruction()


def build_place_instruction() -> str:
    """장소(지도) 마커 지시문 — 맛집 글에서 위치 안내 자리에 지도 카드를 넣게 안내."""
    return (
        "[지도] 가게 위치를 안내하는 자리(보통 '상세 정보 및 위치' 섹션)에 [지도] 를 그 줄에 "
        "혼자 한 번 넣으세요(권장이 아니라 사용). 시스템이 네이버 '장소'를 검색해 지도 카드"
        "(주소·지도 미리보기)로 바꿉니다.\n"
        "- [지도] 는 한 글에 한 번만, 위치를 설명한 문장 바로 아래 줄에 단독으로.\n"
        "- 가게명은 시스템이 알아서 넣으니 [지도] 만 쓰면 됩니다(이름을 직접 적지 마세요).\n"
        "- 마커는 화면에 글자로 안 보이고 지도 카드로 바뀝니다. 문장 안에 섞지 마세요."
    )


# --- 구조별 서식 템플릿 (config/structure_styles.yaml) ---
# 대제목·소제목·해시태그 줄을 패턴으로 인식해 서체/크기/색을 자동 배정한다.
# 마커가 아니라 패턴 인식이라, 외부 챗봇에서 받아온 글에도 동일하게 먹는다.
_STRUCTURE_STYLES_PATH = CONFIG_DIR / "structure_styles.yaml"

# "1. 가게명 후기" 소제목 / 해시태그 줄 인식
_SUBHEADING_RE = re.compile(r"^\d+\.\s+\S")


class RoleStyle(BaseModel):
    font: str | None = None
    size: int | None = None
    color: str | None = None
    align: str | None = None  # 단락 정렬: left/center/right/justify (None=기본 왼쪽)

    def to_style(self) -> EmphasisStyle:
        return EmphasisStyle(
            text_color=self.color,
            font_family=self.font,
            font_size=str(self.size) if self.size else None,
        )


class HashtagStyle(RoleStyle):
    per_line: int = 2  # 한 줄에 태그 N개씩
    divider: str | None = None  # 해시태그 뒤 구분선 종류(DIVIDER_META 키)


class StructureStyles(BaseModel):
    big_title: RoleStyle = Field(default_factory=RoleStyle)
    subheading: RoleStyle = Field(default_factory=RoleStyle)
    hashtags: HashtagStyle = Field(default_factory=HashtagStyle)
    # 협찬 토글 ON 시 본문 맨 위에 고정 삽입할 고지 스티커 "팩코드:인덱스" (예: ogq_a:3). 비우면 안 넣음.
    sponsor_sticker: str = ""

    def sponsor_ref(self) -> tuple[str, int] | None:
        """sponsor_sticker("팩:인덱스") → (pack, index). 형식이 어긋나면 None."""
        pack, _, idx = self.sponsor_sticker.partition(":")
        if pack and idx.isdigit():
            return pack, int(idx)
        return None


def load_structure_styles(path=None) -> StructureStyles:
    """구조별 서식 템플릿 로드(사용자 편집 파일). 없으면 빈 기본값."""
    path = path or _STRUCTURE_STYLES_PATH
    try:
        data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except FileNotFoundError:
        return StructureStyles()
    return StructureStyles(**data)


def _is_hashtag_line(s: str) -> bool:
    """해시태그가 2개 이상인 줄(헤더의 태그 묶음). 본문 속 우연한 # 한 개는 제외."""
    return sum(1 for t in s.split() if t.startswith("#")) >= 2


class PublishBlock(BaseModel):
    kind: str  # "text" | "image" | "video" | "divider" | "quote" | "sticker" | "place" | "link"
    text: str = ""
    link_url: str = ""  # 링크 카드(oglink) URL — 쿠팡파트너스 등
    keep_url_text: bool = False  # 협찬 링크: 카드 밑 'URL 텍스트 줄'을 지우지 말고 남김(크롤러 인식용)
    emphases: list[StyledSpan] = Field(default_factory=list)
    image_path: str | None = None
    image_label: str = ""
    image_size: str | None = None  # 이미지 표시 크기 힌트: "small"(협찬 고지 사진 등). None=기본
    variant: int = 1  # 구분선/인용구 종류(1=기본)
    sticker_pack: str | None = None  # 스티커 팩 코드(picker 해석 결과)
    sticker_index: int | None = None  # 스티커 data-index
    align: str | None = None  # 단락 정렬: center/right/justify (None=기본 왼쪽)
    place_address: str | None = None  # 장소 카드: 수집 도로명 주소(검색 결과 매칭용)


class PublishPlan(BaseModel):
    title: str
    blocks: list[PublishBlock] = Field(default_factory=list)


def build_publish_plan(
    draft: DraftResult,
    photos: list[PhotoItem] | None = None,
    picker: StickerPicker | None = None,
    divider_variant: int = 1,
    quote_variant_default: int = 1,
    structure_styles: StructureStyles | None = None,
    place_query: str | None = None,
    place_address: str | None = None,
    sponsor: bool = False,
    sponsor_links: list[str] | None = None,
    product_links: list[str] | None = None,
    sponsor_sticker: str = "",
    sticker_catalog=None,
    inplace: bool = False,
) -> PublishPlan:
    """초안 → 게시 플랜 (줄 단위 마커 파싱).

    inplace=True(임시저장 글 in-place 편집)면 사진은 이미 글에 박혀 있어 '위치를 옮기는'
    후처리(남은 사진 분산·협찬 사진 끌어올림·대표 썸네일 끌어올림)를 모두 건너뛴다.
    이미지 블록은 마커 순서 그대로 남아 실행기가 image_path로 원본 사진 위치에 매핑한다.

    첫 비어있지 않은 줄=제목. 본문에서 마커를 블록으로 분리:
    - [사진]/[사진:라벨] → 이미지(라벨 같은 사진 우선, 없으면 남은 순서대로)
    - [구분선]    → 구분선
    - [인용구]…[/인용구] → 인용 블록
    - [스티커:상황] → picker가 (팩,인덱스)로 해석한 스티커(picker 없거나 미해석이면 무시)
    그 외 줄은 텍스트 문단으로 누적. 강조 span은 해당 텍스트 블록에 배분.

    sponsor=True면 structure_styles.sponsor_sticker(쿠팡파트너스 고지 스티커)를 본문 맨 위
    블록으로 고정 삽입한다. 지정값은 '태그 이름'(예: 파트너스) 또는 'pack:index'. 태그면
    sticker_catalog에서 찾아 해석한다(카탈로그 없으면 pack:index만 인식). 못 찾으면 건너뜀.
    sponsor_links를 주면 그 URL들을 링크 카드로 본문 텍스트 사이 고른 위치에 분산 삽입한다.
    product_links(상품 리뷰의 필수 링크)도 같은 방식으로 카드 삽입한다(협찬과 무관, 각 한 번씩).
    """
    photos = list(photos or [])
    lines = draft.text.split("\n")

    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            title = line.strip()
            body_start = i + 1
            break
    body_lines = lines[body_start:]

    blocks: list[PublishBlock] = []
    text_buf: list[str] = []
    quote_buf: list[str] = []
    in_quote = False
    quote_variant = 1
    used = [False] * len(photos)  # 사진별 사용 여부(순서 아닌 라벨로 매칭)
    first_body_seen = False  # 대제목은 본문 첫 줄에만 부여

    def take_photo(label: str | None, media_kind: str = "image") -> PhotoItem | None:
        """media_kind(사진/영상)가 같은 것 중, 라벨이 같은 안 쓴 것 우선·없으면 순서대로. 다 쓰면 None."""
        if label:
            for i, ph in enumerate(photos):
                if not used[i] and ph.media_kind == media_kind and ph.label == label:
                    used[i] = True
                    return ph
        for i, ph in enumerate(photos):
            if not used[i] and ph.media_kind == media_kind:
                used[i] = True
                return ph
        return None

    def media_block(ph: PhotoItem) -> PublishBlock:
        """PhotoItem → 이미지/영상 블록(media_kind로 kind 결정, 경로·라벨 필드는 공용)."""
        kind = "video" if ph.media_kind == "video" else "image"
        return PublishBlock(kind=kind, image_path=ph.path, image_label=ph.caption or ph.label)

    def flush_text():
        text = "\n".join(text_buf).strip()
        text_buf.clear()
        if text:
            spans = [e for e in draft.emphases if e.text and e.text in text]
            blocks.append(PublishBlock(kind="text", text=text, emphases=spans, align="center"))

    def classify_role(s: str) -> str | None:
        """구조별 서식이 켜져 있을 때, 이 줄이 어떤 구조 요소인지 판정(없으면 None)."""
        if structure_styles is None:
            return None
        if _is_hashtag_line(s):
            return "hashtags"
        if _SUBHEADING_RE.match(s):
            return "subheading"
        if not first_body_seen and 0 < len(s) <= 40:
            return "big_title"  # 본문 첫 줄의 짧은 콘셉트 한 줄
        return None

    def emit_role_block(role: str, s: str):
        """구조 요소 한 줄을 서식 span이 박힌 텍스트 블록(+해시태그 뒤 구분선)으로 추가."""
        ss = structure_styles
        if role == "hashtags":
            toks = s.split()
            per = max(1, ss.hashtags.per_line)
            rows = [" ".join(toks[i : i + per]) for i in range(0, len(toks), per)]
            spans = [StyledSpan(text=r, preset_id=None, style=ss.hashtags.to_style()) for r in rows]
            blocks.append(
                PublishBlock(
                    kind="text", text="\n".join(rows), emphases=spans, align=ss.hashtags.align
                )
            )
            div = ss.hashtags.divider
            if div and div in DIVIDER_META:
                blocks.append(PublishBlock(kind="divider", variant=DIVIDER_META[div][0], align="center"))
            return
        if role == "subheading":
            # 소제목("1. ...")은 인용구 '밑줄형'으로 렌더한다. 텍스트로 "1. "을 본문에 치면
            # 에디터가 자동 번호목록을 켜서 뒤 문단까지 번호가 번지는데, 별도 인용구 블록으로
            # 빼면 그 누수가 사라지고 소제목도 또렷하게 강조된다(variant=밑줄형).
            # 밑줄형은 왼쪽정렬이 기본·고정이라 align은 따로 주지 않는다(중앙정렬 불가).
            blocks.append(
                PublishBlock(kind="quote", text=s, variant=QUOTE_META["quotation_underline"][0])
            )
            return
        role_style = ss.big_title
        span = StyledSpan(text=s, preset_id=None, style=role_style.to_style())
        blocks.append(
            PublishBlock(kind="text", text=s, emphases=[span], align=role_style.align or "center")
        )

    for line in body_lines:
        s = line.strip()
        if in_quote:
            if s == QUOTE_CLOSE:
                in_quote = False
                qtext = "\n".join(quote_buf).strip()
                quote_buf.clear()
                if qtext:
                    blocks.append(
                        PublishBlock(
                            kind="quote",
                            text=qtext,
                            variant=quote_variant,
                            align=quote_align(quote_variant),
                        )
                    )
            else:
                quote_buf.append(line)
            continue
        div_m = _DIVIDER_RE.match(s)
        quote_m = _QUOTE_OPEN_RE.match(s)
        sticker_m = _STICKER_RE.match(s)
        photo_m = _PHOTO_RE.match(s)
        video_m = _VIDEO_RE.match(s)
        place_m = _PLACE_RE.match(s)
        if place_m:
            flush_text()
            q = (place_m.group(1) or place_query or "").strip()
            if q:  # 가게명(마커 인자 우선, 없으면 수집된 이름)으로 장소 카드
                blocks.append(PublishBlock(kind="place", text=q, place_address=place_address))
        elif div_m:
            flush_text()
            blocks.append(
                PublishBlock(
                    kind="divider", variant=int(div_m.group(1) or divider_variant), align="center"
                )
            )
        elif sticker_m:
            flush_text()
            chosen = picker.pick(sticker_m.group(1) or "") if picker else None
            if chosen:  # 해석 실패(picker 없음/매칭 없음)면 마커 자체를 버림(본문 누수 방지)
                blocks.append(
                    PublishBlock(
                        kind="sticker", sticker_pack=chosen.pack, sticker_index=chosen.index
                    )
                )
        elif quote_m:
            flush_text()
            in_quote = True
            quote_variant = int(quote_m.group(1) or quote_variant_default)
        elif photo_m:
            flush_text()
            ph = take_photo(photo_m.group(1), media_kind="image")
            if ph is not None:
                blocks.append(media_block(ph))
        elif video_m:
            flush_text()
            ph = take_photo(video_m.group(1), media_kind="video")
            if ph is not None:
                blocks.append(media_block(ph))
        else:
            role = classify_role(s)
            if role:
                flush_text()
                emit_role_block(role, s)
            else:
                text_buf.append(line)
            if s:
                first_body_seen = True
    flush_text()
    if in_quote and quote_buf:  # 닫힘 누락 방어
        blocks.append(
            PublishBlock(kind="quote", text="\n".join(quote_buf).strip(), variant=quote_variant)
        )

    # 마커로 못 채운 남은 미디어(사진·영상): 글 끝에 몰지 않고 본문 텍스트 블록 사이에 고루 분산
    # (업로드한 사진·영상은 모두 본문에 들어가되, 끝에 우르르 붙는 걸 방지)
    leftover = [ph for i, ph in enumerate(photos) if not used[i]]
    if leftover:
        text_pos = [i for i, b in enumerate(blocks) if b.kind == "text"]
        if not text_pos:  # 본문 텍스트가 없으면 그대로 끝에
            for ph in leftover:
                blocks.append(media_block(ph))
        else:
            def trailing_end(idx: int) -> int:  # 텍스트 블록 뒤 마커 미디어(사진/영상)까지 건너뛴 위치
                while idx + 1 < len(blocks) and blocks[idx + 1].kind in ("image", "video"):
                    idx += 1
                return idx

            after: dict[int, list[PhotoItem]] = {}
            t = len(text_pos)
            for k, ph in enumerate(leftover):
                anchor = trailing_end(text_pos[(k * t) // len(leftover)])
                after.setdefault(anchor, []).append(ph)
            spread: list[PublishBlock] = []
            for i, b in enumerate(blocks):
                spread.append(b)
                for ph in after.get(i, []):
                    spread.append(media_block(ph))
            blocks = spread

    # 협찬 링크 카드 — 글 끝에 몰지 않고 본문 텍스트 사이 고른 '중간중간' 위치에 분산.
    # 텍스트 블록이 t개일 때 링크 i는 (i+1)/(n+1) 지점 텍스트 뒤에 — 맨 앞/맨 끝을 피해 가운데로.
    links = [u.strip() for u in [*(sponsor_links or []), *(product_links or [])] if u.strip()]
    # 협찬 링크(sponsor_links)는 카드 밑 URL 텍스트 줄을 남겨 체험단 크롤러가 잡게 한다.
    # 상품리뷰 링크(product_links)는 비협찬이라 지금처럼 깔끔하게(텍스트 줄 제거).
    sponsor_set = {u.strip() for u in (sponsor_links or []) if u.strip()}

    def link_block(url: str) -> PublishBlock:
        return PublishBlock(kind="link", link_url=url, keep_url_text=url in sponsor_set)

    if links:
        text_pos = [i for i, b in enumerate(blocks) if b.kind == "text"]
        if not text_pos:  # 본문 텍스트가 없으면 그대로 끝에
            for url in links:
                blocks.append(link_block(url))
        else:
            t = len(text_pos)
            last = t - 2 if t >= 3 else t - 1  # 텍스트 블록이 3개 이상이면 마지막 문단 뒤는 피함
            after: dict[int, list[str]] = {}
            for k, url in enumerate(links):
                anchor = text_pos[min(last, ((k + 1) * t) // (len(links) + 1))]
                after.setdefault(anchor, []).append(url)
            spread: list[PublishBlock] = []
            for i, b in enumerate(blocks):
                spread.append(b)
                for url in after.get(i, []):
                    spread.append(link_block(url))
            blocks = spread

    # 협찬 고지 스티커 — 본문 맨 위에 고정 삽입(제목 칸과 별개로 본문 첫 블록).
    # 우선순위: 글쓰기 화면에서 고른 sponsor_sticker > structure_styles.yaml 수동 지정 > catalog.sponsor.
    # 지정값이 태그명이면 카탈로그로 해석, 아니면 pack:index로 해석.
    if sponsor:
        spec = sponsor_sticker or ""
        if not spec and structure_styles is not None:
            spec = structure_styles.sponsor_sticker
        if not spec and sticker_catalog is not None:
            spec = getattr(sticker_catalog, "sponsor", "")  # 예전 스티커탭 지정(하위호환)
        ref = None
        if sticker_catalog is not None:
            ref = sticker_catalog.resolve_ref(spec)
        elif structure_styles is not None:
            ref = structure_styles.sponsor_ref()
        if ref:
            blocks.insert(0, PublishBlock(kind="sticker", sticker_pack=ref[0], sticker_index=ref[1]))

    # 협찬 고지 사진 — '협찬' 라벨 사진은 본문 '내용의 가장 맨 위'(인트로·헤더보다 위, 블록 0)로
    # 끌어올리고 가장 작은 크기로 표시한다. 마커([사진:협찬])를 어디에 넣었든, 또 대표 썸네일이
    # 따로 지정됐든 항상 맨 처음에 등장하게 보장한다.
    spon_paths = {ph.path for ph in photos if ph.label == SPONSOR_PHOTO_LABEL}
    if spon_paths:
        spon_blocks = [b for b in blocks if b.kind == "image" and b.image_path in spon_paths]
        if spon_blocks:
            for b in spon_blocks:
                b.image_size = "small"  # 협찬 고지 이미지는 가장 작게
            ids = {id(b) for b in spon_blocks}
            blocks = spon_blocks + [b for b in blocks if id(b) not in ids]

    # 대표 썸네일 — 지정 사진을 본문 '첫 이미지'로 끌어올린다(네이버 대표 사진=글의 첫 이미지).
    # 마커가 어디에 박히든 썸네일이 가장 먼저 등장하게 하되, 협찬 고지 사진보다는 뒤에 둔다.
    thumb_path = next((ph.path for ph in photos if ph.thumbnail and ph.path not in spon_paths), None)
    if thumb_path:
        img_idx = [i for i, b in enumerate(blocks) if b.kind == "image" and b.image_path not in spon_paths]
        first = img_idx[0] if img_idx else None
        cur = next((i for i in img_idx if blocks[i].image_path == thumb_path), None)
        if first is not None and cur is not None and cur != first:
            blocks.insert(first, blocks.pop(cur))

    return PublishPlan(title=title, blocks=blocks)
