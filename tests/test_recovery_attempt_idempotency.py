"""B3：恢复记账的 attempt_id 幂等契约。

对齐 main 的幂等意图（main 把恢复做成 unit_event，靠事件账本里 attempt_id 的
唯一性实现），但分支的事件账本与预算账本分开，所以另建 attempt 索引；错误码用
main 的 `attempt-id-conflict` 保持一致。语义：

- 同 attempt + 同指纹 + 同类别 → **幂等重放**：不再扣费，返回原结果并标 `idempotent`;
- 同 attempt + 不同指纹（或映射到不同类别）→ `attempt-id-conflict`；
- 同指纹 + 新 attempt → 正常再扣一次（额度内）；额度用满则照常被拒；
- `expected_run_id` 与当前轮次不一致 → `run-changed`（CAS 防护，采纳 main）；
- `attempt_id` 取值非法 → `invalid-attempt-id`。
"""
from __future__ import annotations

import hashlib

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError
from jiaodui.workflow import convert_material, split_material


def _scene(tmp_path, monkeypatch, name="B3幂等测试"):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    converted = convert_material(source, material_name=name, mode="lecture")
    split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    root = workspace / "校对" / name
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    unit_id = list(data["unit_ids"].values())[0]
    return root, data["task_id"], unit_id


def _fp(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _ledger(root, unit_id):
    return material.load(root)["runs"][-1]["recovery"][unit_id]


def test_same_attempt_is_idempotent_and_does_not_charge_again(tmp_path, monkeypatch):
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)
    fingerprint = _fp("usage")

    first = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                             attempt_id="a1", error_code="usage")
    manifest = root / material.MANIFEST
    before = manifest.read_bytes()
    replay = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                              attempt_id="a1", error_code="usage")
    assert manifest.read_bytes() == before, "重放不得写盘"

    assert first["allowed"] is True and first.get("idempotent") is not True
    assert replay["idempotent"] is True
    assert replay["allowed"] == first["allowed"]
    assert replay["used"] == first["used"] == 1
    assert replay["remaining"] == first["remaining"] == 1
    assert _ledger(root, unit_id)["call_correction"]["used"] == 1, "重放不得再扣"
    # 重放是**真·无操作**：不写盘、不追加事件（采纳 main 的语义——否则被反复重试的
    # 调用会让清单无界增长；审计需求由 attempt 索引与返回值的 idempotent=true 满足）
    events = material.load(root)["runs"][-1]["recovery_events"]
    assert len(events) == 1 and events[0]["attempt_id"] == "a1"
    assert events[0].get("replay") is None


def test_same_attempt_with_different_fingerprint_is_rejected(tmp_path, monkeypatch):
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)

    material.record_recovery_attempt(task_id, unit_id, None, _fp("usage"),
                                     attempt_id="a1", error_code="usage")
    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(task_id, unit_id, None, _fp("other"),
                                         attempt_id="a1", error_code="usage")

    assert error.value.code == "attempt-id-conflict"
    assert _ledger(root, unit_id)["call_correction"]["used"] == 1, "冲突不得扣费"


def test_same_attempt_with_different_category_is_rejected(tmp_path, monkeypatch):
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)
    fingerprint = _fp("x")

    material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                     attempt_id="a1", error_code="usage")
    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                         attempt_id="a1", error_code="verify_failed")
    assert error.value.code == "attempt-id-conflict"


def test_new_attempt_spends_again_even_with_same_fingerprint(tmp_path, monkeypatch):
    """同指纹换 attempt 要再扣一次（指纹只标识"同一失败"，不承担幂等）。"""
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)
    fingerprint = _fp("usage")

    first = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                             attempt_id="a1", error_code="usage")
    second = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                              attempt_id="a2", error_code="usage")
    third = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                             attempt_id="a3", error_code="usage")

    assert first["used"] == 1 and second["used"] == 2
    assert third["allowed"] is False and third["remaining"] == 0
    assert _ledger(root, unit_id)["call_correction"]["used"] == 2


def test_expected_run_id_is_a_cas_guard(tmp_path, monkeypatch):
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)
    data = material.load(root)

    ok = material.record_recovery_attempt(task_id, unit_id, None, _fp("usage"),
                                          attempt_id="a1", error_code="usage",
                                          expected_run_id=data["current_run_id"])
    assert ok["allowed"] is True

    with pytest.raises(BusinessError) as error:
        material.record_recovery_attempt(task_id, unit_id, None, _fp("usage2"),
                                         attempt_id="a2", error_code="usage",
                                         expected_run_id="0" * 32)
    assert error.value.code == "run-changed"


def test_invalid_attempt_id_is_rejected(tmp_path, monkeypatch):
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)
    for bad in ("", "   ", "x" * 201, 7, None):
        with pytest.raises(BusinessError) as error:
            material.record_recovery_attempt(task_id, unit_id, None, _fp("usage"),
                                             attempt_id=bad, error_code="usage")
        assert error.value.code == "invalid-attempt-id", bad
    assert "call_correction" not in material.load(root)["runs"][-1].get("recovery", {}).get(unit_id, {})


def test_denied_attempt_leaves_no_trace_and_repeats_the_same_verdict(tmp_path, monkeypatch):
    """被拒的 attempt **不写盘**（采纳 main：不改变状态的操作不落痕）。

    因此重复同一个 attempt_id 不会被当成幂等重放，而是**重新判定**并得到同一结论；
    这样反复重试被拒的 attempt 也不会让清单增长。
    """
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)
    for index in range(2):
        material.record_recovery_attempt(task_id, unit_id, None, _fp(f"u{index}"),
                                         attempt_id=f"a{index}", error_code="usage")
    manifest = root / material.MANIFEST
    before = manifest.read_bytes()

    denied = material.record_recovery_attempt(task_id, unit_id, None, _fp("u9"),
                                              attempt_id="a9", error_code="usage")
    assert denied["allowed"] is False and denied["remaining"] == 0
    assert manifest.read_bytes() == before, "被拒不得写盘"
    assert "a9" not in material.load(root)["runs"][-1].get("recovery_attempts", {}).get(unit_id, {})

    again = material.record_recovery_attempt(task_id, unit_id, None, _fp("u9"),
                                             attempt_id="a9", error_code="usage")
    assert again["allowed"] is False and again.get("idempotent") is not True
    assert manifest.read_bytes() == before
    assert _ledger(root, unit_id)["call_correction"]["used"] == 2
