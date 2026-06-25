from autoblog.publish.stickers import (
    Sticker,
    StickerCatalog,
    StickerPicker,
    build_sticker_instruction,
    load_sticker_catalog,
    merge_catalog,
    save_sticker_catalog,
)


def test_sticker_instruction_lists_labels():
    instr = build_sticker_instruction(["맛있음", "기쁨", "", "기쁨"])
    assert instr is not None
    assert "맛있음" in instr and "기쁨" in instr
    assert "[스티커:상황]" in instr
    assert build_sticker_instruction([]) is None
    assert build_sticker_instruction(["  "]) is None


def _cat():
    return StickerCatalog(
        stickers=[
            Sticker(pack="ogq_a", index=0, tags=["기쁨", "좋아요"], image="data/stickers/ogq_a/0.png"),
            Sticker(pack="ogq_a", index=1, tags=["기쁨"], image="data/stickers/ogq_a/1.png"),
            Sticker(pack="ogq_b", index=0, tags=["기쁨", "감사"], image="data/stickers/ogq_b/0.png"),
            Sticker(pack="ogq_b", index=5, tags=["슬픔"], image="data/stickers/ogq_b/5.png"),
        ],
        favorites=["ogq_b:0"],
    )


def test_merge_adds_new_preserves_old_marks_stale():
    existing = StickerCatalog(
        stickers=[
            Sticker(pack="ogq_a", index=0, tags=["기쁨"], reviewed=True, image="old.png"),
            Sticker(pack="ogq_a", index=9, tags=["옛날"]),  # 스크랩에 없음 → stale
        ],
        favorites=["ogq_a:0"],
    )
    scraped = [
        Sticker(pack="ogq_a", index=0, image="new.png", animated=True),  # 기존 → 태그/검수 보존
        Sticker(pack="ogq_a", index=1, image="n1.png"),  # 신규
    ]
    merged = merge_catalog(existing, scraped)
    by = merged.by_ref()
    # 기존 검수/태그 보존 + 이미지/animated 갱신 + stale 해제
    assert by["ogq_a:0"].tags == ["기쁨"] and by["ogq_a:0"].reviewed is True
    assert by["ogq_a:0"].image == "new.png" and by["ogq_a:0"].animated is True
    assert by["ogq_a:0"].stale is False
    # 신규는 태그 비어 라벨링 대상
    assert by["ogq_a:1"].tags == []
    # 스크랩에 없던 기존은 stale(삭제 안 함)
    assert by["ogq_a:9"].stale is True
    assert merged.favorites == ["ogq_a:0"]


def test_find_prioritizes_favorites_and_skips_stale():
    cat = _cat()
    hits = cat.find("기쁨")
    assert [s.ref for s in hits][0] == "ogq_b:0"  # 즐겨쓰기 우선
    assert {s.ref for s in hits} == {"ogq_a:0", "ogq_a:1", "ogq_b:0"}
    # stale 제외
    cat.stickers[0].stale = True
    assert "ogq_a:0" not in {s.ref for s in cat.find("기쁨")}


def test_picker_dedup_and_no_match():
    picker = StickerPicker(_cat())
    a = picker.pick("기쁨")
    b = picker.pick("기쁨")
    assert a.ref != b.ref  # 같은 라벨 반복 시 다른 스티커
    assert picker.pick("없는상황") is None


def test_picker_consistency_locks_pack():
    picker = StickerPicker(_cat(), consistent=True)
    first = picker.pick("기쁨")  # 즐겨쓰기 우선 → ogq_b:0
    assert first.pack == "ogq_b"
    # 통일성: 이후 같은 팩으로 고정. '감사'도 ogq_b에 있음
    assert picker.pick("감사").pack == "ogq_b"
    # ogq_b에 없는 라벨이면 후보가 없어 None
    assert picker.pick("슬픔").pack == "ogq_b"  # 슬픔=ogq_b:5 → 같은 팩 OK


def test_picker_empty_label_uses_favorites():
    picker = StickerPicker(_cat())
    s = picker.pick("")
    assert s.ref == "ogq_b:0"  # 즐겨쓰기


def test_labels_distinct_excludes_stale():
    cat = _cat()
    cat.stickers[3].stale = True  # 슬픔 제거
    labels = cat.labels()
    assert "기쁨" in labels and "감사" in labels and "좋아요" in labels
    assert "슬픔" not in labels


def test_yaml_round_trip(tmp_path):
    cat = _cat()
    p = tmp_path / "stickers.yaml"
    save_sticker_catalog(cat, p)
    loaded = load_sticker_catalog(p)
    assert loaded.model_dump() == cat.model_dump()
    # 없는 파일은 빈 카탈로그
    assert load_sticker_catalog(tmp_path / "none.yaml").stickers == []
