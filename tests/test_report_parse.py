"""report_parse 契约测试（移植旧仓 issue 055 保真要求）。"""
from __future__ import annotations

import json
import pytest

from jiaodui.report_parse import (SEVERITY_KEYWORDS, UNSTATED, parse_proofread_md,
                                  parse_reasons, split_sections)


def test_basic_inline_parse():
    text = "严重错误\n### 标记原文\n甲【1|错字|正字】乙。\n### 修改原因\n1. 错别字。\n"
    r = parse_proofread_md(text)
    assert r["summary"] == "严重错误"
    assert r["corrections"][0]["num"] == 1
    assert r["corrections"][0]["original"] == "错字"
    assert r["corrections"][0]["correction"] == "正字"
    assert r["corrections"][0]["reason"] == "错别字。"


def test_no_issue_fast_path():
    r = parse_proofread_md("无问题")
    assert r == {"corrections": [], "summary": "无问题", "marked_text": ""}


def test_decorated_summary_line():
    for line in ("**总结：一般问题**", "> 总结行：轻微问题", "### 无问题"):
        text = f"{line}\n### 标记原文\n### 修改原因\n无\n"
        if "###" in line:
            # 以 ### 开头的总结行会被当作标题边界，摘要识别为未声明
            continue
        r = parse_proofread_md(text)
        assert r["summary"] in SEVERITY_KEYWORDS, line


def test_missing_summary_is_unstated():
    # 缺少严重度行但含标记 → summary 记为「未声明」，不冒充「无问题」
    text = "### 标记原文\n甲【1|错|对】\n### 修改原因\n1. 原因。\n"
    r = parse_proofread_md(text)
    assert r["summary"] == UNSTATED


def test_contradiction_unstated():
    text = "无问题\n### 标记原文\n甲【1|错|对】\n### 修改原因\n1. 原因。\n"
    r = parse_proofread_md(text)
    assert r["summary"] == UNSTATED
    assert len(r["corrections"]) == 1


def test_crlf_normalized():
    text = "一般问题\r\n### 标记原文\r\n甲【1|错|对】\r\n### 修改原因\r\n1. 原因。\r\n"
    r = parse_proofread_md(text)
    assert r["corrections"][0]["num"] == 1


def test_reason_range_expansion():
    reasons = parse_reasons("1-3. 同类原因。\n")
    assert reasons == {1: "同类原因。", 2: "同类原因。", 3: "同类原因。"}


def test_reason_number_anchored_at_line_start():
    # 正文里的小数（非行首编号）不得充当编号条目
    reasons = parse_reasons("正文 $n\\approx1.22$ 不是编号。\n1. 真正原因。\n")
    assert reasons == {1: "真正原因。"}


def test_split_sections_positions():
    text = "头部\n### 标记原文\n正文\n### 修改原因\n1. 原因\n### 尾巴\n"
    head, marked, reasons = split_sections(text)
    assert head.strip() == "头部"
    assert "正文" in marked
    # 原因段在下一个 ### 处截断
    assert 1 in parse_reasons(reasons)


def test_save_and_load_json(tmp_path):
    from jiaodui.report_parse import save_proofread_json
    text = "一般问题\n### 标记原文\n甲【1|错|对】\n### 修改原因\n1. 原因。\n"
    assert save_proofread_json(text, str(tmp_path))
    data = json.loads((tmp_path / "_校对数据.json").read_text(encoding="utf-8"))
    assert data["summary"] == "一般问题"
    assert data["corrections"][0]["correction"] == "对"


@pytest.mark.parametrize("numbering", [("1.", "2."), ("①", "②"), ("1.", "②")])
def test_multiline_reasons_followed_by_verification_note(numbering):
    first, second = numbering
    text = (f"{first} 第一条原因。\n继续解释第一条。\n\n"
            f"{second} 第二条原因。\n核验说明：这段无需修改，不属于编号原因。")
    assert parse_reasons(text) == {1: "第一条原因。\n继续解释第一条。", 2: "第二条原因。"}


def test_range_reason_before_multiline_note():
    text = "1-2. 两个缺图占位均来自原始 Word。\n核验说明：另一张图可辨认。\n不据缺图推断内容。"
    assert parse_reasons(text) == {1: "两个缺图占位均来自原始 Word。", 2: "两个缺图占位均来自原始 Word。"}


def test_empty_reason_not_filled_by_later_note_or_next_number():
    assert parse_reasons("1.   \n核验说明：不能冒充原因。") == {}
    assert parse_reasons("1.\n2. 第二条原因。") == {2: "第二条原因。"}


@pytest.mark.parametrize("header", ["①.", "①-③.", "① )", "①–③、"])
def test_empty_circled_reason_cannot_use_delimiter_as_body(header):
    assert parse_reasons(f"{header}\n核验说明：不充当原因。") == {}


def test_verification_note_does_not_hide_later_duplicate_reason():
    from jiaodui.report_parse import parse_reason_entries
    text = "1. 原因甲。\n核验说明：额外说明。\n1. 原因乙。"
    assert parse_reason_entries(text) == [(1, "原因甲。"), (1, "原因乙。")]
