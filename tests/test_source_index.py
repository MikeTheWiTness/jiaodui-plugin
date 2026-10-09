from __future__ import annotations

import hashlib

import pytest

from jiaodui.source_index import query_locations, resolve_location


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_repeated_phrase_returns_each_occurrence_and_location_is_bound_to_source():
    source = "木板甲。木板乙。木板丙。"
    digest = _digest(source)
    results = query_locations(source, digest, "木板")
    assert [item["match_index"] for item in results] == [1, 2, 3]
    assert len({item["location_id"] for item in results}) == 3
    third = resolve_location(source, digest, results[2]["location_id"], "木板")
    assert (third["start"], third["end"], third["original"]) == (8, 10, "木板")


def test_stale_source_hash_and_wrong_expected_text_are_rejected():
    original = "甲词乙"
    location = query_locations(original, _digest(original), "词")[0]["location_id"]
    with pytest.raises(ValueError) as stale:
        resolve_location("甲词乙。", _digest("甲词乙。"), location, "词")
    assert stale.value.code == "location.stale"
    with pytest.raises(ValueError) as mismatch:
        resolve_location(original, _digest(original), location, "其他")
    assert mismatch.value.code == "location.original-mismatch"


def test_unicode_offsets_use_codepoints_and_preserve_crlf_and_zero_width():
    source = "🙂e\u0301\u200b甲\r\n甲"
    digest = _digest(source)
    found = query_locations(source, digest, "甲")
    assert [(item["start"], item["end"], item["line"], item["column"]) for item in found] == [
        (4, 5, 1, 5), (7, 8, 2, 1)
    ]
    assert resolve_location(source, digest, found[0]["location_id"], "甲")["original"] == "甲"


def test_match_inside_math_or_bold_returns_whole_safe_span():
    source = "公式 $a+b$ 与 **重点词**。"
    results = query_locations(source, _digest(source), "b")
    assert results[0]["original"] == "$a+b$"
    bold = query_locations(source, _digest(source), "重点")
    assert bold[0]["original"] == "**重点词**"
    assert source[bold[0]["start"]:bold[0]["end"]] == "**重点词**"


def test_location_id_cannot_be_replayed_against_another_unit_source():
    one = "相同词句。"
    two = "不同词句。"
    loc = query_locations(one, _digest(one), "相同")[0]["location_id"]
    with pytest.raises(ValueError) as error:
        resolve_location(two, _digest(two), loc, "相同")
    assert error.value.code == "location.stale"
