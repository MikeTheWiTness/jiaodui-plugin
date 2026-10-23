"""CLI契约测试：命令可查询、结构化错误和稳定退出码。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

V1_COMMANDS = ["check-env", "inspect-source", "inspect-images", "convert", "split", "slice", "precheck-split",
               "status", "execution-policy", "unit-read", "unit-locate", "unit-snapshot", "unit-submit",
               "unit-recovery", "unit-progress", "dispatch-plan", "unit-event", "unit-schema", "calc-schema", "verify-report",
               "parse-report", "repair-report", "calc", "build-report", "build-docx"]


def run(*args):
    if args and args[0] in {"convert", "split", "slice", "parse-report", "build-report", "build-docx"}:
        args = (*args, "--legacy-layout")
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


def test_cli_machine_output_is_utf8_even_when_environment_requests_ascii(tmp_path):
    paper = tmp_path / "中文卷"
    paper.mkdir()
    (paper / "第1题").mkdir()
    (paper / "第1题" / "第1题.md").write_text("正文。", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "ascii:replace", "PYTHONUTF8": "0"}
    result = subprocess.run(
        [PY, "-m", "jiaodui", "status", str(paper), "--json"], cwd=ROOT,
        env=env, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "中文卷" in result.stdout
    assert "?" not in result.stdout
    assert json.loads(result.stdout)["counts"]["total"] == 1


def test_structured_error_unknown_file(tmp_path):
    r = run("convert", str(tmp_path / "不存在的文件.docx"), "--json")
    assert r.returncode != 0
    payload = json.loads(r.stderr.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_unit_submit_rejects_invalid_json_file_with_structured_error(tmp_path):
    proposal = tmp_path / "提案.json"
    proposal.write_text("{坏 JSON", encoding="utf-8")
    result = run("unit-submit", "--task-id", "a" * 32, "--unit-id", "b" * 32,
                 "--proposal-json-file", str(proposal),
                 "--expected-snapshot-sha256", "c" * 64)
    assert result.returncode == 6
    error = json.loads(result.stderr.strip().splitlines()[-1])["error"]
    assert error["code"] == "proposal-json-invalid"


def test_unit_schema_bind_current_exports_only_six_fewer_required_fields():
    full_result = run("unit-schema", "--json")
    bind_result = run("unit-schema", "--bind-current", "--json")
    assert bind_result.returncode == 0, bind_result.stderr
    full = json.loads(full_result.stdout)["schema"]
    bound = json.loads(bind_result.stdout)["schema"]
    assert set(full["required"]) - set(bound["required"]) == {
        "task_id", "unit_id", "run_id", "source_sha256", "body_sha256", "proposal_revision"}
    assert full["properties"] == bound["properties"]


def test_check_env_cli_passes_contract_expectations(monkeypatch, tmp_path):
    """check-env 的探针参数必须完整透传给 core，而不是只做本地依赖检查。"""
    from jiaodui import checkenv, cli

    calls = []

    def fake_check_env(**kwargs):
        calls.append(kwargs)
        return checkenv.EnvReport()

    monkeypatch.setattr(checkenv, "check_env", fake_check_env)
    schema_file = tmp_path / "schema.json"
    assert cli.main(["check-env", "--expect-schema-version", "3",
                     "--expect-bundle-version", "0.1.0",
                     "--expect-schema-file", str(schema_file), "--json"]) == 0
    assert calls == [{"expect_schema_version": 3,
                      "expect_bundle_version": "0.1.0",
                      "expect_schema_file": str(schema_file)}]


def test_unit_schema_exports_v3_with_core_assigned_identity():
    """文档承诺的 --schema-version 3 必须真实可用，且不再要求模型填身份字段。"""
    r = run("unit-schema", "--schema-version", "3", "--json")
    assert r.returncode == 0, r.stderr
    schema = json.loads(r.stdout)["schema"]
    assert schema["properties"]["schema_version"]["const"] == 3
    assert set(schema["required"]) == {"schema_version", "corrections", "self_check"}
    corrections = schema["properties"]["corrections"]["items"]["properties"]
    assert "old_text" in corrections and "new_text" in corrections
    assert "location_id" not in corrections


@pytest.mark.parametrize("preview", [False, True])
def test_unit_submit_cli_passes_bind_current_to_core(monkeypatch, preview):
    from jiaodui import cli, unit_delivery

    calls = []
    def submit(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True}
    target = "preview_unit_submission" if preview else "commit_unit_submission"
    monkeypatch.setattr(unit_delivery, target, submit)
    args = ["unit-submit", "--task-id", "a" * 32, "--unit-id", "b" * 32,
            "--proposal-json", '{"schema_version":2}',
            "--expected-snapshot-sha256", "c" * 64, "--bind-current"]
    if preview:
        args.append("--preview")
    assert cli.main(args) == 0
    assert calls[0][1] == {"bind_current": True}
    assert calls[0][0][2] == {"schema_version": 2}


def test_parse_report_cli_passes_manual_legacy_to_core(monkeypatch):
    from jiaodui import cli, workflow

    calls = []
    def parse(*args, **kwargs):
        calls.append(kwargs)
        return {"data": "unused"}
    monkeypatch.setattr(workflow, "parse_unit", parse)
    assert cli.main(["parse-report", "--unit", "unused", "--manual-legacy", "--json"]) == 0
    assert calls[0]["manual_legacy"] is True


def test_repair_report_cli_passes_manual_legacy_to_core(monkeypatch):
    from jiaodui import cli, report_repair

    calls = []
    def repair(*args, **kwargs):
        calls.append(kwargs)
        return report_repair.RepairResult(ok=True)
    monkeypatch.setattr(report_repair, "repair_unit_report", repair)
    assert cli.main(["repair-report", "--unit", "unused", "--apply", "--manual-legacy", "--json"]) == 0
    assert calls[0]["manual_legacy"] is True


def test_unit_submit_requires_one_proposal_input():
    result = run("unit-submit", "--task-id", "a" * 32, "--unit-id", "b" * 32,
                 "--expected-snapshot-sha256", "c" * 64)
    assert result.returncode == 2
    error = json.loads(result.stderr.strip().splitlines()[-1])["error"]
    assert error["code"] == "usage"


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


def test_inspect_images_command_returns_ordered_json(tmp_path):
    unit = tmp_path / "第1题"
    (unit / "images").mkdir(parents=True)
    (unit / "第1题.md").write_text("![图](./images/p.png)", encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (2, 2), "white").save(unit / "images" / "p.png")
    r = run("inspect-images", "--unit", str(unit), "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert payload["references"][0]["line"] == 1


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


def test_slice_preview_prints_cleaned_lecture(tmp_path):
    raw = tmp_path / "讲义_raw.md"
    raw.write_text(LECTURE_GRID, encoding="utf-8")
    r = run("slice", "--raw", str(raw), "--mode", "lecture", "--preview")
    assert r.returncode == 0, r.stderr
    assert "**例1**（多选）" in r.stdout
    assert "+---" not in r.stdout and "|" not in r.stdout


def test_slice_preview_requires_raw(tmp_path):
    r = run("slice", "--preview", "--json")
    assert r.returncode == 2
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "usage"


def test_slice_requires_boundaries_without_preview(tmp_path):
    raw = tmp_path / "a.md"
    raw.write_text("正文", encoding="utf-8")
    r = run("slice", "--raw", str(raw), "--json")
    assert r.returncode == 2
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "usage"


def test_slice_lecture_boundaries_from_preview(tmp_path):
    """完整 skill 示例：preview(--mode lecture --subject) → 定行号 → slice(同参数)。"""
    raw = tmp_path / "讲义_raw.md"
    raw.write_text(LECTURE_GRID, encoding="utf-8")
    preview = run("slice", "--raw", str(raw), "--mode", "lecture",
                  "--subject", "高中物理", "--preview")
    assert preview.returncode == 0, preview.stderr
    assert "+---" not in preview.stdout
    # 预览内容按契约样本钉死：行号取自这里，清理逻辑一变就必须在这里红
    assert preview.stdout.strip() == ("## 模块一\n\n**例1**（多选）\n题干一\n"
                                      "**例2**（多选）\n题干二")
    lines = preview.stdout.splitlines()
    i2 = lines.index("**例2**（多选）")
    bpath = tmp_path / "boundaries.json"
    bpath.write_text(json.dumps({
        "raw": str(raw),
        "mode": "lecture",
        "subject": "高中物理",
        "base_name": "讲义",
        "boundaries": [
            {"name": "单元1", "start_line": 1, "end_line": i2},
            {"name": "单元2", "start_line": i2 + 1, "end_line": len(lines)},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    r = run("slice", "--boundaries", str(bpath), "--mode", "lecture",
            "--subject", "高中物理", "--out-root", str(tmp_path / "out"), "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert len(payload["unit_dirs"]) == 2
    u1 = (Path(payload["unit_dirs"][0]) / "单元1.md").read_text(encoding="utf-8")
    u2 = (Path(payload["unit_dirs"][1]) / "单元2.md").read_text(encoding="utf-8")
    assert "**例1**" in u1 and "题干一" in u1 and "**例2**" not in u1
    assert "**例2**" in u2 and "题干二" in u2
    assert "+---" not in u1 and "+---" not in u2


def test_slice_without_mode_misslices_grid_lecture(tmp_path):
    """回归：漏 --mode（默认 exam）就不清理网格表，预览行号切在原始 raw 上必然错位。"""
    raw = tmp_path / "讲义_raw.md"
    raw.write_text(LECTURE_GRID, encoding="utf-8")
    preview = run("slice", "--raw", str(raw), "--mode", "lecture", "--preview")
    lines = preview.stdout.splitlines()
    i2 = lines.index("**例2**（多选）")
    bpath = tmp_path / "boundaries.json"
    bpath.write_text(json.dumps({
        "raw": str(raw),
        "base_name": "讲义",
        "boundaries": [
            {"name": "单元1", "start_line": 1, "end_line": i2},
            {"name": "单元2", "start_line": i2 + 1, "end_line": len(lines)},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    r = run("slice", "--boundaries", str(bpath), "--out-root", str(tmp_path / "out"), "--json")
    assert r.returncode == 6, r.stderr
    error = json.loads(r.stderr.strip().splitlines()[-1])["error"]
    assert error["code"] == "slice-coverage-invalid"
    assert error["details"]["uncovered_ranges"] == [{"start_line": 7, "end_line": 11}]
    assert not (tmp_path / "out" / "讲义").exists()
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
    from jiaodui.convert import find_pandoc

    if find_pandoc() is None:
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
