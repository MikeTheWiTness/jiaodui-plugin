"""`_校对失败.md` 的结构校验（R-H11）。

该文件由 agent 写（Python 侧无生产者），这里锁定三件事：
结构完整的记录不报问题、结构不全只告警、以及**告警不改判定**（已通过不因旧失败记录回退）。
"""
from __future__ import annotations

from jiaodui.status import COMPLETED, FAILED, scan_status, status_of_unit

SOURCE = "设a为$O$点，b为1。\n\n第二段保持不变。"

VALID_REPORT = """一般问题
### 标记原文
设【1|a|b】为$O$点，b为1。

第二段保持不变。
### 修改原因
1. 参数写错。
"""

GOOD_NOTE = """第1题：公式内锚点无法定位

### verify 输出
{"ok": false, "errors": [{"code": "locate.unknown"}]}

### 产物摘要
标记 2，严重度 一般问题，错误 1
"""


def _unit(tmp_path, *, note=None, report=None, source=SOURCE):
    unit = tmp_path / "第1题"
    unit.mkdir()
    (unit / "第1题.md").write_text(source, encoding="utf-8")
    if report is not None:
        (unit / "_校对报告.md").write_text(report, encoding="utf-8")
    if note is not None:
        (unit / "_校对失败.md").write_text(note, encoding="utf-8")
    return unit


def test_complete_note_reports_no_problems(tmp_path):
    unit = _unit(tmp_path, note=GOOD_NOTE)
    status = status_of_unit(unit)
    assert status.state == FAILED
    assert status.reason.startswith("第1题：公式内锚点")
    assert status.failure_note_problems == []


def test_note_without_verify_output_is_flagged(tmp_path):
    unit = _unit(tmp_path, note="第1题：超时\n\n标记 0，严重度 无问题，错误 0\n")
    codes = {p["code"] for p in status_of_unit(unit).failure_note_problems}
    assert codes == {"failure_note.no-verify-output"}


def test_note_without_summary_is_flagged(tmp_path):
    unit = _unit(tmp_path, note='第1题：读图失败\n\n{"ok": false}\n')
    codes = {p["code"] for p in status_of_unit(unit).failure_note_problems}
    assert codes == {"failure_note.no-summary"}


def test_empty_note_is_flagged(tmp_path):
    unit = _unit(tmp_path, note="   \n\n")
    codes = {p["code"] for p in status_of_unit(unit).failure_note_problems}
    assert codes == {"failure_note.empty"}


def test_verify_not_executed_is_accepted(tmp_path):
    """verify 未执行时明确写「未执行」即算合格留痕。"""
    unit = _unit(tmp_path, note="第1题：转换阶段失败\n\nverify 未执行\n\n标记 0，严重度 无问题，错误 0\n")
    assert status_of_unit(unit).failure_note_problems == []


def test_problems_surface_as_paper_warnings(tmp_path):
    unit = _unit(tmp_path, report="不合规的报告。", note="只有一行\n")
    result = scan_status(unit.parent)
    assert result.units[0].state == FAILED
    assert any("verify-report 输出" in w for w in result.warnings)


def test_note_does_not_revert_completed_unit(tmp_path):
    """已通过的单元不因旧失败记录回退，也不因它的格式问题被标记。"""
    unit = _unit(tmp_path, report=VALID_REPORT, note="只有一行\n")
    status = status_of_unit(unit)
    assert status.state == COMPLETED
    assert status.failure_note_problems == []
