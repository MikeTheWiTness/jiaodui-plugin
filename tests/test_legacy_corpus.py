"""真实语料双向契约测试（PRD §9）：用冻结的旧仓语料钉住闸门。

- 不合格必被拒：空操作、未标记正文被改动（含标记切断 $...$ 公式导致的字段外差异）。
- 合格必被接受：其余报告通过严格新契约（含图片、公式、答案详解）。

预期在修正闸门后逐份标注（2026-09-29）：unknown 仅豁免公式内部差异。
第18题的 8 个原文字段实际追加在公式之后；删除标记才与源文一致，还原原文字段
则多出 50 个非空白字符。该独立证据与文件哈希在下方测试固定，不以闸门输出倒推预期。

语料不在位时整文件 skip；可用 JIAODUI_LEGACY_CORPUS 指向旧仓 output 目录。
旧仓 HEAD 1c45243 完全冻结，本测试只读。
"""
from __future__ import annotations

import hashlib
import os
import re
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
# 第18题此前被边界空匹配误放行；独立正文比对证实原文字段被额外追加，应拒绝。
EXPECTED_REJECTED = {"第3题", "第5题", "第7题", "第10题", "第13题",
                     "第15题", "第17题", "第18题"}
# 拒绝原因逐份标注：空操作，或全文比对失败（缺段/多段/未标记正文）
_ANNOTATED_REASONS = {
    "第5题": ("空操作",),
    "第3题": ("缺段", "多段", "未标记正文"),
    "第7题": ("缺段", "多段", "未标记正文"),
    "第10题": ("缺段", "多段", "未标记正文"),
    "第13题": ("缺段", "多段", "未标记正文"),
    "第15题": ("缺段", "多段", "未标记正文"),
    "第17题": ("缺段", "多段", "未标记正文"),
    "第18题": ("缺段", "多段"),
}


def test_unit18_extra_original_fields_have_independent_evidence():
    """用固定语料及契约定义证明缺陷，不依赖闸门的匹配算法来计算预期。"""
    unit = _PAPER / "第18题"
    source_bytes = (unit / "第18题.md").read_bytes()
    report_bytes = (unit / "_校对报告.md").read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == (
        "706257207e89c20cbc2e89ea33a52160242c39b6202b27d0a2c1be8c76c90fc7"
    )
    assert hashlib.sha256(report_bytes).hexdigest() == (
        "6e823a1b428bbfbef8f4e6fbe6a077ef014446a541647b5114172db4de8abf37"
    )
    source = source_bytes.decode("utf-8")
    report = report_bytes.decode("utf-8")
    body = report.split("### 标记原文", 1)[1].split("### 修改原因", 1)[0]
    # 此固定样本只有两行报告元数据，不属于单元正文。
    lines = body.splitlines()
    metadata = [line for line in lines if line.startswith(("编号：", "内容："))]
    assert len(metadata) == 2
    body = "\n".join(line for line in lines if not line.startswith(("编号：", "内容：")))
    marker = re.compile(r"【(\d+)\|([^|]*)\|([^】]*)】")
    fields = marker.findall(body)
    assert [int(num) for num, _, _ in fields] == list(range(1, 9))
    assert all(original.strip() for _, original, _ in fields)

    source_compact = "".join(source.split())
    removed = "".join(marker.sub("", body).split())
    restored = "".join(marker.sub(lambda match: match.group(2), body).split())
    assert removed == source_compact
    assert restored != source_compact
    assert len(restored) - len(source_compact) == 50
    assert not verify_unit(unit).ok


def test_real_paper_gate_distribution():
    ps = scan_status(_PAPER)
    assert ps.counts()["total"] == 18
    rejected = {u.unit for u in ps.units if u.state != COMPLETED}
    assert rejected == EXPECTED_REJECTED, [
        (u.unit, u.state, u.reason) for u in ps.units if u.state != COMPLETED
    ]


def test_rejected_reasons_are_annotated():
    by_unit = {u.unit: u for u in scan_status(_PAPER).units}
    for unit, keywords in _ANNOTATED_REASONS.items():
        st = by_unit[unit]
        assert st.state == DELIVERED_UNVERIFIED, (unit, st.state)
        assert any(k in (st.reason or "") for k in keywords), (unit, st.reason)


def test_accepted_reports_pass_strict_contract():
    accepted = [u for u in scan_status(_PAPER).units if u.state == COMPLETED]
    assert len(accepted) == 10
    for u in accepted:
        result = verify_unit(u.dir)
        assert result.ok, (u.unit, [i.message for i in result.errors])
        assert result.summary in ("无问题", "轻微问题", "一般问题", "严重错误")
