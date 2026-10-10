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


def test_original_mismatch_names_both_actual_and_expected_text():
    """诊断必须给出「命中的原文」与「调用方写入的期望值」，否则只能盲试。

    回放实测（第 11 讲 单元3）：子 agent 拿整条公式的 location_id 配上子片段，
    只得到一句「不一致」，用同一写法连撞 20 次提交后放弃该条修改并改报「无问题」。
    """
    source = "答案：$I_{6}=2\\,\\mathrm{N}\\times 4\\mathrm{s}+\\left(-2N\\right)\\times 2\\mathrm{s}$。"
    digest = _digest(source)
    whole = query_locations(source, digest, "I_{6}")[0]
    assert whole["original"].startswith("$I_{6}")

    with pytest.raises(ValueError) as mismatch:
        resolve_location(source, digest, whole["location_id"], "\\left(-2N\\right)")
    message = str(mismatch.value)
    # 原文以 repr 形式给出（反斜杠会被转义），因此断言 repr 而不是原始文本
    assert repr(whole["original"]) in message, "必须报出该 location_id 实际命中的原文"
    assert repr("\\left(-2N\\right)") in message, "必须报出调用方写入的 expected_original"
    assert "unit-locate" in message, "必须指出可照抄的来源"


def test_original_mismatch_truncates_long_text_but_keeps_length_hint():
    """错误信息会进入模型上下文：超长原文要截断，同时标出真实长度。"""
    long_text = "甲" * 200
    digest = _digest(long_text)
    location = query_locations(long_text, digest, long_text)[0]["location_id"]
    with pytest.raises(ValueError) as mismatch:
        resolve_location(long_text, digest, location, "乙")
    message = str(mismatch.value)
    assert len(message) < 600, "不允许把整段正文灌进错误信息"
    assert "共 200 字符" in message


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
