from __future__ import annotations

import hashlib
import json

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
    with pytest.raises(BusinessError) as error:
        commit_unit_submission(task_id, unit_id, proposal, current["snapshot_sha256"])
    assert error.value.code == "proposal-revision-stale"
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
