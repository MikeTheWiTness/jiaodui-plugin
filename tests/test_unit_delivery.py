from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError
from jiaodui.markers import split_marked_body
from jiaodui.report_parse import split_sections
from jiaodui.source_index import query_locations
from jiaodui.unit_delivery import (
    commit_unit_submission,
    preview_unit_submission,
    read_unit_snapshot,
)
from jiaodui.inspect_images import inspect_unit_images
from jiaodui.verify import verify_unit
from jiaodui.workflow import convert_material, split_material


def _prepared(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("前言木板。第二段木板。末尾木板。\n### 修改原因\n编号：保留原文。", encoding="utf-8")
    converted = convert_material(source, material_name="结构化提交", mode="lecture")
    split = split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    root = workspace / "校对" / "结构化提交"
    material.set_execution_policy(root, "automatic", "user")
    data = material.load(root)
    unit_id = data["unit_ids"][data["unit_set"][0]]
    unit = __import__("pathlib").Path(split.unit_dirs[0])
    source_file = __import__("jiaodui.paths", fromlist=["find_source_md"]).find_source_md(unit)
    text = source_file.read_bytes().decode("utf-8")
    locations = query_locations(text, hashlib.sha256(text.encode()).hexdigest(), "木板")
    last = locations[-1]
    proposal = {
        "schema_version": 2,
        "task_id": data["task_id"],
        "unit_id": unit_id,
        "run_id": data["current_run_id"],
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "proposal_revision": 1,
        "summary": "一般问题",
        "corrections": [{
            "id": "c1", "location_id": last["location_id"],
            "expected_original": "木板", "replacement": "木块",
            "reason": "对象名称与上下文定义不一致。", "category": "term",
            "severity": "一般问题", "evidence_ids": ["e1"],
        }],
        "evidence": {
            "assumptions": [{"id": "e1", "text": "应为木块。", "source_locations": []}],
            "symbols": [],
            "images": {"status": "not_applicable", "reason": "合成材料无图"},
            "calculations": {"status": "not_applicable", "reason": "无数值或公式核验"},
        },
        "self_check": {"status": "passed", "checks": ["real_issue", "replacement_semantics",
                         "related_coverage", "scope_and_uncertainty", "severity"], "unresolved": []},
    }
    snapshot = read_unit_snapshot(data["task_id"], unit_id)
    return workspace, root, unit, data, unit_id, text, proposal, snapshot


def test_cli_unit_submit_accepts_utf8_proposal_file(tmp_path, monkeypatch):
    workspace, root, _, data, unit_id, _, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    proposal_file = tmp_path / "结构化提案.json"
    proposal["evidence"]["assumptions"][0]["text"] = "中文依据：木板应改为木块。"
    proposal_file.write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "JIAODUI_WORK_ROOT": str(workspace)}
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "--json", "unit-submit",
         "--task-id", data["task_id"], "--unit-id", unit_id,
         "--proposal-json-file", str(proposal_file),
         "--expected-snapshot-sha256", snapshot["snapshot_sha256"]],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["registered"] and payload["verified"]
    assert material.load(root)["unit_records"][0]["unit"] == "单元1"


def test_image_evidence_is_bound_to_inspected_references_before_write(tmp_path, monkeypatch):
    from PIL import Image
    from jiaodui.paths import find_source_md
    from jiaodui.source_index import query_locations

    _, root, unit, data, unit_id, _, proposal, _ = _prepared(tmp_path, monkeypatch)
    source_path = find_source_md(unit)
    source_text = source_path.read_text(encoding="utf-8") + "\n![题图](./images/diagram.png)\n"
    source_path.write_text(source_text, encoding="utf-8")
    image_path = unit / "images" / "diagram.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2, 2), "white").save(image_path)
    manifest = inspect_unit_images(unit, source_path=source_path)
    reference = manifest["references"][0]
    current_data = material.load(root)
    current_data["unit_inputs"][unit.name] = material.unit_inputs(root, unit)
    material.write(root, current_data)
    proposal = dict(proposal)
    proposal["source_sha256"] = hashlib.sha256(source_text.encode()).hexdigest()
    proposal["body_sha256"] = proposal["source_sha256"]
    location = query_locations(source_text, proposal["body_sha256"], "木板")[-1]
    proposal["corrections"] = [{**proposal["corrections"][0],
                                "location_id": location["location_id"],
                                "expected_original": location["original"]}]
    snapshot = read_unit_snapshot(data["task_id"], unit_id)
    before_manifest = (root / material.MANIFEST).read_bytes()
    with pytest.raises(BusinessError) as error:
        preview_unit_submission(data["task_id"], unit_id, proposal,
                                snapshot["snapshot_sha256"])
    assert error.value.code == "proposal.evidence-images"
    assert (root / material.MANIFEST).read_bytes() == before_manifest
    assert not (unit / "_校对报告.md").exists()
    assert not (unit / "_校对数据.json").exists()

    proposal["evidence"] = dict(proposal["evidence"])
    proposal["evidence"]["images"] = [{
        "id": "img1", "reference_index": reference["reference_index"],
        "original_path": reference["original_path"],
        "actual_read_path": reference["actual_read_path"],
        "position": {"line": reference["position"]["line"],
                     "column": reference["position"]["column"]},
        "readable": True, "semantic": "题图", "verdict": "与题干一致",
    }]
    preview = preview_unit_submission(data["task_id"], unit_id, proposal,
                                     snapshot["snapshot_sha256"])
    assert preview["ok"]
    committed = commit_unit_submission(data["task_id"], unit_id, proposal,
                                       snapshot["snapshot_sha256"])
    assert committed["registered"] and committed["verified"]


