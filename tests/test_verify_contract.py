"""verify-report 双向契约测试（PRD §5.2 / §9）。

不合格必被拒 + 合格必被接受；unknown 只豁免「可确定落在一个公式字段内」的差异；
无法区分只记需人工确认；无法完成全文比对（空正文 / 源文缺失 / 缺段 / 重段）必须拒绝。
"""
from __future__ import annotations

from jiaodui.verify import ERROR, MANUAL, WARNING, verify_report_text

SOURCE = """设a为$O$点，b为1。

第二段保持不变。"""

VALID = """一般问题
### 标记原文
设【1|a|b】为$O$点，b为1。

第二段保持不变。
### 修改原因
1. 参数写错。
"""

# 无问题报告：两节仍须存在，且「标记原文」必须完整抄写源文（无问题时无标记）
NO_ISSUE = f"""无问题
### 标记原文
{SOURCE}
### 修改原因
无
"""

SOURCE3 = "第一段含 $a$ 与 b。\n\n第二段不变。\n\n第三段原文。"

# 第一段含无法定位的公式 unknown 标记，第三段是未标记正文篡改
UNKNOWN_PLUS_TAMPER = """一般问题
### 标记原文
第一段含【1|$\\mathrm{a}$|$b$】与 b。

第二段不变。

第三段被篡改。
### 修改原因
1. 测试。
"""

SOURCE_MATH = "设$a$为$O$点，b为1。"
MATH_UNKNOWN = """一般问题
### 标记原文
设【1|$\\mathrm{a}$|$b$】为$O$点，b为1。
### 修改原因
1. 原因。
"""


def _codes(result, severity=None):
    issues = result.errors if severity == ERROR else result.issues
    if severity == WARNING:
        issues = result.warnings
    if severity == MANUAL:
        issues = result.manual
    return {i.code for i in issues}


def test_valid_report_accepted():
    r = verify_report_text(VALID, SOURCE)
    assert r.ok, [i.message for i in r.errors]
    assert r.summary == "一般问题"
    assert r.marker_count == 1
    assert r.warnings == []


def test_no_issue_with_full_source_body_accepted():
    r = verify_report_text(NO_ISSUE, SOURCE)
    assert r.ok, [i.message for i in r.errors]
    assert r.summary == "无问题"
    assert r.marker_count == 0


def test_empty_marked_body_rejected_when_source_nonempty():
    text = "无问题\n### 标记原文\n\n### 修改原因\n无\n"
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert _codes(r) & {"integrity.missing-paragraph", "integrity.no-source"}


def test_severity_missing_rejected():
    text = VALID.replace("一般问题\n", "")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert _codes(r) & {"severity.missing", "severity.invalid"}


def test_bare_wu_severity_rejected():
    text = VALID.replace("一般问题", "无")
    r = verify_report_text(text, SOURCE)
    assert not r.ok


def test_no_issue_with_markers_rejected():
    text = VALID.replace("一般问题", "无问题")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert "severity.contradiction" in _codes(r)


def test_empty_original_rejected():
    text = VALID.replace("【1|a|b】", "【1||b】")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert "original.empty" in _codes(r)


def test_noop_marker_rejected():
    text = VALID.replace("【1|a|b】", "【1|a|a】")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert "original.noop" in _codes(r)


def test_missing_paragraph_rejected():
    text = VALID.replace("\n\n第二段保持不变。", "")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert "integrity.missing-paragraph" in _codes(r)


def test_extra_paragraph_rejected():
    text = VALID.replace("### 修改原因", "凭空多出的一段。\n\n### 修改原因")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert _codes(r) & {"integrity.extra-paragraph", "integrity.changed"}


def test_reason_missing_and_orphan_rejected():
    text = VALID.replace("1. 参数写错。", "2. 编号错位。")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    codes = _codes(r)
    assert "reason.missing" in codes and "reason.orphan" in codes


def test_reason_duplicate_number_rejected():
    text = VALID.replace("1. 参数写错。", "1. 第一条。\n1. 第二条。")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert "reason.duplicate" in _codes(r)


