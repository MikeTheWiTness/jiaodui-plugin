"""测试用正式交付装配：真实 v2 提交与当前快照父复核，不伪造清单。"""
from __future__ import annotations

from pathlib import Path

from jiaodui import material
from jiaodui.inspect_images import inspect_unit_images
from jiaodui.paths import find_source_md
from jiaodui.report_suggestions import extract_body
from jiaodui.review import record_parent_review
from jiaodui.source_index import query_locations
from jiaodui.unit_delivery import commit_unit_submission, read_unit_snapshot


def proposal_v2(unit, corrections=None):
    """返回 (材料清单, unit_id, 完整提案, snapshot)；重复原文可指定从 1 开始的 match_index。"""
    unit = Path(unit)
    root = material.find_material(unit)
    assert root is not None
    data = material.load(root)
    if not data["runs"][-1].get("execution_policy"):
        material.set_execution_policy(root, "automatic", "user")
        data = material.load(root)
    unit_id = data["unit_ids"][unit.name]
    snapshot = read_unit_snapshot(data["task_id"], unit_id)
    body = extract_body(find_source_md(unit).read_bytes().decode("utf-8"))
    resolved = []
    for index, correction in enumerate(corrections or [], 1):
        item = dict(correction)
        match_index = item.pop("match_index", None)
        if "location_id" not in item:
            matches = query_locations(body, snapshot["body_sha256"], item["expected_original"])
            if match_index is None:
                assert len(matches) == 1, "重复原文必须明确指定 match_index 或 location_id"
                match_index = 1
            assert 1 <= match_index <= len(matches), "match_index 从 1 开始且不得越界"
            item["location_id"] = matches[match_index - 1]["location_id"]
        item.setdefault("id", f"c{index}")
        item.setdefault("category", "text")
        item.setdefault("severity", "一般问题")
        item.setdefault("evidence_ids", ["e1"])
        resolved.append(item)
    images = inspect_unit_images(unit)
    image_evidence = [{
        "id": f"img{index}", "reference_index": ref["reference_index"],
        "original_path": ref["original_path"], "actual_read_path": ref["actual_read_path"],
        "position": {"line": ref["position"]["line"], "column": ref["position"]["column"]},
        "readable": True, "semantic": "测试题图", "verdict": "测试装配已核对图片引用",
    } for index, ref in enumerate(images["references"], 1)]
    rank = {"轻微问题": 1, "一般问题": 2, "严重错误": 3}
    proposal = {
        "schema_version": 2, "task_id": data["task_id"], "unit_id": unit_id,
        "run_id": snapshot["run_id"], "source_sha256": snapshot["source_sha256"],
        "body_sha256": snapshot["body_sha256"],
        "proposal_revision": snapshot["next_proposal_revision"],
        "summary": max((item["severity"] for item in resolved), key=rank.get) if resolved else "无问题",
        "corrections": resolved,
        "evidence": {
            "assumptions": [{"id": "e1", "text": "按测试样本的明确预期核对。", "source_locations": []}],
            "symbols": [],
            "images": image_evidence or {"status": "not_applicable", "reason": "测试样本没有图片"},
            "calculations": {"status": "not_applicable", "reason": "本测试仅验证交付流程，不涉及计算判断"},
        },
        "self_check": {"status": "passed", "checks": [
            "real_issue", "replacement_semantics", "related_coverage", "scope_and_uncertainty", "severity",
        ] if resolved else ["no_issue_review"], "unresolved": []},
    }
    return data, unit_id, proposal, snapshot


def deliver_v2(unit, corrections=None, accept=True):
    """提交真实 v2 产物；默认父代理接受当前快照，返回提交结果。"""
    data, unit_id, proposal, snapshot = proposal_v2(unit, corrections)
    result = commit_unit_submission(data["task_id"], unit_id, proposal, snapshot["snapshot_sha256"])
    if accept:
        current = read_unit_snapshot(data["task_id"], unit_id)
        record_parent_review(data["task_id"], unit_id,
                             expected_snapshot_sha256=current["snapshot_sha256"],
                             decision="accepted", reviewer_id="parent-test")
    return result