def test_no_issue_submission_with_decimal_calculation_evidence(tmp_path, monkeypatch):
    from jiaodui.report_parse import parse_reason_entries

    _, _, unit, data, unit_id, _, proposal, _ = _prepared(tmp_path, monkeypatch)
    values = [0.2, 0.2, 0.35, 10, 2, 1, 0.5, 0.45, 0.1, 0]
    expression = "calculation evidence regression"
    call_id = material.record_calc_call(
        data["task_id"], unit_id, "evaluate", {"expression": expression},
        {"success": True, "result": values},
    )
    proposal["summary"] = "无问题"
    proposal["corrections"] = []
    proposal["evidence"]["calculations"] = [{
        "id": "calc1", "call_id": call_id, "expression": expression, "result": values,
    }]
    proposal["self_check"] = {"status": "passed", "checks": ["no_issue_review"], "unresolved": []}
    snapshot = read_unit_snapshot(data["task_id"], unit_id)

    committed = commit_unit_submission(data["task_id"], unit_id, proposal,
                                       snapshot["snapshot_sha256"])
    report = (unit / "_校对报告.md").read_text(encoding="utf-8")

    assert committed["registered"] and committed["verified"]
    assert verify_unit(unit).ok
    _, _, reasons = split_sections(report)
    assert parse_reason_entries(reasons) == []
    assert "核验说明" in report


def test_preview_is_read_only_and_commit_registers_generated_report(tmp_path, monkeypatch):
    _, root, unit, data, unit_id, source, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    before_manifest = (root / material.MANIFEST).read_bytes()
    preview = preview_unit_submission(data["task_id"], unit_id, proposal, snapshot["snapshot_sha256"])
    assert preview["ok"] and preview["preview"]
    assert not (unit / "_校对报告.md").exists()
    assert not (unit / "_校对数据.json").exists()
    assert (root / material.MANIFEST).read_bytes() == before_manifest

    committed = commit_unit_submission(data["task_id"], unit_id, proposal, snapshot["snapshot_sha256"])
    report = (unit / "_校对报告.md").read_text(encoding="utf-8")
    parsed = json.loads((unit / "_校对数据.json").read_text(encoding="utf-8"))
    _, marked, _ = split_sections(report)
    assert committed["registered"] and committed["verified"]
    assert split_marked_body(marked) == source
    assert parsed["schema_version"] == 2
    assert parsed["proposal"]["proposal_revision"] == 1
    assert material.registered(root, material.load(root), unit)
    assert verify_unit(unit).ok


