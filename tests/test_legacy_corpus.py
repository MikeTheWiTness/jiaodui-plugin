"""真实语料双向契约测试（PRD §9）：用冻结的旧仓语料钉住闸门。

- 不合格必被拒：空操作、未标记正文被改动（含标记切断 $...$ 公式导致的字段外差异）。
- 合格必被接受：其余报告通过严格新契约（含图片、公式、答案详解）。

预期在修正闸门后重新逐份标注（2026-09-29）：unknown 只豁免落在其字段内的差异，
因此把「标记切断 $...$ 公式、装饰美元落在字段外」的报告也判为不合格。

语料不在位时整文件 skip；可用 JIAODUI_LEGACY_CORPUS 指向旧仓 output 目录。
旧仓 HEAD 1c45243 完全冻结，本测试只读。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from jiaodui.status import COMPLETED, DELIVERED_UNVERIFIED, scan_status
from jiaodui.verify import verify_unit

_CORPUS = Path(os.environ.get(
    "JIAODUI_LEGACY_CORPUS",
    Path(__file__).resolve().parent.parent.parent / "JiaoDuiAgent" / "output",
))
_PAPER = _CORPUS / "拆题结果" / "2026年7月21日高中物理作业"

pytestmark = pytest.mark.skipif(not _PAPER.is_dir(), reason="旧仓语料不在位（只读参考）")

# 冻结语料逐份标注的预期结果（闸门修正后重新标注，不因新版结果更换）
EXPECTED_REJECTED = {"第5题", "第7题", "第10题", "第13题", "第15题", "第17题"}
# 拒绝原因逐份标注：空操作 / 未标记正文（含标记切断公式、装饰美元落在字段外）
_ANNOTATED_REASONS = {
    "第5题": "空操作",
    "第7题": "未标记正文",
    "第10题": "未标记正文",
    "第13题": "未标记正文",
    "第15题": "未标记正文",
    "第17题": "未标记正文",
}


def test_real_paper_gate_distribution():
    ps = scan_status(_PAPER)
    assert ps.counts()["total"] == 18
    rejected = {u.unit for u in ps.units if u.state != COMPLETED}
    assert rejected == EXPECTED_REJECTED, [
        (u.unit, u.state, u.reason) for u in ps.units if u.state != COMPLETED
    ]


def test_rejected_reasons_are_annotated():
    by_unit = {u.unit: u for u in scan_status(_PAPER).units}
    for unit, keyword in _ANNOTATED_REASONS.items():
        st = by_unit[unit]
        assert st.state == DELIVERED_UNVERIFIED, (unit, st.state)
        assert keyword in (st.reason or ""), (unit, st.reason)


def test_accepted_reports_pass_strict_contract():
    accepted = [u for u in scan_status(_PAPER).units if u.state == COMPLETED]
    assert len(accepted) == 12
    for u in accepted:
        result = verify_unit(u.dir)
        assert result.ok, (u.unit, [i.message for i in result.errors])
        assert result.summary in ("无问题", "轻微问题", "一般问题", "严重错误")