def test_reason_range_overlap_rejected():
    text = VALID.replace("1. 参数写错。", "1-2. 重叠范围。\n2. 显式重复。")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert "reason.duplicate" in _codes(r)


def test_mixed_reason_numbering_not_silently_dropped():
    # 混用「1.」与「①」；统一判重后必须发现重复/孤立，不能静默丢弃阿拉伯数字条目
    text = VALID.replace("1. 参数写错。", "1. 原因甲\n① 原因乙")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert "reason.duplicate" in _codes(r)


def test_malformed_marker_rejected():
    text = VALID.replace("【1|a|b】", "【1a|b】")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert _codes(r) & {"syntax.malformed-marker", "syntax.unbalanced-brackets"}


def test_missing_field_marker_rejected():
    text = VALID.replace("【1|a|b】", "【1|a】")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert _codes(r) & {"syntax.field-count", "syntax.malformed-marker"}


def test_escaped_pipe_does_not_split_field():
    text = VALID.replace("【1|a|b】", "【1|a\\|b|c】")
    r = verify_report_text(text, SOURCE)
    assert "syntax.field-count" not in _codes(r)


def test_unknown_math_field_confined_is_warning():
    """公式字段内的 unknown 差异：逐段一一对齐后仍为警告，不拒绝。"""
    r = verify_report_text(MATH_UNKNOWN, SOURCE_MATH)
    assert r.ok, [i.message for i in r.errors]
    assert "locate.unknown" in _codes(r, WARNING)
    assert "integrity.unknown-diff" in _codes(r, WARNING)


def test_unknown_non_math_field_rejected():
    """非公式的 unknown 差异不属于「LaTeX 标记字段」豁免范围 → 拒绝。"""
    text = VALID.replace("【1|a|b】", "【1|x|y】")
    r = verify_report_text(text, SOURCE)
    assert not r.ok


def test_unknown_math_field_cannot_absorb_prose():
    """公式字段的通配符不得吸收整句未标记正文。"""
    source = "首部$a$。重要条件不能删。尾部"
    report = ("一般问题\n### 标记原文\n首部【1|$\\mathrm{a}$|$b$】尾部\n"
              "### 修改原因\n1. 原因。\n")
    r = verify_report_text(report, source)
    assert not r.ok
    assert _codes(r) & {"integrity.extra-paragraph", "integrity.missing-paragraph"}


def test_unknown_cannot_hide_missing_paragraph():
    """只保留带 unknown 的第一段、丢掉第二段 → 缺段必须被拒绝。"""
    source = "第一段含 $a$ 与 b。\n\n第二段必须保留。"
    report = ("一般问题\n### 标记原文\n第一段含【1|$\\mathrm{a}$|$b$】与 b。\n"
              "### 修改原因\n1. 原因。\n")
    r = verify_report_text(report, source)
    assert not r.ok
    assert "integrity.missing-paragraph" in _codes(r, ERROR)


def test_unknown_cannot_duplicate_paragraph():
    """同一源文段在报告里被复制成两个 unknown 段 → 多段/重段必须被拒绝。"""
    source = "设 $a$ 为。"
    report = ("一般问题\n### 标记原文\n设【1|$\\mathrm{a}$|$b$】为。\n\n"
              "设【2|$\\mathrm{a}$|$c$】为。\n### 修改原因\n1. 甲。\n2. 乙。\n")
    r = verify_report_text(report, source)
    assert not r.ok
    assert "integrity.extra-paragraph" in _codes(r, ERROR)


def test_unknown_does_not_excuse_other_paragraph_tampering():
    r = verify_report_text(UNKNOWN_PLUS_TAMPER, SOURCE3)
    assert not r.ok, [i.code for i in r.warnings]
    assert _codes(r) & {"integrity.extra-paragraph", "integrity.missing-paragraph"}
    assert any(i.code == "integrity.unknown-diff" for i in r.warnings)


def test_manual_review_when_correction_indistinguishable():
    text = VALID.replace("【1|a|b】", "【1|a|A】")
    r = verify_report_text(text, SOURCE)
    assert r.ok
    assert "marker.manual-review" in _codes(r, MANUAL)


