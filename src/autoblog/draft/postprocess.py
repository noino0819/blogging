"""포맷 후처리 — 결정적 규칙 강제 (기획서 §4.3 / stage 3).

모델이 베이스 프롬프트의 기계적 규칙을 어겨도 코드로 보정한다:
- 느낌표(!) → .ᐟ (제목 줄은 치환 대신 제거 — 검색 색인 보호, 대괄호 구간은 원형 보존)
- 물결표(~) → - (대괄호 구간·허용 카오모지 보호)
- 줄 앞 글머리 기호(•,*,▶,→,✓,✅,- ) 제거
- 마크다운 헤더(#) 마커 제거
- 명시적으로 금지된 흔한 이모지 제거
줄바꿈 스타일(한 줄 짧은 절) 등 의미 의존 규칙은 모델 몫으로 남긴다.
"""

from __future__ import annotations

import re

# 마크다운 헤더(# 뒤 공백 필수)만 제거. '#혜화맛집'처럼 # 뒤에 바로 글자가
# 오는 해시태그는 건드리지 않는다(헤더의 태그 묶음 보존).
_HEADER_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_BULLET_RE = re.compile(r"^[ \t]*[•*▶→✓✅][ \t]+", re.MULTILINE)
# 상품 리뷰의 추천 체크리스트(✅)/체크(✓)는 의도된 나열이라 보존한다.
_BULLET_RE_KEEP_CHECK = re.compile(r"^[ \t]*[•*▶→][ \t]+", re.MULTILINE)
_DASH_BULLET_RE = re.compile(r"^[ \t]*-[ \t]+", re.MULTILINE)
# 베이스 프롬프트가 금지한 흔한 감정형/장식 이모지(허용 목록 밖)
_FORBIDDEN_EMOJI = "💖💕❤️🔥😍🤤😋💯😊😄😁🥰😘🤩🥳😆👏🙌💪🍀🌟💫🤗😅😂🤣"
# 물결표(~)를 포함한 허용 이모지 — 치환 전 보호한다
_TILDE_EMOJI = "(๑´~ˋ๑)"
# 센티널은 NUL로 감싼다 — enforce_format 진입 시 입력의 NUL을 제거하므로 본문과 충돌 불가
# (예전 평문 센티널 'TILDE_EMOJI'는 입력에 같은 리터럴이 오면 카오모지로 둔갑했다)
_TILDE_SENTINEL = "\x00TILDE\x00"
# 금지 표현 → 완화 표현
_FORBIDDEN_PHRASES = {
    "강력 추천": "추천",
    "강력추천": "추천",
    "강력히 추천": "추천",
    "꼭 가보세요": "한 번 가보셔도 좋을 것 같아요",
    "꼭 가보시길": "가보셔도 좋을 것 같아요",
}

# 줄바꿈: 절 경계로 쓰는 연결어미(이 뒤에서 끊는다)
_CONNECTIVE_RE = re.compile(
    r"(거든요|더라구요|더라고요|는데요|은데요|인데요|지만|는데|어서|아서|면서|으며|니까|라서|구요|고요)(\s+)"
)


# 줄 맨 앞에 단독으로 오면 어색한 짧은 의존명사·단위(앞말과 안 끊는다)
_DEP_START = set("것 수 때 줄 등 점 뿐 채 척 적 개 번 분".split())
# 줄 끝에 단독으로 매달리면 어색한 짧은 수식어·부사(뒷말과 안 끊고 다음 줄로 내린다)
_ADV_END = set("아주 참 더 딱 좀 또 꼭 잘 안 못 늘 꽤 막 너무 정말 진짜 매우 가장 제일 살짝 한참 그냥".split())


