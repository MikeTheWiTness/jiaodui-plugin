"""status 状态机测试（PRD §5.3）。"""
from __future__ import annotations

import pytest

from jiaodui.status import (COMPLETED, DELIVERED_UNVERIFIED, FAILED, NOT_STARTED,
                            SKIPPED, scan_status, status_of_unit)

SRC = "设a为$O$点。"
VALID = "一般问题\n### 标记原文\n设【1|a|b】为$O$点。\n### 修改原因\n1. 原因。\n"


def _make_unit(root, name="第1题", report=None, fail=None):
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.md").write_text(SRC, encoding="utf-8")
    if report is not None:
        (d / "_校对报告.md").write_text(report, encoding="utf-8")
    if fail is not None:
        (d / "_校对失败.md").write_text(fail, encoding="utf-8")
    return d


def test_not_started(tmp_path):
    d = _make_unit(tmp_path)
    assert status_of_unit(d).state == NOT_STARTED


def test_completed(tmp_path):
    d = _make_unit(tmp_path, report=VALID)
    assert status_of_unit(d).state == COMPLETED


def test_delivered_unverified(tmp_path):
    bad = VALID.replace("一般问题\n", "")  # 缺严重度 → 校验不过，无失败记录
    d = _make_unit(tmp_path, report=bad)
    assert status_of_unit(d).state == DELIVERED_UNVERIFIED


def test_failed_with_fail_doc(tmp_path):
    bad = VALID.replace("一般问题\n", "")
    d = _make_unit(tmp_path, report=bad, fail="自修 3 轮仍不过\n详情")
    st = status_of_unit(d)
    assert st.state == FAILED
    assert "自修" in st.reason


def test_completed_beats_stale_fail_doc(tmp_path):
    d = _make_unit(tmp_path, report=VALID, fail="旧的失败记录")
    assert status_of_unit(d).state == COMPLETED


def test_skip_unit(tmp_path):
    d = _make_unit(tmp_path, name="板块1")
    (d / ".skip_proofread").touch()
    assert status_of_unit(d).state == SKIPPED


def test_failed_without_report(tmp_path):
    """技术崩溃后恢复：有失败记录但无报告，仍应保留为失败，不能回到未开始。"""
    d = _make_unit(tmp_path)
    (d / "_校对失败.md").write_text("API 超时，重派 1 次仍失败\n详情", encoding="utf-8")
    st = status_of_unit(d)
    assert st.state == FAILED
    assert "API 超时" in (st.reason or "")


def test_scan_status_counts(tmp_path):
    _make_unit(tmp_path, name="第1题", report=VALID)
    _make_unit(tmp_path, name="第2题")
    ps = scan_status(tmp_path)
    c = ps.counts()
    assert c["total"] == 2 and c[COMPLETED] == 1 and c[NOT_STARTED] == 1


def test_many_formula_markers_do_not_abort_paper_scan(tmp_path):
    """含大量公式标记的合法单元不能中断整卷状态扫描。"""
    _make_unit(tmp_path, name="第1题", report=VALID)
    unit = _make_unit(tmp_path, name="第2题")
    count = 600
    source = "、".join(["$a$"] * count) + "。"
    marked = "、".join(
        rf"【{i}|$\mathrm{{a}}$|$b$】" for i in range(1, count + 1)
    ) + "。"
    reasons = "\n".join(f"{i}. 修正变量。" for i in range(1, count + 1))
    (unit / "第2题.md").write_text(source, encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"一般问题\n### 标记原文\n{marked}\n### 修改原因\n{reasons}\n",
        encoding="utf-8",
    )
    _make_unit(tmp_path, name="第3题")

    result = scan_status(tmp_path)
    assert result.counts()[COMPLETED] == 2
    assert result.counts()[NOT_STARTED] == 1
    assert result.counts()["total"] == 3
    assert result.units[1].marker_count == count
