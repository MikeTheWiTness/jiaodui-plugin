"""智能切片覆盖契约：全量无遗漏，节选显式留痕，所有拒绝均早于单元写盘。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jiaodui import material
from jiaodui.errors import JiaoduiError
from jiaodui.report import build_report
from jiaodui.review import record_parent_review
from jiaodui.split import precheck_split, slice_by_boundaries
from jiaodui.unit_delivery import commit_unit_submission, read_unit_snapshot
from jiaodui.workflow import convert_material, slice_material, split_material


@pytest.mark.parametrize("boundaries, missing, overlap", [
    ([{"start_line": 1, "end_line": 1}, {"start_line": 3, "end_line": 3}],
     [{"start_line": 2, "end_line": 2}], []),
    ([{"start_line": 1, "end_line": 2}, {"start_line": 2, "end_line": 3}],
     [], [{"start_line": 2, "end_line": 2}]),
])
def test_full_slice_rejects_missing_or_repeated_nonempty_lines(tmp_path, boundaries, missing, overlap):
    out = tmp_path / "out"
    callbacks = []
    with pytest.raises(JiaoduiError) as error:
        slice_by_boundaries("第一题。\n关键错误正文。\n第二题。", boundaries,
                            str(out), "材料", before_write=callbacks.append)
    assert error.value.code == "slice-coverage-invalid"
    assert error.value.details["uncovered_ranges"] == missing
    assert error.value.details["overlapping_ranges"] == overlap
    assert callbacks == []
    assert not out.exists()


def test_full_slice_ignores_uncovered_blank_lines(tmp_path):
    result = slice_by_boundaries("甲\n  \n乙", [
        {"start_line": 1, "end_line": 1}, {"start_line": 3, "end_line": 3}], str(tmp_path / "out"), "材料")
    assert result.coverage["scope"] == "full"
    assert result.coverage["checked"] is True
    assert result.coverage["uncovered_ranges"] == []
    assert result.coverage["overlapping_ranges"] == []
    assert result.coverage["nonempty_lines"] == 2


@pytest.mark.parametrize("boundary", [
    {"start_line": 0, "end_line": 1}, {"start_line": 3, "end_line": 4},
    {"start_line": 2, "end_line": 1}, {"start_line": "错", "end_line": 2},
    {"start_line": True, "end_line": 2},
])
def test_invalid_ranges_are_rejected_without_clamping(tmp_path, boundary):
    out = tmp_path / "out"
    with pytest.raises(JiaoduiError) as error:
        slice_by_boundaries("甲\n乙", [boundary], str(out), "材料")
    assert error.value.code == "invalid-boundaries"
    assert error.value.details["boundary_index"] == 1
    assert not out.exists()


def test_full_text_boundary_cannot_claim_source_coverage(tmp_path):
    with pytest.raises(JiaoduiError) as error:
        slice_by_boundaries("甲\n遗漏正文", [{"text": "甲"}], str(tmp_path / "out"), "材料")
    assert error.value.code == "slice-line-ranges-required"
    assert not (tmp_path / "out").exists()


def test_excerpt_requires_reason_and_still_rejects_overlap(tmp_path):
    boundary = [{"start_line": 1, "end_line": 1}]
    with pytest.raises(JiaoduiError) as error:
        slice_by_boundaries("甲\n乙", boundary, str(tmp_path / "out"), "材料", scope="excerpt")
    assert error.value.code == "slice-scope-required"
    with pytest.raises(JiaoduiError) as error:
        slice_by_boundaries("甲\n乙", boundary * 2, str(tmp_path / "out"), "材料",
                            scope="excerpt", scope_reason="用户只校对甲")
    assert error.value.code == "slice-coverage-invalid"
    assert error.value.details["overlapping_ranges"] == [{"start_line": 1, "end_line": 1}]


def test_explicit_text_excerpt_reports_unchecked_coverage(tmp_path):
    result = slice_by_boundaries("原始正文", [{"text": "人工节选"}], str(tmp_path / "out"), "材料",
                                 scope="excerpt", scope_reason="用户提供的人工节选")
    assert result.coverage["scope"] == "excerpt"
    assert result.coverage["checked"] is False
    assert result.coverage["uncovered_ranges"] is None
    assert any("text" in warning for warning in result.warnings)


def _prepared(tmp_path, monkeypatch):
    workspace = tmp_path / "W"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "材料.md"
    source.write_text("第一题。\n关键错误正文。\n第二题。", encoding="utf-8")
    converted = convert_material(source, mode="lecture")
    root = workspace / "校对" / "材料"
    return workspace, converted, root


def _accept_units(root, result):
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    for directory in result.unit_dirs:
        unit = Path(directory)
        unit_id = data["unit_ids"][unit.name]
        snapshot = read_unit_snapshot(data["task_id"], unit_id)
        proposal = {
            "schema_version": 2, "task_id": data["task_id"], "unit_id": unit_id,
            "run_id": data["current_run_id"], "source_sha256": snapshot["source_sha256"],
            "body_sha256": snapshot["body_sha256"], "proposal_revision": snapshot["next_proposal_revision"],
            "summary": "无问题", "corrections": [],
            "evidence": {
                "assumptions": [{"id": "e1", "text": "按单元题设核对", "source_locations": []}],
                "symbols": [], "images": {"status": "not_applicable", "reason": "无图"},
                "calculations": {"status": "not_applicable", "reason": "无公式"},
            },
            "self_check": {"status": "passed", "checks": ["no_issue_review"], "unresolved": []},
        }
        commit_unit_submission(data["task_id"], unit_id, proposal, snapshot["snapshot_sha256"])
        current = read_unit_snapshot(data["task_id"], unit_id)
        record_parent_review(data["task_id"], unit_id, expected_snapshot_sha256=current["snapshot_sha256"],
                             decision="accepted", reviewer_id="parent")


def test_rejected_reslice_keeps_previous_material_bytes(tmp_path, monkeypatch):
    _, converted, root = _prepared(tmp_path, monkeypatch)
    original = split_material(converted.raw_md, mode="lecture", strategy="none")
    _accept_units(root, original)
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(JiaoduiError) as error:
        split_material(converted.raw_md, mode="lecture", replace_units=True, boundaries=[
            {"start_line": 1, "end_line": 1}, {"start_line": 3, "end_line": 3}])
    assert error.value.code == "slice-coverage-invalid"
    assert {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
    assert build_report(Path(original.unit_dirs[0]).parent).complete


@pytest.mark.parametrize("scope, boundaries", [
    ("full", [{"start_line": 1, "end_line": 2}, {"start_line": 3, "end_line": 3}]),
    ("excerpt", [{"start_line": 1, "end_line": 1}, {"start_line": 3, "end_line": 3}]),
])
def test_scope_persists_through_v2_completion_and_delivery(tmp_path, monkeypatch, scope, boundaries):
    _, converted, root = _prepared(tmp_path, monkeypatch)
    spec = tmp_path / "边界.json"
    spec.write_text(json.dumps({"raw": converted.raw_md, "mode": "lecture", "scope": scope,
                                "scope_reason": "用户只要求第一题和第二题" if scope == "excerpt" else None,
                                "boundaries": boundaries}, ensure_ascii=False), encoding="utf-8")
    result = slice_material(spec)
    data = material.load(root)
    assert data["params"]["slice_coverage"] == result.coverage
    assert data["runs"][-1]["actions"][-1]["args"]["slice_coverage"] == result.coverage
    paper = Path(result.unit_dirs[0]).parent
    assert precheck_split(str(paper)).coverage == result.coverage
    _accept_units(root, result)
    report = build_report(paper)
    assert report.complete
    assert report.to_dict()["coverage"]["scope"] == scope
    text = Path(report.out_path).read_text(encoding="utf-8")
    if scope == "full":
        assert "关键错误正文。" in text
    else:
        assert "关键错误正文。" not in text
        assert "明确节选" in text and "用户只要求第一题和第二题" in text
        assert result.coverage["uncovered_ranges"] == [{"start_line": 2, "end_line": 2}]


def test_scope_change_opens_new_run_without_changing_unit_source(tmp_path, monkeypatch):
    from jiaodui.status import scan_status
    _, converted, root = _prepared(tmp_path, monkeypatch)
    boundaries = [{"start_line": 1, "end_line": 3}]
    full = split_material(converted.raw_md, mode="lecture", boundaries=boundaries)
    _accept_units(root, full)
    before_run = material.load(root)["current_run_id"]
    unit = Path(full.unit_dirs[0])
    source_before = (unit / "单元1.md").read_bytes()
    split_material(converted.raw_md, mode="lecture", boundaries=boundaries)
    assert material.load(root)["current_run_id"] == before_run
    assert scan_status(unit.parent).counts()["已完成"] == 1

    split_material(converted.raw_md, mode="lecture", boundaries=boundaries,
                   scope="excerpt", scope_reason="用户指定本次所选范围")
    assert material.load(root)["current_run_id"] != before_run
    assert (unit / "单元1.md").read_bytes() == source_before
    assert scan_status(unit.parent).counts()["已完成"] == 0
    assert not build_report(unit.parent).complete


def test_adopted_regular_split_units_get_unchecked_coverage(tmp_path, monkeypatch):
    import shutil

    _, converted, root = _prepared(tmp_path, monkeypatch)
    split = split_material(converted.raw_md, mode="lecture", boundaries=[
        {"start_line": 1, "end_line": 1}, {"start_line": 2, "end_line": 3}])
    paper = Path(split.unit_dirs[0]).parent
    data = material.load(root)
    data["params"].pop("slice_coverage", None)
    material.write(root, data)
    removed = Path(split.unit_dirs[1])
    shutil.rmtree(removed)

    adopted = split_material(converted.raw_md, mode="lecture", adopt_units=True)
    coverage = material.load(root)["params"]["slice_coverage"]
    assert coverage["scope"] == "excerpt" and coverage["checked"] is False
    assert adopted.coverage == coverage
    assert any("重新核验" in warning for warning in adopted.warnings)
    _accept_units(root, adopted)
    report = build_report(paper)
    text = Path(report.out_path).read_text(encoding="utf-8")
    assert "人工接纳" in text and "不代表全材料完成" in text


def test_adopted_units_do_not_reuse_previous_verified_coverage(tmp_path, monkeypatch):
    import shutil
    _, converted, root = _prepared(tmp_path, monkeypatch)
    full = split_material(converted.raw_md, mode="lecture", boundaries=[
        {"start_line": 1, "end_line": 1}, {"start_line": 2, "end_line": 3}])
    _accept_units(root, full)
    paper = Path(full.unit_dirs[0]).parent
    removed = Path(full.unit_dirs[1])
    destination = paper / ".superseded" / "人工接纳" / removed.name
    assert removed.resolve() == (paper / "单元2").resolve()
    assert destination.resolve().is_relative_to(root.resolve())
    destination.parent.mkdir(parents=True)
    shutil.move(str(removed), str(destination))

    adopted = split_material(converted.raw_md, mode="lecture", adopt_units=True)
    data = material.load(root)
    coverage = data["params"]["slice_coverage"]
    assert coverage["scope"] == "excerpt"
    assert coverage["checked"] is False
    assert coverage["uncovered_ranges"] is None
    assert adopted.coverage == coverage
    assert any("重新核验" in warning for warning in adopted.warnings)
    _accept_units(root, adopted)
    report = build_report(paper)
    assert report.complete
    text = Path(report.out_path).read_text(encoding="utf-8")
    assert "明确节选" in text and "人工接纳" in text
    assert "不代表全材料完成" in text
    assert report.coverage == coverage


def test_explicit_scope_conflict_with_boundary_metadata_is_rejected(tmp_path, monkeypatch):
    _, converted, root = _prepared(tmp_path, monkeypatch)
    spec = tmp_path / "边界.json"
    spec.write_text(json.dumps({"raw": converted.raw_md, "mode": "lecture", "scope": "excerpt",
                                "scope_reason": "只选首题", "boundaries": [
                                    {"start_line": 1, "end_line": 1}]}), encoding="utf-8")
    with pytest.raises(JiaoduiError) as error:
        slice_material(spec, scope="full")
    assert error.value.code == "slice-scope-required"
    assert material.load(root)["unit_set"] == []


def test_excerpt_word_delivery_keeps_scope_notice(tmp_path, monkeypatch):
    from jiaodui.docx_report import build_docx, find_pandoc
    import zipfile
    from lxml import etree

    if find_pandoc() is None:
        pytest.skip("pandoc 不可用")
    _, converted, root = _prepared(tmp_path, monkeypatch)
    result = split_material(converted.raw_md, mode="lecture", scope="excerpt",
                            scope_reason="用户指定首题", boundaries=[{"start_line": 1, "end_line": 1}])
    _accept_units(root, result)
    word = build_docx(str(Path(result.unit_dirs[0]).parent))
    assert word.ok, word.warnings
    assert word.coverage == result.coverage
    with zipfile.ZipFile(word.out_path) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
    text = "".join(document.itertext())
    assert "明确节选" in text and "用户指定首题" in text
    assert "不代表全材料完成" in text
    assert "关键错误正文。" not in text


def test_cli_default_full_rejection_and_explicit_excerpt(tmp_path, monkeypatch):
    workspace, converted, root = _prepared(tmp_path, monkeypatch)
    spec = tmp_path / "边界.json"
    spec.write_text(json.dumps({"raw": converted.raw_md, "mode": "lecture", "boundaries": [
        {"start_line": 1, "end_line": 1}, {"start_line": 3, "end_line": 3}]}), encoding="utf-8")
    command = [sys.executable, "-m", "jiaodui", "slice", "--boundaries", str(spec),
               "--work-root", str(workspace), "--json"]
    rejected = subprocess.run(command, capture_output=True, text=True)
    assert rejected.returncode == 6
    assert json.loads(rejected.stderr.strip().splitlines()[-1])["error"]["code"] == "slice-coverage-invalid"
    accepted = subprocess.run(command + ["--scope", "excerpt", "--scope-reason", "用户指定节选"],
                              capture_output=True, text=True)
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["coverage"]["scope"] == "excerpt"
    assert material.load(root)["params"]["slice_coverage"]["reason"] == "用户指定节选"
