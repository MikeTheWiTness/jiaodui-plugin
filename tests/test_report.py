"""build-report 测试：只拼入通过校验的正文，失败写占位。"""
from __future__ import annotations

from jiaodui.report import build_report

SRC = "设a为$O$点。"
VALID = "一般问题\n### 标记原文\n设【1|a|b】为$O$点。\n### 修改原因\n1. 原因。\n"
BAD = "设a为$O$点。\n没有规范段落。"


def _unit(root, name, report):
    d = root / name
    d.mkdir()
    (d / f"{name}.md").write_text(SRC, encoding="utf-8")
    (d / "_校对报告.md").write_text(report, encoding="utf-8")
    return d


def test_only_verified_included(tmp_path):
    paper = tmp_path / "卷子"
    paper.mkdir()
    _unit(paper, "第1题", VALID)
    _unit(paper, "第2题", BAD)
    out = tmp_path / "out.md"
    r = build_report(paper, out_path=out, legacy_layout=True)
    assert r.out_path and out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "设【1|a|b】为$O$点。" in text
    assert "没有规范段落" not in text
    assert "未通过交付校验" in text
    assert [u["unit"] for u in r.included] == ["第1题"]
    assert [u["unit"] for u in r.failed] == ["第2题"]


def test_skipped_unit_placeholder(tmp_path):
    paper = tmp_path / "卷子"
    paper.mkdir()
    d = _unit(paper, "第1题", VALID)
    (d / ".skip_proofread").touch()
    r = build_report(paper, out_path=tmp_path / "out.md", legacy_layout=True)
    assert r.skipped and not r.included
