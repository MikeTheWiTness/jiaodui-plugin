from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jiaodui.report_repair import build_repair_candidate, repair_unit_report
from jiaodui.verify import verify_report_text

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
SOURCE = "题干频率为 2×{10}^{-2} Hz。\n\n原因中的数字 5 应修改。"
REPORT = "总结行：一般问题\n\n### 标记原文\n题干频率为 2×10^{-2} Hz。\n\n原因中的数字【1|5|六】应修改。\n### 修改原因\n1. 数字错误。\n"
EXPECTED = "总结行：一般问题\n\n### 标记原文\n题干频率为 2×{10}^{-2} Hz。\n\n原因中的数字 【1|5|六】 应修改。\n### 修改原因\n1. 数字错误。\n"


def test_candidate_restores_unmarked_formula_from_source():
    result = build_repair_candidate(SOURCE, REPORT)
    assert result.ok
    assert result.text == EXPECTED
    assert verify_report_text(result.text, SOURCE).ok
    assert result.fields[0]["source_line"] == 3
    assert "10^{-2}" in result.diff


def test_candidate_rejects_non_unique_or_missing_original_field():
    cases = [
        ("甲重复词乙。\n\n丙重复词丁。", "repair.original-not-unique"),
        ("只有其他内容。", "repair.original-not-found"),
    ]
    for source, code in cases:
        report = "一般问题\n### 标记原文\n正文【1|重复词|替代】。\n### 修改原因\n1. 测试。"
        result = build_repair_candidate(source, report)
        assert not result.ok
        assert result.text is None
        assert result.diagnostics[0]["code"] == code
        assert result.diagnostics[0]["number"] == 1


def test_candidate_rejects_order_overlap_and_duplicate_number():
    reversed_result = build_repair_candidate(
        "甲乙。",
        "一般问题\n### 标记原文\n【1|乙|丙】【2|甲|丁】\n### 修改原因\n1. 原因。\n2. 原因。",
    )
    overlap_result = build_repair_candidate(
        "abcdef。",
        "一般问题\n### 标记原文\n【1|abc|x】【2|cde|y】f。\n### 修改原因\n1. 原因。\n2. 原因。",
    )
    duplicate_result = build_repair_candidate(
        "甲乙。",
        "一般问题\n### 标记原文\n【1|甲|丙】【1|乙|丁】。\n### 修改原因\n1. 原因。",
    )
    assert reversed_result.diagnostics[0]["code"] == "repair.marker-order"
    assert overlap_result.diagnostics[0]["code"] == "repair.marker-overlap"
    assert duplicate_result.diagnostics[0]["code"] == "report.verify-failed"


def test_candidate_rejects_structure_and_syntax_errors():
    missing_section = build_repair_candidate("正文。", "一般问题\n### 标记原文\n正文。")
    malformed = build_repair_candidate(
        "正文甲乙。",
        "一般问题\n### 标记原文\n正文【1甲乙】。\n### 修改原因\n无",
    )
    assert not missing_section.ok
    assert missing_section.diagnostics[0]["code"] == "report.reasons-section"
    assert not malformed.ok
    assert any(item["code"] == "report.verify-failed" for item in malformed.diagnostics)


def test_candidate_handles_escaped_pipe_multiline_and_crlf():
    source = "含 a\\|b。\n\n第二段甲\n乙。"
    report = "一般问题\n### 标记原文\n含【1|a\\|b|a\\|b?】。\n\n第二段【2|甲\n乙|丙】。\n### 修改原因\n1. 原因。\n2. 原因。"
    result = build_repair_candidate(source.replace("\n", "\r\n"), report.replace("\n", "\r\n"))
    assert result.ok
    assert "【1|a\\|b|a\\|b?】" in result.text
    assert "【2|甲\n乙|丙】" in result.text
    assert verify_report_text(result.text, source).ok


def test_apply_rejects_bad_images_without_mutating_files(tmp_path):
    unit = tmp_path / "单元1"
    unit.mkdir()
    source = unit / "单元1.md"
    report = unit / "_校对报告.md"
    failure = unit / "_校对失败.md"
    source.write_text("图片：![](./images/missing.png)。\n\n正文甲。", encoding="utf-8")
    report.write_text("一般问题\n### 标记原文\n图片：![](./images/missing.png)。\n\n正文【1|甲|乙】。\n### 修改原因\n1. 原因。", encoding="utf-8")
    failure.write_text("既有留痕。", encoding="utf-8")
    before = [path.read_bytes() for path in (source, report, failure)]
    result = repair_unit_report(unit, apply=True, work_root=tmp_path)
    assert not result.ok
    assert any(item["code"] == "images.missing" for item in result.diagnostics)
    assert [path.read_bytes() for path in (source, report, failure)] == before


def test_cli_preview_and_apply_without_parse_or_registration(tmp_path):
    unit = tmp_path / "单元1"
    unit.mkdir()
    (unit / "单元1.md").write_text(SOURCE, encoding="utf-8")
    report = unit / "_校对报告.md"
    report.write_text(REPORT, encoding="utf-8")
    preview = subprocess.run(
        [PY, "-m", "jiaodui", "repair-report", "--unit", str(unit), "--json"],
        cwd=ROOT, capture_output=True, text=True)
    assert preview.returncode == 0, preview.stderr
    payload = json.loads(preview.stdout)
    assert payload["mode"] == "preview"
    assert payload["applied"] is False
    assert "{10}^{-2}" in payload["diff"]
    assert report.read_text(encoding="utf-8") == REPORT
    applied = subprocess.run(
        [PY, "-m", "jiaodui", "repair-report", "--unit", str(unit), "--apply", "--work-root", str(tmp_path), "--json"],
        cwd=ROOT, capture_output=True, text=True)
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout)["verified"] is True
    assert report.read_text(encoding="utf-8") == EXPECTED
    assert not (unit / "_校对数据.json").exists()


def test_cli_apply_rejects_report_outside_work_root(tmp_path):
    unit = tmp_path / "单元1"
    unit.mkdir()
    (unit / "单元1.md").write_text(SOURCE, encoding="utf-8")
    (unit / "_校对报告.md").write_text(REPORT, encoding="utf-8")
    result = subprocess.run(
        [PY, "-m", "jiaodui", "repair-report", "--unit", str(unit), "--apply", "--work-root", str(tmp_path / "other"), "--json"],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 6
    error = json.loads(result.stderr.strip().splitlines()[-1])
    assert error["error"]["code"] == "outside-workspace"


def test_plan_sample_repairs_formula_transcription_without_writing():
    unit = ROOT / "校对/第 6 讲校对测试-独立续测-03/units/第 6 讲校对测试-独立续测-03/单元3"
    if not unit.is_dir():
        pytest.skip("当前工作区没有计划指定的回归样本")
    source = (unit / "单元3.md").read_text(encoding="utf-8")
    report_path = unit / "_校对报告.md"
    report = report_path.read_text(encoding="utf-8")
    result = build_repair_candidate(source, report)
    assert result.ok
    assert r"\times {10}^{-2}" in result.text
    assert r"\times 10^{-2}" not in result.text
    assert verify_report_text(result.text, source).ok
    assert report_path.read_text(encoding="utf-8") == report