def _greedy_wrap(segment: str, max_len: int) -> list[str]:
    """긴 절을 어절 단위로 '균형 있게' 줄바꿈(SNS 스타일).

    그리디로 max_len까지 꽉 채우면 마지막에 한두 어절만 남는 외톨이 줄이 생기고,
    짧은 어절을 무조건 앞줄에 붙이느라 줄이 30자를 넘기곤 했다. 대신 필요한 줄 수(k)를
    먼저 구해 목표 길이(total/k)로 고르게 나눈다 — 외톨이·초과 줄이 안 생긴다.
    경계 다듬기: 줄 맨 앞에 짧은 의존명사(것·수…)가 오면 앞말과 붙이고,
    줄 끝에 짧은 수식어(아주·참…)가 매달리면 그 말을 다음 줄로 내려 수식 대상과 붙인다.
    """
    total = len(segment)
    if total <= max_len + 2:  # 1~2자 초과는 쪼개면 더 잘게 끊겨 어색 — 그냥 둔다
        return [segment]
    words = segment.split(" ")
    k = max(1, (total + max_len - 1) // max_len)  # 필요한 줄 수
    target = (total + k - 1) // k  # 균형 목표 길이(≤ max_len)
    out: list[str] = []
    cur: list[str] = []
    cur_len = 0
    breaks_left = k - 1  # 남은 줄바꿈 횟수 — 다 쓰면 나머지는 마지막 줄로
    for word in words:
        add = len(word) + (1 if cur else 0)
        do_break = bool(cur) and cur_len + add > target and breaks_left > 0
        if do_break and len(word) <= 2 and word in _DEP_START:
            do_break = False  # 짧은 의존명사는 앞말과 안 끊음
        if do_break:
            carry: list[str] = []
            if len(cur) > 1 and cur[-1] in _ADV_END:
                carry = [cur.pop()]  # 줄 끝 수식어는 다음 줄로 내림
            out.append(" ".join(cur))
            breaks_left -= 1
            cur = [*carry, word]
            cur_len = sum(len(w) for w in cur) + (len(cur) - 1)
        else:
            cur.append(word)
            cur_len += add
    if cur:
        out.append(" ".join(cur))
    return out


def _wrap_line(line: str, max_len: int) -> list[str]:
    """긴 한 줄을 쉼표·연결어미·공백 기준으로 짧은 절로 분할."""
    if len(line) <= max_len:
        return [line]
    # 쉼표 뒤, 연결어미 뒤에서 1차 분할 (숫자 안 쉼표 '13,000'은 제외)
    marked = re.sub(r"(?<!\d)([,，])\s*", r"\1\n", line)
    marked = _CONNECTIVE_RE.sub(lambda m: m.group(1) + "\n", marked)
    pieces: list[str] = []
    for clause in marked.split("\n"):
        clause = clause.strip()
        if not clause:
            continue
        if len(clause) > max_len:
            pieces.extend(_greedy_wrap(clause, max_len))
        else:
            pieces.append(clause)
    return pieces


# 대괄호 구간([사진:라벨]·[지도]·본문 속 [ 가게명 ])은 문자 치환에서 보호한다 —
# 마커 라벨이나 고유명사 속 !/~가 치환되면 매칭·표기가 깨진다(예: '잇쇼우!').
_BRACKET_SEG_RE = re.compile(r"\[[^\[\]\n]*\]")


def _sub_special_chars(text: str) -> str:
    """느낌표→.ᐟ, 물결표→- 치환(대괄호 구간·허용 카오모지는 보호)."""
    segs: list[str] = []

    def _stash(m: re.Match) -> str:
        segs.append(m.group(0))
        return f"\x00B{len(segs) - 1}\x00"

    text = _BRACKET_SEG_RE.sub(_stash, text)
    text = text.replace("!", ".ᐟ")
    text = text.replace(_TILDE_EMOJI, _TILDE_SENTINEL)  # 허용 이모지 보호
    text = re.sub(r"~+", "-", text)
    text = text.replace(_TILDE_SENTINEL, _TILDE_EMOJI)
    for i, seg in enumerate(segs):
        text = text.replace(f"\x00B{i}\x00", seg)
    return text


def _clean_title_line(line: str) -> str:
    """제목(첫 줄)은 검색 결과에 그대로 노출된다 — 장식 문자는 치환 대신 제거.

    .ᐟ(U+141F)·〰️ 같은 변형 유니코드가 제목에 박히면 검색엔진이 일반 문자와 다른
    코드포인트로 취급해 키워드 매칭이 깨질 수 있다. 느낌표도 제목에서는 삭제.
    범위 표시 물결(3월~4월)은 제목에서 정상 표기라 건드리지 않고, 대괄호 구간
    ('[잇쇼우!] …')은 본문 보호 규칙과 동일하게 원형을 유지한다(제목-본문 표기 일치).
    """
    segs: list[str] = []

    def _stash(m: re.Match) -> str:
        segs.append(m.group(0))
        return f"\x00B{len(segs) - 1}\x00"

    line = _BRACKET_SEG_RE.sub(_stash, line)
    line = line.replace(".ᐟ", "").replace("ᐟ", "").replace("!", "")
    line = re.sub("〰️?", "", line)
    for i, seg in enumerate(segs):
        line = line.replace(f"\x00B{i}\x00", seg)
    return re.sub(r"[ \t]{2,}", " ", line).strip()


# 상품 리뷰의 나열 박스 표식으로 시작하는 줄은 한 항목이라 쪼개지 않는다.
# 키캡 숫자(1️⃣…)는 변이 선택자(U+FE0F) 유무가 입력마다 달라 정규식으로 너그럽게 매칭한다.
_LIST_LINE_RE = re.compile(r"^[ \t]*(?:[0-9]️?⃣|🔟|✅|✓|👉|🌟)")
# 상품 리뷰에서 구조 표식으로 쓰는 🌟은 금지 이모지 제거에서 예외로 둔다.
_PRODUCT_KEEP_EMOJI = "🌟"
# 핵심 요약 박스(키캡 줄)의 "소제목: 설명" 콜론을 em-dash로 바꾼다 — 콜론이 어색하다는 피드백.
# 키캡으로 시작하는 줄에만, 첫 콜론 하나만 적용한다(시간 표기·👉 구매처: 등 다른 콜론은 보존).
_KEYCAP_COLON_RE = re.compile(r"^([ \t]*[0-9]️?⃣[^\n:]*?)[ \t]*:[ \t]*", re.MULTILINE)


def wrap_long_lines(text: str, max_len: int = 30, *, keep_list_lines: bool = False) -> str:
    """긴 줄을 짧은 절 단위로 줄바꿈(SNS 스타일). 빈 줄(문단 간격)은 보존.

    첫 비어있지 않은 줄(=제목)은 쪼개지 않는다 — plan이 첫 줄만 제목으로 떼어내므로
    쉼표·길이로 분할되면 뒷부분이 본문으로 새어 나간다(쉼표 들어간 제목 보호).
    keep_list_lines=True(상품 리뷰)면 나열 박스 표식으로 시작하는 줄도 원형 유지한다."""
    out: list[str] = []
    title_seen = False
    for line in text.split("\n"):
        if not line.strip():
            out.append("")
        elif not title_seen:
            out.append(line)  # 제목 줄은 원형 유지
            title_seen = True
        elif sum(1 for t in line.split() if t.startswith("#")) >= 2:
            out.append(line)  # 해시태그 줄(2개 이상)은 쪼개지 않는다 — 헤더 태그 묶음
        elif keep_list_lines and _LIST_LINE_RE.match(line):
            out.append(line)  # 나열 박스 한 줄(키캡/✅/👉/🌟)은 쪼개지 않는다
        else:
            out.extend(_wrap_line(line, max_len))
    return "\n".join(out)


def enforce_format(
    text: str,
    wrap: bool = True,
    max_len: int = 30,
    *,
    allow_checklist: bool = False,
    ornaments: bool = True,
) -> str:
    """결정적 포맷 규칙을 강제 적용.

    allow_checklist=True(상품 리뷰)면 줄 앞 ✅/✓ 체크리스트 기호를 보존한다
    (1️⃣~ 키캡 이모지는 글머리 기호가 아니라 어느 모드에서도 보존됨).
    ornaments=False(발랄체가 아닌 어투)면 어투 결합 치환을 건너뛴다 — 본문 !→.ᐟ,
    ~→- 치환과 금지 이모지 제거는 기본 어투(발랄체)의 규칙이라, 유저가 고른 문체에
    코드가 기본어투를 다시 입히면 안 된다. 제목 정리·글머리 기호·줄바꿈은 포맷
    규칙이라 어투와 무관하게 항상 적용한다.
    """
    bullet_re = _BULLET_RE_KEEP_CHECK if allow_checklist else _BULLET_RE
    text = text.replace("\x00", "")  # NUL 제거 — 내부 센티널(\x00…)과의 충돌 차단
    text = _HEADER_RE.sub("", text)  # 마크다운 헤더 마커 제거
    text = bullet_re.sub("", text)  # 글머리 기호 제거
    text = _DASH_BULLET_RE.sub("", text)  # 줄 앞 '- ' 제거
    if wrap:  # 전체 문서 모드 — 첫 줄(제목)은 장식 문자 제거, 본문만 치환
        # lstrip()으로 공백-only 선행 줄까지 걷어내야 실제 제목이 첫 줄로 잡힌다
        # (wrap_long_lines의 제목 판정과 동일 기준).
        stripped = text.lstrip()
        title, sep, body = stripped.partition("\n")
        if ornaments:
            body = _sub_special_chars(body)
        text = _clean_title_line(title) + (sep + body if sep else "")
    elif ornaments:  # 강조 스팬 등 조각 정규화 — 제목 개념 없음
        text = _sub_special_chars(text)
    if ornaments:
        forbidden = _FORBIDDEN_EMOJI
        if allow_checklist:  # 상품 구조 표식(🌟)은 보존
            forbidden = forbidden.replace(_PRODUCT_KEEP_EMOJI, "")
        for ch in forbidden:
            text = text.replace(ch, "")
    for bad, good in _FORBIDDEN_PHRASES.items():  # 금지 표현 완화
        text = text.replace(bad, good)
    if allow_checklist:  # 상품: 키캡 요약 줄의 "소제목: 설명" 콜론 → em-dash
        text = _KEYCAP_COLON_RE.sub(r"\1 — ", text)
    if wrap:
        text = wrap_long_lines(text, max_len, keep_list_lines=allow_checklist)
    # 치환으로 생긴 줄 끝 공백 / 과도한 빈 줄 정리
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