def test_missing_sections_rejected():
    text = "一般问题\n随便写点东西。"
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    codes = _codes(r)
    assert "sections.missing-marked" in codes and "sections.missing-reasons" in codes


def test_empty_report_rejected():
    r = verify_report_text("   ", SOURCE)
    assert not r.ok
    assert "report.empty" in _codes(r)


def test_source_missing_rejected():
    r = verify_report_text(VALID, None)
    assert not r.ok
    assert "integrity.no-source" in _codes(r, ERROR)


def test_between_formula_prose_cannot_be_absorbed():
    """两个真实公式之间的正文不能被伪公式通配符吸收。"""
    source = "首部$a$重要条件$b$尾部"
    report = ("一般问题\n### 标记原文\n首部$a【1|$\\mathrm{x}$|$y$】b$尾部\n"
              "### 修改原因\n1. 原因。\n")
    r = verify_report_text(report, source)
    assert not r.ok
    assert _codes(r) & {"integrity.missing-paragraph", "integrity.extra-paragraph"}


def test_local_formula_marker_accepted():
    """只标记公式内部局部内容：差异落在一个真实公式区间内 → 接受（仅警告）。"""
    source = "已知 $a+b$。"
    report = ("一般问题\n### 标记原文\n已知 $【1|$\\mathrm{a}$|c】+b$。\n"
              "### 修改原因\n1. 原因。\n")
    r = verify_report_text(report, source)
    assert r.ok, [i.message for i in r.errors]
    assert "integrity.unknown-diff" in _codes(r, WARNING)


def test_ordinary_marker_kept_literal_near_formula():
    """普通标记的原文不得因邻近公式而丢失：应与公式局部标记一起被接受。"""
    source = "设a与$x$满足条件。"
    report = ("一般问题\n### 标记原文\n设【1|a|b】与【2|$\\mathrm{x}$|$c$】满足条件。\n"
              "### 修改原因\n1. 甲。\n2. 乙。\n")
    r = verify_report_text(report, source)
    assert r.ok, [i.message for i in r.errors]
    assert "integrity.unknown-diff" in _codes(r, WARNING)



def test_phantom_marker_without_source_formula_rejected():
    """源文没有任何公式，却用 unknown 标记凭空插入公式内容 → 拒绝。"""
    source = "这是普通正文。"
    report = ("一般问题\n### 标记原文\n这是【1|$x$|$y$】普通正文。\n"
              "### 修改原因\n1. 原因。\n")
    r = verify_report_text(report, source)
    assert not r.ok
    assert _codes(r) & {"integrity.missing-paragraph", "integrity.extra-paragraph"}


def test_display_formula_local_marker_accepted():
    source = "已知 $$a+b$$。"
    report = ("一般问题\n### 标记原文\n已知 $$【1|$\\mathrm{a}$|c】+b$$。\n"
              "### 修改原因\n1. 原因。\n")
    r = verify_report_text(report, source)
    assert r.ok, [i.message for i in r.errors]
    assert "integrity.unknown-diff" in _codes(r, WARNING)


def test_display_formula_whole_wrapped_marker_accepted():
    source = "已知 $$a+b$$。"
    report = ("一般问题\n### 标记原文\n已知 【1|$$\\mathrm{a}+b$$|$$c+d$$】。\n"
              "### 修改原因\n1. 原因。\n")
    r = verify_report_text(report, source)
    assert r.ok, [i.message for i in r.errors]


def test_adjacent_formulas_two_markers_accepted():
    """两个相邻公式各配一个 unknown 占位符：必须尝试合法划分而不是只认首个正则匹配。"""
    source = "取 $a$ $b$。"
    report = ("一般问题\n### 标记原文\n取 【1|$\\mathrm{a}$|$c$】【2|$\\mathrm{b}$|$d$】。\n"
              "### 修改原因\n1. 甲。\n2. 乙。\n")
    r = verify_report_text(report, source)
    assert r.ok, [i.message for i in r.errors]
    assert "integrity.unknown-diff" in _codes(r, WARNING)