def test_stale_data_version_refuses_commit_without_overwrite(tmp_path, monkeypatch):
    _, root, unit, data, unit_id, _, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    path = unit / "_校对数据.json"
    path.write_text("preexisting bytes\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(BusinessError) as error:
        commit_unit_submission(data["task_id"], unit_id, proposal, snapshot["snapshot_sha256"])
    assert error.value.code == "snapshot-stale"
    assert path.read_bytes() == before
    assert not (unit / "_校对报告.md").exists()


def test_registration_failure_rolls_back_report_data_and_manifest(tmp_path, monkeypatch):
    _, root, unit, data, unit_id, _, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    manifest = root / material.MANIFEST
    before_manifest = manifest.read_bytes()

    def fail(*args, **kwargs):
        raise RuntimeError("simulated registration failure")

    monkeypatch.setattr(material, "register_locked", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        commit_unit_submission(data["task_id"], unit_id, proposal, snapshot["snapshot_sha256"])
    assert not (unit / "_校对报告.md").exists()
    assert not (unit / "_校对数据.json").exists()
    assert manifest.read_bytes() == before_manifest


def test_new_snapshot_cannot_reuse_old_proposal_revision(tmp_path, monkeypatch):
    _, root, unit, data, unit_id, _, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    first = commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    current = read_unit_snapshot(task_id, unit_id)
    assert current["next_proposal_revision"] == 2
    with pytest.raises(BusinessError) as error:
        commit_unit_submission(task_id, unit_id, proposal, current["snapshot_sha256"])
    assert error.value.code == "proposal-revision-stale"
    # 必须给出当前版本与应填版本：只说「必须增加1」时调用方只能试探性加减
    message = str(error.value)
    assert "当前已登记 revision=1" in message
    assert "proposal_revision=2" in message
    assert "你写的是 1" in message
    next_proposal = {**proposal, "proposal_revision": 2}
    second = commit_unit_submission(task_id, unit_id, next_proposal, current["snapshot_sha256"])
    actions = material.load(root)["runs"][-1]["actions"]
    assert actions[-1]["previous_records"][0]["report_sha256"] == first["report_sha256"]
    assert second["proposal_sha256"] != first["proposal_sha256"]


def test_bad_proposal_never_mutates_existing_files(tmp_path, monkeypatch):
    _, root, unit, data, unit_id, _, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    (unit / "_校对报告.md").write_bytes(b"old report")
    (unit / "_校对数据.json").write_bytes(b"old data")
    fresh = read_unit_snapshot(data["task_id"], unit_id)
    invalid = {**proposal, "source_sha256": "0" * 64}
    before = [(unit / name).read_bytes() for name in ("_校对报告.md", "_校对数据.json")]
    with pytest.raises(BusinessError):
        commit_unit_submission(data["task_id"], unit_id, invalid, fresh["snapshot_sha256"])
    assert [(unit / name).read_bytes() for name in ("_校对报告.md", "_校对数据.json")] == before


def _prepare_special(tmp_path, monkeypatch, source_text: str, phrase: str):
    """为「含标记特殊字符的源文」准备一次真实提交现场（复用与 _prepared 相同的装配）。"""
    from pathlib import Path

    from jiaodui.paths import find_source_md

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text(source_text, encoding="utf-8")
    # clean=False：讲义清理会去表格竖线，本用例要保留源文字面的 `|`
    converted = convert_material(source, material_name="特殊字符", mode="lecture")
    split = split_material(converted.raw_md, subject="高中物理", mode="lecture",
                           strategy="none", clean=False)
    root = workspace / "校对" / "特殊字符"
    material.set_execution_policy(root, "automatic", "user")
    data = material.load(root)
    unit_id = data["unit_ids"][data["unit_set"][0]]
    unit = Path(split.unit_dirs[0])
    text = find_source_md(unit).read_bytes().decode("utf-8")
    located = query_locations(text, hashlib.sha256(text.encode()).hexdigest(), phrase)[-1]
    return data, unit_id, unit, text, located


def test_submission_round_trips_marker_special_characters(tmp_path, monkeypatch):
    """ADR 0006 集成：含竖线/标记括号/反斜杠的源文经 unit-submit 后逐字恢复且登记成功。"""
    source_text = "第一段：甲|乙 与【注】 和反斜杠\\尾。\n\n第二段：结尾。\n"
    data, unit_id, unit, text, located = _prepare_special(
        tmp_path, monkeypatch, source_text, "甲|乙")
    proposal = {
        "schema_version": 2,
        "task_id": data["task_id"],
        "unit_id": unit_id,
        "run_id": data["current_run_id"],
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "proposal_revision": 1,
        "summary": "一般问题",
        "corrections": [{
            "id": "c1", "location_id": located["location_id"],
            "expected_original": located["original"], "replacement": "甲或乙",
            "reason": "并集写法不一致。", "category": "term",
            "severity": "一般问题", "evidence_ids": ["e1"],
        }],
        "evidence": {
            "assumptions": [{"id": "e1", "text": "按源文核对。", "source_locations": []}],
            "symbols": [],
            "images": {"status": "not_applicable", "reason": "合成材料无图"},
            "calculations": {"status": "not_applicable", "reason": "无数值或公式核验"},
        },
        "self_check": {"status": "passed", "checks": ["real_issue", "replacement_semantics",
                         "related_coverage", "scope_and_uncertainty", "severity"], "unresolved": []},
    }
    snapshot = read_unit_snapshot(data["task_id"], unit_id)
    result = commit_unit_submission(data["task_id"], unit_id, proposal,
                                    snapshot["snapshot_sha256"])
    assert result["ok"] and result["registered"] and result["verified"]
    report = (unit / "_校对报告.md").read_text(encoding="utf-8")
    _, marked, _ = split_sections(report)
    assert r"甲\|乙" in marked
    assert split_marked_body(marked, escaped=True) == text
    assert verify_unit(unit).ok


def test_submission_rejects_empty_body(tmp_path, monkeypatch):
    """空白正文的单元必须显式拒绝，不得登记出一份空报告（ADR 0006 §8）。"""
    data, unit_id, unit, text, located = _prepare_special(
        tmp_path, monkeypatch, "   \n\n", " ")
    assert not text.strip()
    proposal = {
        "schema_version": 2,
        "task_id": data["task_id"],
        "unit_id": unit_id,
        "run_id": data["current_run_id"],
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "proposal_revision": 1,
        "summary": "无问题",
        "corrections": [],
        "evidence": {
            "assumptions": [{"id": "e1", "text": "无正文。", "source_locations": []}],
            "symbols": [],
            "images": {"status": "not_applicable", "reason": "合成材料无图"},
            "calculations": {"status": "not_applicable", "reason": "无数值或公式核验"},
        },
        "self_check": {"status": "passed", "checks": ["no_issue_review"], "unresolved": []},
    }
    snapshot = read_unit_snapshot(data["task_id"], unit_id)
    with pytest.raises(BusinessError) as error:
        commit_unit_submission(data["task_id"], unit_id, proposal,
                               snapshot["snapshot_sha256"])
    assert error.value.code == "proposal.empty-body"
    assert not (unit / "_校对报告.md").exists()
