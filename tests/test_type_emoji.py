"""_type_with_keycaps — 결합 이모지를 쪼개 치지 않는다(브라우저 없이 키 입력만 기록해 검사).

2026-08-19 실사고: '…적혀 있어요 👍🏻' 다음 줄이 같은 문단으로 붙어 저장 전 관문에 걸렸다.
원인은 피부톤 이모지(👍+U+1F3FB)가 코드포인트 단위로 쪼개져 두 번에 나눠 입력된 것 —
키캡(1️⃣)만 통째로 넣고 나머지 결합 이모지는 빠져 있었다.
"""

import re

from autoblog.publish.editor import BlogPublisher

# 한 글자를 이루려고 앞 글자에 붙는 결합자 — 이게 앞 글자와 떨어져 입력되면 결합이 깨진다.
_JOINERS = re.compile(r"[︎️⃣‍\U0001F3FB-\U0001F3FF]")


class _FakeKeyboard:
    def __init__(self, log):
        self._log = log

    def type(self, text, delay=None):
        self._log.append(("type", text))

    def insert_text(self, text):
        self._log.append(("insert", text))


class _FakePage:
    def __init__(self):
        self.log: list[tuple[str, str]] = []
        self.keyboard = _FakeKeyboard(self.log)

    def wait_for_timeout(self, ms):
        pass


def _record(text: str) -> list[tuple[str, str]]:
    """브라우저 없이 _type_with_keycaps를 돌려 (방식, 문자열) 입력 기록을 받는다."""
    pub = BlogPublisher.__new__(BlogPublisher)  # __init__(플레이라이트 기동) 건너뜀
    pub._page = _FakePage()
    pub._type_with_keycaps(text)
    return pub._page.log


def _assert_clusters_intact(text: str):
    """결합자가 든 조각은 반드시 insert 한 번으로 통째 들어가야 한다."""
    for how, chunk in _record(text):
        if how == "type":
            assert not _JOINERS.search(chunk), f"결합 이모지가 쪼개져 타이핑됨: {chunk!r}"


def test_skin_tone_emoji_goes_in_one_piece():
    text = "포장에 친절하게 적혀 있어요 👍🏻\n이런 안내 은근히 고맙죠"
    _assert_clusters_intact(text)
    log = _record(text)
    assert ("insert", "👍🏻") in log
    # 이모지 뒤 줄바꿈이 그대로 남아야 문단이 갈라진다(붙으면 저장 전 관문에 걸린다)
    assert any(how == "type" and chunk.startswith("\n") for how, chunk in log)


def test_zwj_and_variation_selector_stay_whole():
    _assert_clusters_intact("가족 👩‍👧 이야기\n하트 ❤️ 하나")


def test_keycap_normalized_to_color_form():
    log = _record("1️⃣ 베이스\n2⃣ 쌈장")
    inserts = [chunk for how, chunk in log if how == "insert"]
    assert inserts == ["1️⃣", "2️⃣"]  # 변이 선택자 없는 2⃣도 표준형으로


def test_plain_text_and_single_emoji_untouched():
    # 단일 코드포인트 이모지는 결합이 없어 기존대로 한 글자씩 — 쪼갤 게 없다
    log = _record("괜히 신뢰가 갔어요 ✨\n다음 줄")
    assert log == [("type", "괜히 신뢰가 갔어요 ✨\n다음 줄")]


def test_nothing_is_lost_or_duplicated():
    text = "첫 줄 👍🏻\n둘째 줄 🌽\n1️⃣ 셋째 줄 ✅"
    assert "".join(chunk for _, chunk in _record(text)) == text
