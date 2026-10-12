from __future__ import annotations

from pathlib import Path

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError
from jiaodui.report import build_report
from jiaodui.review import record_parent_review, review_current
from jiaodui.source_index import query_locations, source_digest
from jiaodui.unit_delivery import commit_unit_submission, read_unit_snapshot
from jiaodui.workflow import convert_material, split_material


def _prepared(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("前言木板。第二段木板。末尾木板。", encoding="utf-8")
    converted = convert_material(source, material_name="复核测试", mode="lecture")
    split = split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    root = workspace / "校对" / "复核测试"
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    unit = Path(split.unit_dirs[0])
    unit_id = data["unit_ids"][unit.name]
    source_path = unit / f"{unit.name}.md"
    text = source_path.read_bytes().decode("utf-8")
    location = query_locations(text, source_digest(text), "木板")[-1]
    proposal = {
        "schema_version": 2, "task_id": data["task_id"], "unit_id": unit_id,
        "run_id": data["current_run_id"], "source_sha256": source_digest(text),
        "body_sha256": source_digest(text), "proposal_revision": 1,
        "summary": "一般问题",
        "corrections": [{"id": "c1", "location_id": location["location_id"],
                         "expected_original": "木板", "replacement": "木块",
                         "reason": "对象名称不一致。", "category": "term",
                         "severity": "一般问题", "evidence_ids": ["e1"]}],
        "evidence": {"assumptions": [{"id": "e1", "text": "对象定义为木块。", "source_locations": []}],
                     "symbols": [], "images": {"status": "not_applicable", "reason": "无图片"},
                     "calculations": {"status": "not_applicable", "reason": "无数值核验"}},
        "self_check": {"status": "passed", "checks": ["real_issue", "replacement_semantics",
                         "related_coverage", "scope_and_uncertainty", "severity"], "unresolved": []},
    }
    snapshot = read_unit_snapshot(data["task_id"], unit_id)
    return root, unit, data, unit_id, proposal, snapshot


def test_structured_delivery_requires_parent_review_for_exact_hashes(tmp_path, monkeypatch):
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    manifest = material.load(root)
    assert not review_current(root, manifest, unit.name)
    report = build_report(root / "units" / root.name)
    assert report.unreviewed and not report.complete
    assert not report.failed and report.included
    assert "父代理复核" in report.unreviewed[0]["reason"]

    current = read_unit_snapshot(task_id, unit_id)
    result = record_parent_review(task_id, unit_id,
                                  expected_snapshot_sha256=current["snapshot_sha256"],
                                  decision="accepted", reviewer_id="parent-1")
    assert result["current"] is True
    manifest = material.load(root)
    assert review_current(root, manifest, unit.name)
    accepted = build_report(root / "units" / root.name)
    assert accepted.complete and not accepted.failed


def test_report_or_input_hash_change_invalidates_parent_review(tmp_path, monkeypatch):
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    current = read_unit_snapshot(task_id, unit_id)
    record_parent_review(task_id, unit_id,
                         expected_snapshot_sha256=current["snapshot_sha256"],
                         decision="accepted", reviewer_id="parent-2")
    assert review_current(root, material.load(root), unit.name)

    report_path = unit / "_校对报告.md"
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert not review_current(root, material.load(root), unit.name)
    with pytest.raises(BusinessError) as error:
        record_parent_review(task_id, unit_id,
                             expected_snapshot_sha256=current["snapshot_sha256"],
                             decision="accepted", reviewer_id="parent-2")
    assert error.value.code == "review-stale"


def test_latest_rejection_revokes_acceptance_and_old_parse_cannot_bypass(tmp_path, monkeypatch):
    from jiaodui.workflow import parse_unit
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    current = read_unit_snapshot(task_id, unit_id)
    record_parent_review(task_id, unit_id, expected_snapshot_sha256=current["snapshot_sha256"],
                         decision="accepted", reviewer_id="parent")
    record_parent_review(task_id, unit_id, expected_snapshot_sha256=current["snapshot_sha256"],
                         decision="needs_revision", reviewer_id="parent", issue="关联用语需复查")
    assert not review_current(root, material.load(root), unit.name)
    before = (unit / "_校对数据.json").read_bytes()
    with pytest.raises(BusinessError) as error:
        parse_unit(unit)
    assert error.value.code == "parse-v2-requires-submit"
    assert (unit / "_校对数据.json").read_bytes() == before
    assert not build_report(unit.parent).complete


def test_parent_review_gates_completion_and_redispatch(tmp_path, monkeypatch):
    """回归（P1）：提交只算技术登记；复核前与被退回都要回到待派发集合。

    修复前 `register_locked` 只看 registered+verify，提交后立刻 `run.status=completed`、
    单元报「已完成」；父代理再 `needs_revision` 也不回退，`dispatch-plan` 从此不再
    派发该单元——断点恢复与自动补位都会漏掉它。
    """
    from jiaodui.status import scan_status

    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    material.record_unit_event(task_id, unit_id, phase="proposed", attempt_id="worker-1")
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])

    pending = scan_status(unit.parent)
    assert [item.state for item in pending.units] == ["本轮未完成"]
    assert "父复核" in pending.units[0].reason
    assert material.load(root)["runs"][-1]["status"] == "in_progress"
    assert material.unit_progress(task_id)["units"][0]["phase"] == "awaiting_parent_review"
    with pytest.raises(BusinessError) as late:
        material.record_unit_event(task_id, unit_id, phase="read", attempt_id="worker-1")
    assert late.value.code == "attempt-terminated"
    assert material.dispatch_plan(task_id)["dispatch"] == [], "已提交的单元待复核期间不应重复派发"

    current = read_unit_snapshot(task_id, unit_id)
    record_parent_review(task_id, unit_id, expected_snapshot_sha256=current["snapshot_sha256"],
                         decision="accepted", reviewer_id="parent")
    assert [item.state for item in scan_status(unit.parent).units] == ["已完成"]
    assert material.load(root)["runs"][-1]["status"] == "completed"
    assert material.unit_progress(task_id)["units"][0]["phase"] == "parent_reviewed"
    assert material.dispatch_plan(task_id)["dispatch"] == []

    record_parent_review(task_id, unit_id, expected_snapshot_sha256=current["snapshot_sha256"],
                         decision="needs_revision", reviewer_id="parent", issue="关联用语需复查")
    rejected = scan_status(unit.parent)
    assert [item.state for item in rejected.units] == ["本轮未完成"]
    assert material.load(root)["runs"][-1]["status"] == "in_progress"
    assert material.dispatch_plan(task_id)["dispatch"] == [unit.name], "退回单元必须重新可派发"
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="worker-2")
    with pytest.raises(BusinessError) as late_old_attempt:
        material.record_unit_event(task_id, unit_id, phase="registered", attempt_id="worker-1")
    assert late_old_attempt.value.code == "attempt-terminated"
    progress = material.unit_progress(task_id)["units"][0]
    assert progress["attempt_id"] == "worker-2"
    assert progress["phase"] == "read" and progress["in_flight"] is True


