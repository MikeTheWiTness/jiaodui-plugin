"""M5 调度闭环：错误码 → 恢复类别的确定性分类（PLAN-rework-continuation P5 第 1 项）。

锁三件事：
1. 计划点名的四类故障（参数拼错 / 旧路径引用 / 编辑前置失败 / 不支持函数差异）各自归类正确；
2. 用户取消与权限拒绝**不可恢复**，不得消耗预算；
3. 未分类的错误码被拒绝并给出建议，不允许模型自选类别绕过分类。
"""
from __future__ import annotations

import hashlib

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError
from jiaodui.error_classification import RECOVERY_BUDGETS, classify_error
from jiaodui.workflow import convert_material


@pytest.mark.parametrize("code,category", [
    # 计划点名的四例
    ("usage", "call_correction"),                 # 参数拼错
    ("not_found", "call_correction"),             # 旧路径引用
    ("host-edit-precondition", "call_correction"),  # 编辑前置失败（old_string 不匹配）
    ("unsupported", "call_correction"),           # 不支持函数差异
    # 调用形态类
    ("snapshot-stale", "call_correction"),
    ("location.stale", "call_correction"),
    ("location.original-mismatch", "call_correction"),
    ("identity-missing", "call_correction"),
    ("proposal.schema", "call_correction"),
    ("proposal.no-op", "call_correction"),
    ("proposal-base-invalid", "call_correction"),
    ("proposal-binding-conflict", "call_correction"),
    ("proposal-binding-unavailable", "call_correction"),
    ("proposal-revision-stale", "call_correction"),
    ("host-tool-schema", "call_correction"),
    # 计算表示类
    ("calc_failed", "calc_representation"),
    ("calc-evidence-invalid", "calc_representation"),
    ("proposal.calc-call-mismatch", "calc_representation"),
    # 报告类（闸门与完整性）
    ("verify_failed", "report_repair"),
    ("contract", "report_repair"),
    ("report-restore-mismatch", "report_repair"),
    ("integrity.missing-paragraph", "report_repair"),
    ("syntax.field-count", "report_repair"),
    ("original.not-locatable", "report_repair"),
    ("out-of-contract", "report_repair"),
    # 图片类
    ("images-invalid", "image_schema_fix"),
    ("images.missing", "image_schema_fix"),
    ("images.white_background_missing", "image_schema_fix"),
    # 技术类
    ("env", "technical_redispatch"),
    ("host-timeout", "technical_redispatch"),
    ("host-crash", "technical_redispatch"),
])
def test_error_codes_map_to_expected_category(code, category):
    result = classify_error(code)
    assert result["recoverable"] is True, code
    assert result["category"] == category, code
    assert result["category"] in RECOVERY_BUDGETS, "映射结果必须是六类预算之一"


@pytest.mark.parametrize("code", ["user-cancel", "permission-denied",
                                  "user_cancel", "permission_denied"])
def test_user_cancel_and_permission_denied_are_not_recoverable(code):
    result = classify_error(code)
    assert result["recoverable"] is False
    assert result["category"] is None


@pytest.mark.parametrize("code", ["anchor.not-found", "anchor.structure-cut", "revise.reason-empty", "revise.evidence-required"])
def test_interactive_diagnostics_do_not_consume_recovery_budget(code):
    result = classify_error(code)
    assert result["recoverable"] is False
    assert result["interactive"] is True
    assert result["category"] is None
    assert result["reason"] == "交互诊断：按 details 修正参数后直接重试，不消耗恢复预算"


@pytest.mark.parametrize("code", ["anchor.ambiguous", "revise.too-long"])
def test_recovery_rejects_interactive_codes_without_writing(tmp_path, monkeypatch, code):
    root, unit, task_id, unit_id = _unit(tmp_path, monkeypatch)
    manifest = root / "_校对记录.json"
    before = manifest.read_bytes()
    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(
            task_id, unit_id, None, hashlib.sha256(b"interactive").hexdigest(),
            attempt_id="interactive", error_code=code)
    assert error.value.code == "recovery-interactive-code"
    assert int(error.value.exit_code) == 6
    assert manifest.read_bytes() == before


