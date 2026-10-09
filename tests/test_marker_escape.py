"""ADR 0006：v2 报告正文的无损标记编码（转义、反转义、结构扫描）。

这些用例锁的是「写入侧转义 + 读取侧反转义」的对称性与可表达字符集，
预期值全部来自 ADR 0006 的规则本身，不由实现反算。
"""
from __future__ import annotations

import pytest

from jiaodui.markers import (escape_marker_field, is_v2_report,
                             mask_marker_fields, scan_math_spans,
                             split_marked_body, unescape_marker_field)

# 执行计划 §11.1 要求覆盖的字符集合：汉字、emoji、组合字符、零宽、LaTeX、跨行、竖线、括号
SAMPLES = [
    "木板",
    "甲|乙",
    "【选修专项】",
    "【1|原文|改为】",
    r"$\frac{\lambda }{v}=4\mathrm{s}$",
    r"\|",
    "\\",
    "|",
    "【",
    "】",
    "带|竖线【与】括号\\反斜杠",
    "emoji🙂与组合字符e\u0301",
    "零宽\u200b字符",
    "多行\n第二行|带竖线",
    "左【中|右】尾",
    r"\\\|",
]


@pytest.mark.parametrize("text", SAMPLES)
def test_escape_and_unescape_round_trip(text):
    assert unescape_marker_field(escape_marker_field(text)) == text


@pytest.mark.parametrize("text", SAMPLES)
def test_escape_is_injective(text):
    """不同输入不得编码成同一字段（否则反转义无法还原）。"""
    other = text + "尾"
    assert escape_marker_field(text) != escape_marker_field(other)


def test_escape_order_protects_backslashes_then_delimiters():
    assert escape_marker_field(r"a|b") == r"a\|b"
    assert escape_marker_field("a【b】c") == r"a\【b\】c"
    assert escape_marker_field("\\") == "\\\\"
    # 先转义反斜杠，再转义竖线：`\|` 应变成 `\\\|`，而不是 `\\\\|`
    assert escape_marker_field(r"\|") == r"\\\|"


def test_unescape_keeps_unknown_escapes_literal():
    """LaTeX 命令的首字母不能被吃掉：`\\f` 之类必须原样保留。"""
    latex = r"\frac{1}{2}\mathrm{s}=\lambda"
    assert unescape_marker_field(latex) == latex
    assert unescape_marker_field(escape_marker_field(latex)) == latex


def test_escaped_delimiters_do_not_terminate_marker_fields():
    body = r"甲【1|A\|B|A、B】乙【2|\【注\】|〔注〕】丙"
    assert split_marked_body(body, escaped=True) == "甲A|B乙【注】丙"
    assert split_marked_body(body, escaped=True) != body


def test_v1_fields_are_never_unescaped():
    """v1（无 v2 封套）必须逐字回填，`\\|` 保持字面，行为不因本 ADR 改变。"""
    body = r"甲【1|A\|B|A、B】乙"
    assert split_marked_body(body) == r"甲A\|B乙"
    assert split_marked_body(body, escaped=False) == r"甲A\|B乙"


def test_is_v2_report_only_matches_the_v2_envelope():
    assert is_v2_report("<!-- jiaodui-report-v2 -->\n总结行：无问题")
    assert not is_v2_report("总结行：无问题\n### 标记原文")


def test_mask_marker_fields_is_length_preserving_and_keeps_structure():
    body = r"前【1|A\】B|C】后"
    masked = mask_marker_fields(body)
    assert len(masked) == len(body)
    # 结构字符保留：开括号、编号、两个结构竖线、闭合括号
    assert masked.count("【") == 1 and masked.count("】") == 1
    assert masked.count("|") == 2
    assert masked.startswith("前【1|")
    # 字段内容（含被转义的闭合括号）不得残留
    assert "A" not in masked and "B" not in masked and "C" not in masked


def test_scan_math_spans_ignores_dollars_inside_escaped_marker_fields():
    """字段里出现「转义闭合括号 + 公式」时，屏蔽不能被提前截断。"""
    body = r"题【1|\【注\】$b$|x】后$y$"
    assert [body[s:e] for s, e in scan_math_spans(body)] == ["$y$"]
