"""四个核心流程的端到端 CLI 冒烟：试卷 / 讲义 / 智能切片 / 闸门与交付。

每个流程都从 raw Markdown 出发，走 CLI（split / slice / verify-report /
build-report / build-docx），断言退出码与产物；需要 pandoc 的环节显式跳过。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")


def run(*args):
    return subprocess.run([PY, "-m", "jiaodui", *args], cwd=ROOT,
                          capture_output=True, text=True)


def _report(source: str, needle: str, replacement: str) -> str:
    """在 source 里把 needle 处插入一个合法标记，生成能过闸门的报告。"""
    idx = source.find(needle)
    assert idx != -1, f"needle not in source: {needle!r}"
    marked = source[:idx] + f"【1|{needle}|{replacement}】" + source[idx + len(needle):]
    return ("一般问题\n\n### 标记原文\n" + marked
            + "\n\n### 修改原因\n1. 测试流程用原因。\n")


def _unit_source(unit_dir: Path) -> str:
    return (unit_dir / f"{unit_dir.name}.md").read_text(encoding="utf-8")


def _write_report(unit_dir: Path, needle: str, replacement: str) -> None:
    src = _unit_source(unit_dir)
    (unit_dir / "_校对报告.md").write_text(
        _report(src, needle, replacement), encoding="utf-8")


EXAM_RAW = "1．设a为$O$点，求a的值。\n\n2．第二题：$1+1=2$。\n"
LECTURE_GRID = ("## 模块一\n\n"
                "+------------------+\n"
                "| **例1**（多选）    |\n"
                "+------------------+\n"
                "| 题干一            |\n"
                "+------------------+\n"
                "| **例2**（多选）    |\n"
                "+------------------+\n"
                "| 题干二            |\n"
                "+------------------+\n")

PANDOC = shutil.which("pandoc") or (
    "/usr/local/bin/pandoc" if Path("/usr/local/bin/pandoc").is_file() else None)
NEEDS_PANDOC = pytest.mark.skipif(PANDOC is None, reason="pandoc 不可用")


# ─── 流程 1：试卷规则拆分 → 闸门 → 整卷报告 → Word ─────────────

def test_flow_exam_split_gate_and_docx(tmp_path):
    raw = tmp_path / "卷子_raw.md"
    raw.write_text(EXAM_RAW, encoding="utf-8")
    r = run("split", str(raw), "--subject", "高中物理", "--mode", "exam",
            "--out-root", str(tmp_path / "out"), "--json")
    assert r.returncode == 0, r.stderr
    paper = Path(tmp_path / "out" / "卷子")
    units = sorted(p for p in paper.iterdir() if p.is_dir())
    assert [u.name for u in units] == ["第1题", "第2题"]
    _write_report(units[0], "求a的值", "求 $a$ 的值")
    _write_report(units[1], "第二题", "第二题（改）")
    for u in units:
        v = run("verify-report", "--unit", str(u), "--json")
        assert v.returncode == 0, v.stderr
    br = run("build-report", str(paper), "--json")
    assert br.returncode == 0, br.stderr
    msg = json.loads(br.stdout)
    assert msg["ok"] is True
    if PANDOC is None:
        pytest.skip("pandoc 不可用，跳过 Word 交付")
    bd = run("build-docx", str(paper), "--json")
    assert bd.returncode == 0, bd.stderr
    docx = json.loads(bd.stdout)
    assert docx["ok"] is True and docx["missing_count"] == 0
    assert docx["marker_count"] == 2 and docx["anchor_count"] == 2
    assert docx["excluded_units"] == []


# ─── 流程 2：讲义规则拆分（网格表清理）→ 闸门 → Word ───────────

def test_flow_lecture_split_gate_and_docx(tmp_path):
    raw = tmp_path / "讲义_raw.md"
    raw.write_text(LECTURE_GRID, encoding="utf-8")
    r = run("split", str(raw), "--subject", "高中物理", "--mode", "lecture",
            "--out-root", str(tmp_path / "out"), "--json")
    assert r.returncode == 0, r.stderr
    paper = Path(tmp_path / "out" / "讲义")
    units = sorted(p for p in paper.iterdir() if p.is_dir())
    assert [u.name for u in units] == ["单元1", "单元2"]
    assert "|" not in _unit_source(units[0]), "讲义网格表必须被清理"
    _write_report(units[0], "题干一", "题干一（改）")
    _write_report(units[1], "题干二", "题干二（改）")
    for u in units:
        v = run("verify-report", "--unit", str(u), "--json")
        assert v.returncode == 0, v.stderr
    if PANDOC is None:
        pytest.skip("pandoc 不可用，跳过 Word 交付")
    bd = run("build-docx", str(paper), "--json")
    assert bd.returncode == 0, bd.stderr
    docx = json.loads(bd.stdout)
    assert docx["ok"] is True and docx["marker_count"] == 2


# ─── 流程 3：智能切片（预览 → 边界 → slice） ───────────────

def test_flow_smart_slice_matches_cleaned_lines(tmp_path):
    raw = tmp_path / "讲义_raw.md"
    raw.write_text(LECTURE_GRID, encoding="utf-8")
    preview = run("slice", "--raw", str(raw), "--mode", "lecture",
                  "--subject", "高中物理", "--preview")
    assert preview.returncode == 0, preview.stderr
    lines = preview.stdout.splitlines()
    i1 = lines.index("**例1**（多选）")
    i2 = lines.index("**例2**（多选）")
    bpath = tmp_path / "boundaries.json"
    bpath.write_text(json.dumps({
        "raw": str(raw), "mode": "lecture", "subject": "高中物理",
        "base_name": "讲义",
        "boundaries": [
            {"name": "单元1", "start_line": i1 + 1, "end_line": i2},
            {"name": "单元2", "start_line": i2 + 1, "end_line": len(lines)},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    r = run("slice", "--boundaries", str(bpath), "--mode", "lecture",
            "--subject", "高中物理", "--out-root", str(tmp_path / "out"), "--json")
    assert r.returncode == 0, r.stderr
    units = [Path(p) for p in json.loads(r.stdout)["unit_dirs"]]
    assert "**例1**" in _unit_source(units[0])
    assert "**例2**" not in _unit_source(units[0])
    assert "**例2**" in _unit_source(units[1])
    _write_report(units[0], "题干一", "题干一（改）")
    v = run("verify-report", "--unit", str(units[0]), "--json")
    assert v.returncode == 0, v.stderr


# ─── 流程 4：闸门拒绝不合格报告，不进入汇总与交付 ─────────────

def test_flow_gate_rejects_and_excludes(tmp_path):
    raw = tmp_path / "卷子_raw.md"
    raw.write_text(EXAM_RAW, encoding="utf-8")
    r = run("split", str(raw), "--subject", "高中物理", "--mode", "exam",
            "--out-root", str(tmp_path / "out"), "--json")
    assert r.returncode == 0, r.stderr
    paper = Path(tmp_path / "out" / "卷子")
    unit = paper / "第1题"
    # 未标记正文被改动：源文是 a，报告写 b，且没有标记
    changed = _unit_source(unit).replace("a", "b", 1)
    (unit / "_校对报告.md").write_text(
        "一般问题\n\n### 标记原文\n" + changed
        + "\n\n### 修改原因\n1. 原因。\n", encoding="utf-8")
    v = run("verify-report", "--unit", str(unit), "--json")
    assert v.returncode == 4
    st = run("status", str(paper), "--json")
    assert st.returncode == 0
    state = json.loads(st.stdout)
    assert state["counts"]["已交付未过校验"] == 1
    br = run("build-report", str(paper), "--json")
    assert br.returncode == 0
    failed = json.loads(br.stdout)["failed"]
    assert any(f["unit"] == "第1题" for f in failed)
    if PANDOC is None:
        pytest.skip("pandoc 不可用，跳过 Word 交付")
    bd = run("build-docx", str(paper), "--json")
    assert bd.returncode == 6
    assert json.loads(bd.stdout)["excluded_units"]