def test_invalidated_pending_review_delivery_returns_to_dispatch(tmp_path, monkeypatch):
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    material.record_unit_event(task_id, unit_id, phase="proposed", attempt_id="worker-1")
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    report_path = unit / "_校对报告.md"
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n损坏", encoding="utf-8")

    plan = material.dispatch_plan(task_id)

    assert plan["stop"] is False
    assert plan["states"][unit.name] == "本轮未完成"
    assert plan["dispatch"] == [unit.name]


def test_dispatch_refills_window_while_first_unit_waits_for_parent(tmp_path, monkeypatch):
    from jiaodui.source_index import source_digest

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("前言木板。\n第二段正文。\n末尾木板。", encoding="utf-8")
    converted = convert_material(source, material_name="补位测试", mode="lecture")
    split = split_material(converted.raw_md, subject="高中物理", mode="lecture", boundaries=[
        {"start_line": 1, "end_line": 1}, {"start_line": 2, "end_line": 3}])
    root = workspace / "校对" / "补位测试"
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    first = Path(split.unit_dirs[0])
    unit_id = data["unit_ids"][first.name]
    text = (first / f"{first.name}.md").read_text(encoding="utf-8")
    location = query_locations(text, source_digest(text), "木板")[0]
    proposal = {
        "schema_version": 2, "task_id": data["task_id"], "unit_id": unit_id,
        "run_id": data["current_run_id"], "source_sha256": source_digest(text),
        "body_sha256": source_digest(text), "proposal_revision": 1,
        "summary": "一般问题",
        "corrections": [{"id": "c1", "location_id": location["location_id"],
                         "expected_original": location["original"], "replacement": "木块",
                         "reason": "名称与语境不一致。", "category": "term",
                         "severity": "一般问题", "evidence_ids": ["e1"]}],
        "evidence": {"assumptions": [{"id": "e1", "text": "按语境应为木块。", "source_locations": []}],
                     "symbols": [], "images": {"status": "not_applicable", "reason": "无图"},
                     "calculations": {"status": "not_applicable", "reason": "无计算"}},
        "self_check": {"status": "passed", "checks": ["real_issue", "replacement_semantics",
                        "related_coverage", "scope_and_uncertainty", "severity"], "unresolved": []},
    }
    material.record_unit_event(data["task_id"], unit_id, phase="proposed", attempt_id="worker-1")
    snapshot = read_unit_snapshot(data["task_id"], unit_id)
    commit_unit_submission(data["task_id"], unit_id, proposal, snapshot["snapshot_sha256"])

    plan = material.dispatch_plan(data["task_id"], window=1)
    assert plan["in_flight"] == []
    assert plan["dispatch"] == ["单元2"]
    assert plan["waiting"] == []