def test_unclassified_error_code_is_rejected_with_suggestion():
    result = classify_error("totally-unknown-code")
    assert result["recoverable"] is False
    assert result["category"] is None
    assert result["suggestion"], "未分类码必须给出建议，不能只说失败"


def _unit(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    converted = convert_material(source, material_name="分类测试", mode="lecture")
    from jiaodui.workflow import split_material

    split = split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    root = workspace / "校对" / "分类测试"
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    from pathlib import Path

    unit = Path(split.unit_dirs[0])
    return root, unit, data["task_id"], data["unit_ids"][unit.name]


def test_recovery_consumes_budget_only_for_classified_codes(tmp_path, monkeypatch):
    root, unit, task_id, unit_id = _unit(tmp_path, monkeypatch)
    fingerprint = hashlib.sha256(b"bad-arg").hexdigest()

    # 错误码决定类别：调用方不必也不该自选
    allowed = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                               attempt_id="e1", error_code="usage")
    assert allowed["allowed"] is True
    assert allowed["category"] == "call_correction"

    # 同一错误换新指纹仍消费预算（不因换 agent / 换指纹重置）
    again = material.record_recovery_attempt(task_id, unit_id, None,
                                             hashlib.sha256(b"other").hexdigest(),
                                             attempt_id="e2", error_code="usage")
    assert again["allowed"] is True
    exhausted = material.record_recovery_attempt(task_id, unit_id, None,
                                                 fingerprint, attempt_id="e3",
                                                 error_code="usage")
    assert exhausted["allowed"] is False and exhausted["remaining"] == 0


def test_recovery_rejects_category_that_contradicts_the_code(tmp_path, monkeypatch):
    root, unit, task_id, unit_id = _unit(tmp_path, monkeypatch)
    fingerprint = hashlib.sha256(b"x").hexdigest()
    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(task_id, unit_id, "report_repair", fingerprint,
                                         attempt_id="e4", error_code="usage")
    assert error.value.code == "recovery-category-mismatch"
    # 报错必须给出可机械修正的目标值：第 12 讲实测父代理批量填错类别，4 次调用全部作废
    assert error.value.details["expected_category"] == "call_correction"
    assert error.value.details["provided_category"] == "report_repair"
    assert error.value.details["error_code"] == "usage"

    # 省略 category 即按错误码派生（这才是错误驱动恢复的正常写法）
    recorded = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                                attempt_id="e4b", error_code="usage")
    assert recorded["category"] == "call_correction"
    assert recorded["charged"] == ["call_correction"]


def test_recovery_rejects_unclassified_code_and_cancel(tmp_path, monkeypatch):
    root, unit, task_id, unit_id = _unit(tmp_path, monkeypatch)
    fingerprint = hashlib.sha256(b"x").hexdigest()
    with pytest.raises(BusinessError) as unknown:
        material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                         attempt_id="e5", error_code="no-such-code")
    assert unknown.value.code == "unclassified-error-code"
    for code in ("user-cancel", "permission-denied"):
        with pytest.raises(BusinessError) as forbidden:
            material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                             attempt_id=f"e6-{code}", error_code=code)
        assert forbidden.value.code == "recovery-forbidden"
    # 被拒绝的事件不得消耗任何预算
    state = material.load(root)["runs"][-1].get("recovery", {})
    assert state.get(unit_id, {}).get("call_correction", {}).get("used", 0) == 0


def test_targeted_review_needs_no_error_code_but_other_categories_do(tmp_path, monkeypatch):
    root, unit, task_id, unit_id = _unit(tmp_path, monkeypatch)
    fingerprint = hashlib.sha256(b"review").hexdigest()
    review = material.record_recovery_attempt(task_id, unit_id, "targeted_review", fingerprint,
                                               attempt_id="e7")
    assert review["allowed"] is True and review["category"] == "targeted_review"
    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(task_id, unit_id, "call_correction",
                                         hashlib.sha256(b"y").hexdigest(), attempt_id="e8")
    assert error.value.code == "recovery-error-code-required"
