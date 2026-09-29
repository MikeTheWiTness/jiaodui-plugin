"""标记真实性审计（Issue 056）：判定该不该生成批注、正文渲染哪一侧字段。

用例取自真实事故现场（移植自旧仓 tests/test_marker_audit.py）：
- 第 9 讲单元6：源文是「交于$O$点」，模型把原文标成「0」
- 第 8 讲单元8：源文确有「压强为为」，标记「为为→为」是真实结论
"""
from __future__ import annotations

from jiaodui.markers import (MARKER_EMPTY_ORIG, MARKER_NOOP, MARKER_OK,
                             MARKER_RESTORE_NEW, MARKER_UNKNOWN, audit_markers,
                             scan_math_spans, split_marked_body)

UNIT6_BODY = "①在白纸上画一条直线$ab$，并画出其垂线$cd$，交于【1|0|$O$】点；\n"
UNIT6_SOURCE = ("**例3**（2024·浙江）\n①在白纸上画一条直线$ab$，并画出其垂线$cd$，"
                "交于$O$点；\n②将侧面$A$沿$ab\\,$放置，并确定侧面$B$的位置$ef$；\n")

UNIT8_BODY = "$A$管内气体压强为【1|为为|为】$p_{A1}$，体积为${V}_{A1}=l\\cdot 4S$\n"
UNIT8_SOURCE = ("解答：  设$B$管的横截面积为$S$，$A$管在上方时，"
                "$A$管内气体压强为为$p_{A1}$，体积为${V}_{A1}=l\\cdot 4S$，"
                "$B$管内气体压强为$p_{B1}$\n")


def _one(body, source=None):
    audits = audit_markers(body, source)
    assert len(audits) == 1
    return audits[0]


def test_genuine_inline_marker_keeps_comment():
    a = _one("为等压过程，气体【1|体积与温度成正比|体积与热力学温度成正比】，故压强不变。",
             "为等压过程，气体体积与温度成正比，故压强不变。")
    assert a.verdict == MARKER_OK
    assert not a.render_new
    assert a.keep_comment


def test_phantom_marker_renders_correction():
    a = _one(UNIT6_BODY, UNIT6_SOURCE)
    assert a.verdict == MARKER_RESTORE_NEW
    assert a.render_new
    assert (a.original, a.correction) == ("0", "$O$")


def test_real_typo_with_overlapping_field_keeps_comment():
    a = _one(UNIT8_BODY, UNIT8_SOURCE)
    assert a.verdict == MARKER_RESTORE_NEW
    assert a.render_new
    assert a.keep_comment, "源文确有错字，批注不得被静默丢弃"


def test_noop_without_source_drops_comment():
    a = _one("故气体体积【2|增大|增大】。")
    assert a.verdict == MARKER_NOOP
    assert not a.keep_comment
    assert not a.render_new


def test_empty_original_drops_comment():
    a = _one("结果为$\\frac{【1||bbb】x}{R}$")
    assert a.verdict == MARKER_EMPTY_ORIG
    assert not a.keep_comment


def test_source_missing_does_not_guess():
    a = _one(UNIT6_BODY, None)
    assert a.verdict == MARKER_UNKNOWN
    assert not a.render_new
    assert a.keep_comment


def test_field_with_latex_decoration_not_misjudged():
    a = _one("折射率为【1|$p\\color{red}{＿}2$|$p_2$】$=2.5\\times10^5Pa$",
             "解得$p_2=2.5\\times10^5Pa$，$p_3=3\\times10^5Pa$")
    assert a.verdict == MARKER_UNKNOWN
    assert not a.render_new
    assert a.keep_comment


def test_audit_returns_one_entry_per_marker_in_order():
    audits = audit_markers("甲【1|错|对】乙【2|增大|增大】丙【3||改】", None)
    assert [a.num for a in audits] == [1, 2, 3]
    assert [a.verdict for a in audits] == [MARKER_UNKNOWN, MARKER_NOOP, MARKER_EMPTY_ORIG]


def test_no_marker_returns_empty():
    assert audit_markers("没有任何标记的正文", "源文") == []


def test_split_marked_body_restores_originals():
    assert split_marked_body("设【1|a|b】为【2|0|O】点。") == "设a为0点。"


def test_scan_math_spans_ignores_marker_internal_dollars():
    text = "x $a$ 与 【1|a$|b$】 y $c$"
    spans = scan_math_spans(text)
    assert len(spans) == 2


def test_scan_math_spans_handles_display_formula():
    spans = scan_math_spans("x $$a+b$$ y $c$")
    assert (2, 9) in spans, spans
    assert (12, 15) in spans, spans


def test_scan_math_spans_does_not_treat_display_as_two_empty():
    spans = scan_math_spans("$$a+b$$")
    assert spans == [(0, 7)], spans

