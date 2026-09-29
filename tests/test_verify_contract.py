"""verify-report 双向契约测试（PRD §5.2 / §9）。

不合格必被拒 + 合格必被接受；unknown 定位只告警；无法区分只记需人工确认。
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

NO_ISSUE = """无问题
### 标记原文

### 修改原因
无
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


def test_no_issue_with_both_sections_accepted():
    r = verify_report_text(NO_ISSUE, SOURCE)
    assert r.ok, [i.message for i in r.errors]
    assert r.summary == "无问题"
    assert r.marker_count == 0


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


def test_malformed_marker_rejected():
    text = VALID.replace("【1|a|b】", "【1a|b】")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert _codes(r) & {"syntax.malformed-marker", "syntax.unbalanced-brackets"}


def test_missing_field_marker_rejected():
    # 只有两段（缺「改为」）→ 字段数错误
    text = VALID.replace("【1|a|b】", "【1|a】")
    r = verify_report_text(text, SOURCE)
    assert not r.ok
    assert _codes(r) & {"syntax.field-count", "syntax.malformed-marker"}


def test_escaped_pipe_does_not_split_field():
    # \| 是 LaTeX 转义竖线，整体属于字段内容，不算分隔符
    text = VALID.replace("【1|a|b】", "【1|a\\|b|c】")
    r = verify_report_text(text, SOURCE)
    assert "syntax.field-count" not in _codes(r)


def test_unknown_localization_is_warning_not_error():
    # 原文字段与改为都无法在源文定位 → unknown，仅告警
    text = VALID.replace("【1|a|b】", "【1|x|y】")
    r = verify_report_text(text, SOURCE)
    assert "locate.unknown" in _codes(r, WARNING)
    assert "locate.unknown" not in _codes(r, ERROR)
    assert any(i.code in {"locate.unknown", "integrity.unknown-diff"} for i in r.warnings)


def test_manual_review_when_correction_indistinguishable():
    # 归一化后 原文 == 改为（大小写/全角差异）→ 需人工确认，不拒绝
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


def test_source_missing_only_warns():
    r = verify_report_text(VALID, None)
    assert r.ok
    assert "integrity.no-source" in _codes(r, WARNING)
