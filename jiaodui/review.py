"""版本绑定的父代理复核记录。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import material
from .errors import BusinessError
from .paths import data_path, report_path
from .unit_delivery import read_unit_snapshot


def self_check_digest(data: dict) -> str:
    proposal = data.get("proposal")
    if not isinstance(proposal, dict) or not isinstance(proposal.get("self_check"), dict):
        raise BusinessError("当前建议缺少子代理自查记录", code="self-check-missing")
    encoded = json.dumps(proposal["self_check"], ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_current(root, data: dict, unit_name: str) -> bool:
    """父复核只对当前run、输入、建议和报告摘要有效。"""
    unit_id = data.get("unit_ids", {}).get(unit_name)
    if not unit_id:
        return False
    unit = material.relative_path(root, data["paths"]["paper"]) / unit_name
    if not material.registered(root, data, unit):
        return False
    try:
        unit_data = json.loads(data_path(unit).read_text(encoding="utf-8"))
        checks_sha256 = self_check_digest(unit_data)
    except (OSError, ValueError, BusinessError):
        return False
    report_sha256 = material.sha256(report_path(unit))
    proposal_sha256 = unit_data.get("proposal_sha256")
    inputs = material.unit_inputs(root, unit)
    for review in reversed(data.get("unit_reviews", [])):
        if (review.get("unit_id") == unit_id and review.get("run_id") == data["current_run_id"]
                and review.get("report_sha256") == report_sha256
                and review.get("proposal_sha256") == proposal_sha256
                and review.get("self_check_sha256") == checks_sha256
                and review.get("inputs") == inputs):
            return review.get("decision") == "accepted"
    return False


def record_parent_review(task_id: str, unit_id: str, *, expected_snapshot_sha256: str,
                         decision: str, reviewer_id: str, issue: str = "") -> dict[str, Any]:
    """记录父代理接受或退回，旧hash结果保留但不再作为当前复核。"""
    if decision not in {"accepted", "needs_revision"}:
        raise BusinessError("复核decision必须为accepted或needs_revision", code="review-invalid")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise BusinessError("reviewer_id不能为空", code="review-invalid")
    if decision == "needs_revision" and not issue.strip():
        raise BusinessError("退回复核必须说明问题", code="review-issue-required")
    root, unit = material.find_unit_by_id(task_id, unit_id)
    from .workdir import ensure_inside
    ensure_inside(root)
    with material.locked(root):
        current = read_unit_snapshot(task_id, unit_id)
        if current["snapshot_sha256"] != expected_snapshot_sha256:
            raise BusinessError("父复核依据的报告版本已过期", code="review-stale",
                                details={"current_snapshot_sha256": current["snapshot_sha256"]})
        data = material.load(root)
        unit_data = json.loads(data_path(unit).read_text(encoding="utf-8"))
        if unit_data.get("schema_version") != 2:
            raise BusinessError("父复核仅适用于结构化schema v2提交", code="review-legacy-not-supported")
        review = {
            "unit_id": unit_id,
            "run_id": current["run_id"],
            "report_sha256": current["report_sha256"],
            "proposal_sha256": unit_data.get("proposal_sha256"),
            "self_check_sha256": self_check_digest(unit_data),
            "inputs": current["inputs"],
            "snapshot_sha256": current["snapshot_sha256"],
            "decision": decision,
            "reviewer_id": reviewer_id,
            "issue": issue.strip(),
            "recorded_at": material.now(),
        }
        data.setdefault("unit_reviews", []).append(review)
        data["runs"][-1].setdefault("actions", []).append({
            "command": "parent-review", "at": review["recorded_at"],
            "unit_id": unit_id, "decision": decision,
            "report_sha256": review["report_sha256"],
            "proposal_sha256": review["proposal_sha256"],
            "inputs": review["inputs"],
        })
        # 轮次完成口径含父复核：接受/退回都必须重算，否则退回后仍留着 completed、
        # 接受后也补不回 completed。
        data["runs"][-1]["status"] = ("completed" if material.run_units_complete(root, data)
                                      else "in_progress")
        material.write(root, data)
        return {"ok": True, "review": review, "current": review_current(root, data, unit.name)}