def test_parent_review_cli_accepts_current_registered_version(tmp_path, monkeypatch):
    import subprocess
    import sys
    import json
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    current = read_unit_snapshot(task_id, unit_id)
    result = subprocess.run([sys.executable, "-m", "jiaodui", "unit-review", "--task-id", task_id,
                             "--unit-id", unit_id, "--expected-snapshot-sha256", current["snapshot_sha256"],
                             "--decision", "accepted", "--reviewer-id", "parent", "--json"],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["current"] is True


def test_successful_calc_cli_produces_a_bound_call_id(tmp_path, monkeypatch):
    import subprocess
    import sys
    import json
    from jiaodui.report_suggestions import render_suggestions
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    result = subprocess.run([sys.executable, "-m", "jiaodui", "calc", "evaluate", "--task-id", data["task_id"],
                             "--unit-id", unit_id, "--param", "expression=1+2", "--json"],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["call_id"]
    proposal["evidence"]["calculations"] = [{"id": "calc1", "call_id": output["call_id"],
                                             "expression": "1+2", "result": 3}]
    current_data = material.load(root)
    source = (unit / f"{unit.name}.md").read_bytes().decode("utf-8")
    candidate = render_suggestions(source, proposal, expected_task_id=data["task_id"],
                                   expected_unit_id=unit_id, expected_run_id=data["current_run_id"],
                                   calc_calls=current_data["runs"][-1]["calc_calls"])
    assert "核验说明：" in candidate.text


def test_word_rejects_unreviewed_then_accepts_current_review(tmp_path, monkeypatch):
    from jiaodui.docx_report import build_docx, find_pandoc
    import zipfile
    if not find_pandoc():
        pytest.skip("pandoc不可用")
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    rejected = build_docx(str(unit.parent))
    assert not rejected.ok and rejected.excluded_units
    current = read_unit_snapshot(task_id, unit_id)
    record_parent_review(task_id, unit_id, expected_snapshot_sha256=current["snapshot_sha256"],
                         decision="accepted", reviewer_id="parent")
    accepted = build_docx(str(unit.parent))
    assert accepted.ok, accepted.warnings
    assert accepted.marker_count == 1
    assert accepted.anchor_count + accepted.formula_fallback_count == 1
    with zipfile.ZipFile(accepted.out_path) as archive:
        assert "对象名称不一致" in archive.read("word/comments.xml").decode("utf-8")


def test_parent_review_rejects_empty_issue_and_requires_decision(tmp_path, monkeypatch):
    root, unit, data, unit_id, proposal, snapshot = _prepared(tmp_path, monkeypatch)
    task_id = data["task_id"]
    commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])
    current = read_unit_snapshot(task_id, unit_id)
    with pytest.raises(BusinessError) as issue:
        record_parent_review(task_id, unit_id,
                             expected_snapshot_sha256=current["snapshot_sha256"],
                             decision="needs_revision", reviewer_id="parent", issue=" ")
    assert issue.value.code == "review-issue-required"
