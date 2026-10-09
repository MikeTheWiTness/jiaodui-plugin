"""main 时期的按单元策略契约测试，按结构化语义逐条映射（Phase 2 合并）。

映射规则与 `tests/test_execution_compat.py` 同源（那边有完整说明），此处只列差异：

- main 的 `_event(unit, phase=…, event=…, category=…)` 把「恢复事件」与「扣预算」合一；
  分支分开：`material.record_unit_event`（心跳，含取消来源）与
  `material.record_recovery_attempt`（扣预算，类别由错误码确定性映射）。
- main 的 `recover_unit(source=…)` → 分支同一恢复入口 + 错误码。
- main 的 `policy["spent"][unit][类别]` → 分支 `run["recovery"][unit_id][类别]["used"]`。
- 预算耗尽：main 抛 `execution-budget-exhausted`；分支返回 `allowed=false`。

**未保留的一条**：`test_recovery_uses_only_technical_redispatch_budget` 里的「only」——
合并后的产品选择「错误码确定性映射到六类额度」（UNIFY-PLAN 决策 1 + P5a），
技术类恢复仍只花 `technical_redispatch`，但恢复入口不再被限定为只花这一类；
该用例已改写成「技术类恢复花 technical_redispatch」并保留额度耗尽断言。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError

FINGERPRINT_A = "a" * 64
ERROR_CODE = {
    "call_correction": "usage",
    "calc_representation": "calc_failed",
    "report_repair": "verify_failed",
    "technical_redispatch": "host-timeout",
    "image_schema_fix": "images.missing",
}


def _material(tmp_path, monkeypatch):
    from jiaodui.workflow import convert_material, split_material

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "卷.md"
    source.write_text("1．题干。\n\n2．第二题。\n", encoding="utf-8")
    converted = convert_material(source, material_name="卷", mode="exam")
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    units = [Path(path) for path in split.unit_dirs]
    manifest = workspace / "校对" / "卷" / "_校对记录.json"
    return units, manifest


def _ids(manifest: Path, unit: Path):
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data["task_id"], data["unit_ids"][unit.name], data["current_run_id"]


def _authorize(unit: Path, manifest: Path, *, mode: str = "automatic", origin: str = "user"):
    from jiaodui import material

    return material.set_execution_policy(manifest.parent, mode, origin)


def _spend(unit: Path, manifest: Path, *, attempt_id: str, category: str = "call_correction",
           fingerprint: str = FINGERPRINT_A):
    from jiaodui import material

    task_id, unit_id, _ = _ids(manifest, unit)
    return material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                            attempt_id=attempt_id,
                                            error_code=ERROR_CODE[category])


def _recover(unit: Path, manifest: Path, *, attempt_id: str, error_code: str,
             fingerprint: str = FINGERPRINT_A):
    from jiaodui import material

    task_id, unit_id, _ = _ids(manifest, unit)
    return material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                            attempt_id=attempt_id, error_code=error_code)


def _cancel(unit: Path, manifest: Path, *, attempt_id: str, initiator: str = "user",
            reason: str = "user_cancel"):
    from jiaodui import material

    task_id, unit_id, _ = _ids(manifest, unit)
    return material.record_unit_event(task_id, unit_id, phase="prepared", attempt_id=attempt_id,
                                      cancel_initiator=initiator, cancel_reason=reason)


def _ledger(manifest: Path, unit: Path) -> dict:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    unit_id = data["unit_ids"][unit.name]
    return data["runs"][-1].get("recovery", {}).get(unit_id, {})


def _used(manifest: Path, unit: Path, category: str) -> int:
    return _ledger(manifest, unit).get(category, {}).get("used", 0)


def test_new_run_is_not_preauthorized_and_attempt_fails_without_policy(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    before = manifest.read_bytes()
    data = json.loads(before)
    assert "execution_policy" not in data["runs"][-1]

    with pytest.raises(JiaoduiError) as err:
        _spend(units[0], manifest, attempt_id="attempt-1")
    assert err.value.code == "execution-policy-required"
    assert manifest.read_bytes() == before

    with pytest.raises(JiaoduiError) as err:
        _recover(units[0], manifest, attempt_id="retry-without-policy", error_code="host-timeout")
    assert err.value.code == "execution-policy-required"
    assert manifest.read_bytes() == before


def test_budget_categories_are_fixed_and_not_entry_questions():
    from jiaodui.execution_policy import BUDGETS

    assert BUDGETS == {
        "call_correction": 2,
        "calc_representation": 2,
        "report_repair": 3,
        "targeted_review": 2,
        "technical_redispatch": 1,
        "image_schema_fix": 2,
    }
    assert "entry_question" not in BUDGETS


def test_units_have_independent_call_budgets(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    _authorize(units[0], manifest)
    for index in range(2):
        assert _spend(units[0], manifest, attempt_id=f"{units[0].name}-call-{index}")["allowed"]

    exhausted = _spend(units[0], manifest, attempt_id="第1题-call-over")
    assert exhausted["allowed"] is False and exhausted["remaining"] == 0

    assert _spend(units[1], manifest, attempt_id="第2题-call-0")["allowed"]  # 第2题有独立额度
    assert _used(manifest, units[1], "call_correction") == 1
    assert _spend(units[1], manifest, attempt_id="第2题-call-1")["allowed"]
    assert _spend(units[1], manifest, attempt_id="第2题-call-third")["allowed"] is False

    assert _used(manifest, units[0], "call_correction") == 2
    assert _used(manifest, units[1], "call_correction") == 2


def test_attempt_id_is_idempotent_but_same_fingerprint_new_attempt_spends(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)

    first = _spend(unit, manifest, attempt_id="attempt-a")
    before_duplicate = manifest.read_bytes()
    same_attempt = _spend(unit, manifest, attempt_id="attempt-a")
    assert same_attempt["idempotent"] is True and same_attempt["used"] == first["used"]
    assert manifest.read_bytes() == before_duplicate, "同 attempt 重放不得改盘"

    _spend(unit, manifest, attempt_id="attempt-b", fingerprint=FINGERPRINT_A)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    unit_id = data["unit_ids"][unit.name]
    assert _used(manifest, unit, "call_correction") == 2
    assert len(data["runs"][-1]["recovery_attempts"][unit_id]) == 2


def test_reusing_attempt_id_with_different_fingerprint_is_rejected(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    _authorize(units[0], manifest)
    _spend(units[0], manifest, attempt_id="attempt-a")
    before = manifest.read_bytes()

    with pytest.raises(JiaoduiError) as err:
        _spend(units[0], manifest, attempt_id="attempt-a", fingerprint="b" * 64)
    assert err.value.code == "attempt-id-conflict"
    assert manifest.read_bytes() == before


def test_fingerprint_must_be_sha256_hex(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    _authorize(units[0], manifest)
    with pytest.raises(JiaoduiError) as err:
        _spend(units[0], manifest, attempt_id="attempt-a", fingerprint="not-a-hash")
    assert err.value.code == "invalid-attempt-fingerprint"


def test_image_schema_fix_spends_call_budget_once_per_attempt_not_additively(tmp_path, monkeypatch):
    """图片格式修复连带扣一次调用；同一 attempt 重放不再扣（「不叠加」的落点）。"""
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)

    for index in range(2):
        assert _spend(unit, manifest, attempt_id=f"image-{index}",
                      category="image_schema_fix")["allowed"]
    before = manifest.read_bytes()
    replay = _spend(unit, manifest, attempt_id="image-0", category="image_schema_fix")
    assert replay["idempotent"] is True and manifest.read_bytes() == before

    over = _spend(unit, manifest, attempt_id="image-over", category="image_schema_fix")
    assert over["allowed"] is False
    assert manifest.read_bytes() == before, "被拒时不得改盘"

    assert _used(manifest, unit, "image_schema_fix") == 2
    assert _used(manifest, unit, "call_correction") == 2


def test_cancellation_and_permission_never_spend_or_recover(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)
    before = manifest.read_bytes()

    for error_code in ("user-cancel", "permission-denied"):
        with pytest.raises(JiaoduiError) as err:
            _recover(unit, manifest, attempt_id=f"{error_code}-1", error_code=error_code)
        assert err.value.code == "recovery-forbidden"
    assert manifest.read_bytes() == before, "取消与权限拒绝不得改盘"

    _cancel(unit, manifest, attempt_id="cancel-event")
    assert _ledger(manifest, unit) == {}, "取消事件不得消耗任何预算"


def test_recovery_spends_the_mapped_budget_not_a_shared_one(tmp_path, monkeypatch):
    """技术类恢复只花 technical_redispatch（额度 1），第二次即耗尽。

    原 main 用例断言的是「恢复只允许 technical_redispatch 这一类」；合并后恢复入口
    按错误码映射到六类，故这里保留「技术类只花 technical_redispatch」与耗尽断言。
    """
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)

    recovery = _recover(unit, manifest, attempt_id="retry-1", error_code="host-timeout")
    assert recovery["allowed"] is True and recovery["category"] == "technical_redispatch"
    assert _used(manifest, unit, "technical_redispatch") == 1
    assert "unit_recovery" not in _ledger(manifest, unit)
    assert "technical_retry" not in _ledger(manifest, unit)

    before = manifest.read_bytes()
    exhausted = _recover(unit, manifest, attempt_id="retry-2", error_code="host-timeout")
    assert exhausted["allowed"] is False and exhausted["remaining"] == 0
    assert manifest.read_bytes() == before


def test_policy_change_is_locked_and_ledger_is_preserved(tmp_path, monkeypatch):
    """路线差异：main 允许同轮次改模式并保留 spent；分支把授权视为一次性。

    保留的部分：重复授权返回同一策略、**已花额度不被重置**；换模式须显式开新轮次。
    """
    units, manifest = _material(tmp_path, monkeypatch)
    _authorize(units[0], manifest)
    _spend(units[0], manifest, attempt_id="attempt-a", category="calc_representation")
    assert _used(manifest, units[0], "calc_representation") == 1

    same = _authorize(units[0], manifest)
    assert same["mode"] == "automatic"
    assert _used(manifest, units[0], "calc_representation") == 1, "重复授权不得重置额度"

    with pytest.raises(JiaoduiError) as err:
        _authorize(units[0], manifest, mode="interactive")
    assert err.value.code == "execution-policy-locked"


def test_cli_requires_attempt_id_and_fingerprint_for_unit_events():
    from jiaodui.cli import build_parser

    parser = build_parser()
    choices = next(action for action in parser._actions if getattr(action, "choices", None)).choices

    with pytest.raises(JiaoduiError):
        choices["unit-event"].parse_args(["--task-id", "t", "--unit-id", "u", "--phase", "read"])
    with pytest.raises(JiaoduiError):
        choices["unit-recovery"].parse_args(["--task-id", "t", "--unit-id", "u",
                                             "--attempt-id", "a-1"])
    args = choices["unit-recovery"].parse_args([
        "--task-id", "t", "--unit-id", "u", "--attempt-id", "a-1",
        "--fingerprint", FINGERPRINT_A, "--error-code", "usage",
    ])
    assert args.attempt_id == "a-1"
    assert args.fingerprint == FINGERPRINT_A
    event = choices["unit-event"].parse_args([
        "--task-id", "t", "--unit-id", "u", "--phase", "read", "--attempt-id", "a-1",
        "--expected-run-id", "run-1",
    ])
    assert event.expected_run_id == "run-1"
