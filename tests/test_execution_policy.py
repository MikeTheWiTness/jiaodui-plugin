from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from jiaodui.errors import BusinessError
from jiaodui import material
from jiaodui.workflow import convert_material


def _material(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    convert_material(source, material_name="隔离策略测试")
    return workspace / "校对" / "隔离策略测试"


def test_execution_policy_is_recorded_once_per_run(tmp_path, monkeypatch):
    root = _material(tmp_path, monkeypatch)
    policy = material.set_execution_policy(root, "automatic")

    manifest = json.loads((root / material.MANIFEST).read_text(encoding="utf-8"))
    run = manifest["runs"][-1]
    assert run["execution_policy"] == policy
    assert policy["run_id"] == manifest["current_run_id"]
    assert policy["budgets"] == {
        "call_correction": 2,
        "calc_representation": 2,
        "report_repair": 3,
        "targeted_review": 2,
        "technical_redispatch": 1,
        "image_schema_fix": 2,
    }
    assert material.set_execution_policy(root, "automatic") == policy
    with pytest.raises(BusinessError) as error:
        material.set_execution_policy(root, "interactive")
    assert error.value.code == "execution-policy-locked"


def test_execution_policy_is_invalidated_by_new_run(tmp_path, monkeypatch):
    root = _material(tmp_path, monkeypatch)
    material.set_execution_policy(root, "interactive", "confirmed")

    with material.locked(root):
        manifest = material.load(root)
        material.new_run(manifest, manifest["params"], manifest["resources"])
        material.write(root, manifest)

    manifest = material.load(root)
    assert "execution_policy" not in manifest["runs"][-1]
    assert manifest["runs"][-2]["execution_policy"]["mode"] == "interactive"
    assert Path(manifest["paths"]["paper"]).is_absolute() is False


def test_execution_policy_rejects_unknown_mode_and_origin(tmp_path, monkeypatch):
    root = _material(tmp_path, monkeypatch)
    for mode, origin, code in [
        ("auto", "user", "invalid-execution-mode"),
        ("automatic", "default", "invalid-execution-origin"),
    ]:
        with pytest.raises(BusinessError) as error:
            material.set_execution_policy(root, mode, origin)
        assert error.value.code == code


def test_execution_policy_cli_requires_workspace_and_emits_json(tmp_path, monkeypatch):
    import subprocess
    import sys

    root = _material(tmp_path, monkeypatch)
    workspace = root.parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "--work-root", str(workspace), "execution-policy",
         str(root), "--mode", "automatic", "--origin", "confirmed", "--json"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["execution_policy"]["mode"] == "automatic"


# ---- B1：策略机制搬进 execution_policy.py，并采纳 main 的连带扣费语义 ----

def _scene(tmp_path, monkeypatch, name="策略机制测试"):
    """建材料 + 拆出一个单元 + 写入执行模式，返回 (root, task_id, unit_id)。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    converted = convert_material(source, material_name=name, mode="lecture")
    from jiaodui.workflow import split_material

    split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    root = workspace / "校对" / name
    material.set_execution_policy(root, "automatic")
    manifest = material.load(root)
    unit = manifest["unit_set"][0]
    return root, manifest["task_id"], manifest["unit_ids"][unit]


def test_image_schema_fix_charges_call_budget_too(tmp_path, monkeypatch):
    """图片格式修复本身占一次调用：除 image_schema_fix 外连带扣 call_correction。

    采纳 main 的 `_charges` 语义（main 侧有测试锁定）。只扣一类会漏算调用成本。
    """
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)

    result = material.record_recovery_attempt(task_id, unit_id, None, "a" * 64,
                                              attempt_id="img-1", error_code="images.missing")

    assert result["allowed"] is True and result["category"] == "image_schema_fix"
    assert result["charged"] == ["image_schema_fix", "call_correction"]
    state = material.load(root)["runs"][-1]["recovery"][unit_id]
    assert state["image_schema_fix"]["used"] == 1
    assert state["call_correction"]["used"] == 1, "必须连带扣一次 call_correction"
    assert state["image_schema_fix"]["fingerprints"] == {"a" * 64: 1}
    assert state["call_correction"]["fingerprints"] == {}, "连带扣只记成本，不记失败指纹"


def test_exhausted_call_budget_blocks_image_schema_fix(tmp_path, monkeypatch):
    """连带扣的另一面：call_correction 用满后图片修复必须被拒，且不得部分扣费。"""
    root, task_id, unit_id = _scene(tmp_path, monkeypatch)

    for index in range(2):  # call_correction 额度 2，用满
        fingerprint = hashlib.sha256(f"used-{index}".encode()).hexdigest()
        allowed = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                                   attempt_id=f"use-{index}", error_code="usage")
        assert allowed["allowed"] is True

    blocked_fingerprint = hashlib.sha256(b"blocked-image-fix").hexdigest()
    blocked = material.record_recovery_attempt(task_id, unit_id, None, blocked_fingerprint,
                                               attempt_id="img-blocked", error_code="images.missing")

    assert blocked["allowed"] is False
    assert blocked["category"] == "image_schema_fix"
    assert blocked["blocked_category"] == "call_correction"
    assert blocked["remaining"] == 0
    state = material.load(root)["runs"][-1]["recovery"][unit_id]
    assert state.get("image_schema_fix", {}).get("used", 0) == 0, "被拒时不得部分扣费，也不落零状态"
    assert state["call_correction"]["used"] == 2


def test_policy_mechanism_lives_in_pure_module():
    """策略机制落在纯模块里（无 IO），material 只调用它。"""
    from jiaodui import execution_policy

    assert execution_policy.BUDGETS == {
        "call_correction": 2, "calc_representation": 2, "report_repair": 3,
        "targeted_review": 2, "technical_redispatch": 1, "image_schema_fix": 2,
    }
    assert execution_policy.charges("image_schema_fix") == ("image_schema_fix", "call_correction")
    assert execution_policy.charges("call_correction") == ("call_correction",)
    with pytest.raises(BusinessError) as error:
        execution_policy.charges("no-such-category")
    assert error.value.code == "recovery-invalid"
    source = Path(execution_policy.__file__).read_text(encoding="utf-8")
    for forbidden in ("open(", "json.load", "subprocess", "Path("):
        assert forbidden not in source, f"纯模块不得含 IO：{forbidden}"


def test_fingerprint_error_code_is_specific():
    """指纹非法用更具体的错误码（采纳 main 的 invalid-attempt-fingerprint）。"""
    from jiaodui import execution_policy

    for bad in ("not-a-hash", "A" * 64, "", None, 7):
        with pytest.raises(BusinessError) as error:
            execution_policy.validate_fingerprint(bad)
        assert error.value.code == "invalid-attempt-fingerprint", bad
    with pytest.raises(BusinessError) as error:
        execution_policy.validate_attempt("", "a" * 64)
    assert error.value.code == "invalid-attempt-id"
