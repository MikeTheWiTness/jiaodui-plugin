"""CLI 契约测试：11 个 v1 命令可查询、结构化错误、稳定退出码。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")

V1_COMMANDS = ["check-env", "convert", "split", "slice", "precheck-split",
               "status", "verify-report", "parse-report", "calc",
               "build-report", "build-docx"]


def run(*args):
    return subprocess.run([PY, "-m", "jiaodui", *args], cwd=ROOT,
                          capture_output=True, text=True)


@pytest.mark.parametrize("cmd", V1_COMMANDS)
def test_command_help(cmd):
    r = run(cmd, "--help")
    assert r.returncode == 0, r.stderr
    assert cmd in r.stdout or cmd in r.stderr


def test_top_help_lists_all_v1():
    r = run("--help")
    assert r.returncode == 0
    for cmd in V1_COMMANDS:
        assert cmd in r.stdout


def test_structured_error_unknown_file():
    r = run("convert", "/tmp/不存在的文件.docx", "--json")
    assert r.returncode != 0
    payload = json.loads(r.stderr.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_verify_report_exit_code(tmp_path):
    unit = tmp_path / "第1题"
    unit.mkdir()
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text("没有规范段落。", encoding="utf-8")
    r = run("verify-report", "--unit", str(unit), "--json")
    assert r.returncode == 4
    payload = json.loads(r.stdout)
    assert payload["ok"] is False


def test_verify_report_valid_exit_zero(tmp_path):
    unit = tmp_path / "第1题"
    unit.mkdir()
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        "一般问题\n### 标记原文\n设【1|a|b】为$O$点。\n### 修改原因\n1. 参数写错。\n",
        encoding="utf-8")
    r = run("verify-report", "--unit", str(unit), "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ok"] is True


def test_status_json(tmp_path):
    unit = tmp_path / "卷子" / "第1题"
    unit.mkdir(parents=True)
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    r = run("status", str(tmp_path / "卷子"), "--json")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["counts"]["total"] == 1


def test_calc_unknown_op_structured(tmp_path):
    r = run("calc", "not-an-op", "--json")
    assert r.returncode == 7
    payload = json.loads(r.stderr.strip().splitlines()[-1])
    assert payload["error"]["code"] == "unsupported"


# ---------------------------------------------------------------- 集成：split / precheck / report

RAW_EXAM = "1．设a为$O$点，求a的值。\n\n2．第二题：$1+1=2$。\n"


def test_split_command_exam(tmp_path):
    raw = tmp_path / "卷子_raw.md"
    raw.write_text(RAW_EXAM, encoding="utf-8")
    r = run("split", str(raw), "--subject", "高中物理", "--mode", "exam", "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert len(payload["unit_dirs"]) == 2
    assert all((Path(p) / "images").is_dir() for p in payload["unit_dirs"])


def test_precheck_split_command(tmp_path):
    paper = tmp_path / "卷子"
    for i in (1, 2):
        d = paper / f"第{i}题"
        d.mkdir(parents=True)
        (d / f"第{i}题.md").write_text(f"第{i}题内容。", encoding="utf-8")
    r = run("precheck-split", str(paper), "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["unit_count"] == 2
    assert len(payload["units"]) == 2


def test_build_report_command(tmp_path):
    paper = tmp_path / "卷子"
    d = paper / "第1题"
    d.mkdir(parents=True)
    (d / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (d / "_校对报告.md").write_text(
        "一般问题\n### 标记原文\n设【1|a|b】为$O$点。\n### 修改原因\n1. 参数写错。\n",
        encoding="utf-8")
    r = run("build-report", str(paper), "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert Path(payload["out_path"]).is_file()
    assert "【1|a|b】" in Path(payload["out_path"]).read_text(encoding="utf-8")


def test_parse_report_refuses_unverified(tmp_path):
    unit = tmp_path / "第1题"
    unit.mkdir()
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text("不合规内容。", encoding="utf-8")
    r = run("parse-report", "--unit", str(unit), "--json")
    assert r.returncode == 6
    payload = json.loads(r.stderr.strip().splitlines()[-1])
    assert payload["error"]["code"] == "contract"
    assert not (unit / "_校对数据.json").exists()


def test_parse_report_legacy_allows(tmp_path):
    unit = tmp_path / "第1题"
    unit.mkdir()
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        "### 修改 1\n- **类型**: text\n- **原文**: a\n- **改为**: b\n- **原因**: 参数写错\n",
        encoding="utf-8")
    r = run("parse-report", "--unit", str(unit), "--legacy", "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["ok"] is True and payload["legacy"] is True



def test_verify_failure_emits_stderr_json(tmp_path):
    unit = tmp_path / "第1题"
    unit.mkdir()
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text("不合规内容。", encoding="utf-8")
    r = run("verify-report", "--unit", str(unit), "--json")
    assert r.returncode == 4
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["ok"] is False and err["error"]["code"] == "verify_failed"
    assert json.loads(r.stdout)["ok"] is False


def test_missing_required_args_structured():
    r = run("split")
    assert r.returncode == 2
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "usage"


def test_verify_rejects_report_without_source(tmp_path):
    unit = tmp_path / "第1题"
    unit.mkdir()
    (unit / "_校对报告.md").write_text(
        "一般问题\n### 标记原文\n设a为$O$点。\n### 修改原因\n1. 原因。\n", encoding="utf-8")
    r = run("verify-report", "--unit", str(unit), "--json")
    assert r.returncode == 4
    payload = json.loads(r.stdout)
    assert any(e["code"] == "integrity.no-source" for e in payload["errors"])



def test_calc_business_failure_emits_stderr_json():
    r = run("calc", "evaluate", "--json")
    assert r.returncode == 6
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "calc_failed"


def test_build_report_empty_emits_stderr_json(tmp_path):
    empty = tmp_path / "空卷"
    empty.mkdir()
    r = run("build-report", str(empty), "--json")
    assert r.returncode == 6
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "build_report_failed"


def test_build_docx_nonexistent_dir_emits_stderr_json(tmp_path):
    r = run("build-docx", str(tmp_path / "不存在"), "--json")
    assert r.returncode == 6
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "docx_incomplete"


def test_build_docx_excluded_emits_stderr_json(tmp_path):
    import shutil
    if not (shutil.which("pandoc") or Path("/usr/local/bin/pandoc").is_file()):
        import pytest as _pytest
        _pytest.skip("需要 pandoc")
    paper = tmp_path / "卷子"
    unit = paper / "第1题"
    unit.mkdir(parents=True)
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text("不合规。", encoding="utf-8")
    r = run("build-docx", str(paper), "--quiet", "--json")
    assert r.returncode == 6
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "docx_incomplete"

