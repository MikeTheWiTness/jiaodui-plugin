"""B2：旧清单兼容——可读、未授权、重授权时按单元保守迁移。

适配 main 的 `test_policy_legacy_compat.py` 两条断言到分支的账本形态
（分支按 `unit_id` 记 `recovery[unit][类别] = {used, fingerprints}`，
main 记在 `policy["spent"][unit]`），断言意图保持一致：

1. 缺执行策略的旧清单**可读**，但任何需要授权的操作必须被拒，重授权后才可用；
2. 旧聚合预算 + 聚合 spent 的清单**可读**（不是 invalid-manifest），重授权时把旧计数
   按单元保守迁移，**不重置额度**。
"""
from __future__ import annotations

import json

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError
from jiaodui.workflow import convert_material, split_material

LEGACY_POLICY = {
    "mode": "automatic", "origin": "confirmed",
    "confirmed_at": "2026-01-01T00:00:00+00:00",
    "budgets": {
        "entry_question": 2,
        "call_correction": 2,
        "report_correction": 3,
        "unit_recovery": 2,
        "technical_retry": 1,
        "calculation_correction": 2,
    },
    "spent": {
        "entry_question": 0,
        "call_correction": 1,
        "report_correction": 2,
        "unit_recovery": 1,
        "technical_retry": 1,
        "calculation_correction": 1,
    },
}


def _material(tmp_path, monkeypatch, *, units=2):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    converted = convert_material(source, material_name="旧清单兼容", mode="lecture")
    split = split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    root = workspace / "校对" / "旧清单兼容"
    if units > 1:
        from pathlib import Path

        template = Path(split.unit_dirs[0])
        for index in range(2, units + 1):
            target = template.parent / f"单元{index}"
            target.mkdir()
            (target / f"单元{index}.md").write_text(
                (template / f"{template.name}.md").read_text(encoding="utf-8"), encoding="utf-8")
        split_material(converted.raw_md, subject="高中物理", mode="lecture", adopt_units=True)
    return root, material.load(root)


def _rewrite_policy(root, mutate):
    manifest = root / material.MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    mutate(data["runs"][-1])
    manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_legacy_manifest_without_policy_is_readable_but_not_authorized(tmp_path, monkeypatch):
    root, data = _material(tmp_path, monkeypatch)
    _rewrite_policy(root, lambda run: run.pop("execution_policy", None))
    unit_id = list(data["unit_ids"].values())[0]

    # 可读：没有策略不构成清单损坏
    loaded = material.load(root)
    assert loaded["current_run_id"] == data["current_run_id"]

    # 未授权：任何需要授权的操作必须被拒
    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(data["task_id"], unit_id, None, "a" * 64,
                                         error_code="usage")
    assert error.value.code == "execution-policy-required"

    # 重授权后可用
    material.set_execution_policy(root, "automatic")
    allowed = material.record_recovery_attempt(data["task_id"], unit_id, None, "a" * 64,
                                               error_code="usage")
    assert allowed["allowed"] is True


def test_legacy_aggregated_budget_migrates_conservatively_per_unit(tmp_path, monkeypatch):
    root, data = _material(tmp_path, monkeypatch)
    _rewrite_policy(root, lambda run: run.__setitem__("execution_policy", dict(LEGACY_POLICY)))

    # 旧聚合形态必须可读（不是 invalid-manifest），但仍不授权
    loaded = material.load(root)
    assert loaded["runs"][-1]["execution_policy"]["budgets"]["report_correction"] == 3
    unit_id = list(data["unit_ids"].values())[0]
    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(data["task_id"], unit_id, None, "b" * 64,
                                         error_code="usage")
    assert error.value.code == "execution-policy-required"

    policy = material.set_execution_policy(root, "interactive")

    # 策略换成当前形态
    assert policy["budgets"] == {
        "call_correction": 2, "calc_representation": 2, "report_repair": 3,
        "targeted_review": 2, "technical_redispatch": 1, "image_schema_fix": 2,
    }
    # 旧聚合计数按单元保守迁移（main 的映射：entry 丢弃、image_schema_fix 从旧
    # call_correction 推、technical_redispatch 取 unit_recovery/technical_retry 最大）
    run = material.load(root)["runs"][-1]
    for identity in data["unit_ids"].values():
        used = {key: state["used"] for key, state in run["recovery"][identity].items()}
        assert used["call_correction"] == 1
        assert used["report_repair"] == 2
        assert used["technical_redispatch"] == 1
        assert used["calc_representation"] == 1
        assert used["image_schema_fix"] == 1
        assert used.get("targeted_review", 0) == 0

    # 迁移的计数**计入额度**：call_correction 已用 1，只剩 1 次
    first = material.record_recovery_attempt(data["task_id"], unit_id, None, "c" * 64,
                                             error_code="usage")
    assert first["allowed"] is True and first["used"] == 2 and first["remaining"] == 0
    second = material.record_recovery_attempt(data["task_id"], unit_id, None, "d" * 64,
                                              error_code="usage")
    assert second["allowed"] is False, "迁移过来的计数必须计入额度，不能被重置"
