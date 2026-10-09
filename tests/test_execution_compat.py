"""main 时期的执行策略兼容契约测试，按结构化语义逐条映射（Phase 2 合并）。

映射规则（详见 `docs/PROCESS_REWORK.md` 的 Phase 2 记录）：

- `workflow.set_execution_policy(unit, mode=…, expected_run_id=…)`
  → `material.set_execution_policy(material_root, mode, origin)`：分支按**材料根**授权，
    轮次校验内置在清单里，不额外收 `expected_run_id`。
- `workflow.record_unit_event(...category=…)`（main 把恢复做成事件、由事件扣预算）
  → 分支把**心跳与预算分家**：心跳是 `material.record_unit_event`，扣预算走
    `material.record_recovery_attempt(..., error_code=…)`，类别由错误码确定性映射。
- `workflow.recover_unit(source=…)` → 同一恢复入口 + 对应错误码：
  `timeout`/`technical_crash` → `host-timeout`/`host-crash`；
  `user_cancel`/`permission_denied` → 错误码 `user-cancel`/`permission-denied`。
- 预算账本：main 的 `policy["spent"][unit][类别]` → 分支的
  `run["recovery"][unit_id][类别]["used"]`。
- 预算耗尽：main 抛 `execution-budget-exhausted`；分支返回 `allowed=false` 且
  `remaining=0`（保留返回式语义，编排侧据此停止补位，不靠异常控制流）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError

FINGERPRINT = "a" * 64
# 类别 → 该类别的一个代表性错误码（分支的映射见 jiaodui/error_classification.py）
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
    unit = Path(split.unit_dirs[0])
    manifest = workspace / "校对" / "卷" / "_校对记录.json"
    return workspace, unit, manifest


def _ids(manifest: Path, unit: Path):
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data["task_id"], data["unit_ids"][unit.name], data["current_run_id"]


def _authorize(unit: Path, manifest: Path, *, mode: str = "automatic", origin: str = "user"):
    from jiaodui import material

    return material.set_execution_policy(manifest.parent, mode, origin)


def _spend(unit: Path, manifest: Path, *, attempt_id: str, category: str = "call_correction",
           fingerprint: str = FINGERPRINT):
    from jiaodui import material

    task_id, unit_id, _ = _ids(manifest, unit)
    return material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                            attempt_id=attempt_id,
                                            error_code=ERROR_CODE[category])


def _recover(unit: Path, manifest: Path, *, attempt_id: str, error_code: str,
             fingerprint: str = FINGERPRINT):
    from jiaodui import material

    task_id, unit_id, _ = _ids(manifest, unit)
    return material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                            attempt_id=attempt_id, error_code=error_code)


def _used(manifest: Path, unit: Path, category: str) -> int:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    unit_id = data["unit_ids"][unit.name]
    return (data["runs"][-1].get("recovery", {}).get(unit_id, {})
            .get(category, {}).get("used", 0))


def test_manifest_run_requires_explicit_idempotent_execution_policy(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "execution_policy" not in data["runs"][-1]
    before = manifest.read_bytes()

    policy = _authorize(unit, manifest, mode="automatic", origin="confirmed")

    assert policy["mode"] == "automatic" and policy["origin"] == "confirmed"
    assert policy["confirmed_at"]
    assert policy["budgets"] == {
        "call_correction": 2,
        "calc_representation": 2,
        "report_repair": 3,
        "targeted_review": 2,
        "technical_redispatch": 1,
        "image_schema_fix": 2,
    }
    # 分支把已花额度记在 run.recovery（按 unit_id），不塞进 policy
    assert _used(manifest, unit, "call_correction") == 0
    assert policy["run_id"] == json.loads(manifest.read_text(encoding="utf-8"))["current_run_id"]
    after_confirmation = manifest.read_bytes()
    assert after_confirmation != before

    # 幂等：同模式同来源重复授权不改盘
    assert _authorize(unit, manifest, mode="automatic", origin="confirmed") == policy
    assert manifest.read_bytes() == after_confirmation


def test_execution_policy_validation_rejects_budget_drift(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    _authorize(unit, manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["runs"][-1]["execution_policy"]["budgets"]["report_repair"] = 99
    manifest.write_text(json.dumps(data), encoding="utf-8")

    from jiaodui import material

    with pytest.raises(JiaoduiError) as err:
        material.load(manifest.parent)
    assert err.value.code == "invalid-manifest"


def test_unit_events_require_policy_attempt_and_expected_run(tmp_path, monkeypatch):
    """阶段事件同样要求授权；没有授权不留下工作痕迹。"""
    from jiaodui import material

    _, unit, manifest = _material(tmp_path, monkeypatch)
    task_id, unit_id, run_id = _ids(manifest, unit)
    before = manifest.read_bytes()

    with pytest.raises(JiaoduiError) as err:
        material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-1",
                                   expected_run_id=run_id)
    assert err.value.code == "execution-policy-required"
    assert manifest.read_bytes() == before

    _authorize(unit, manifest)
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-1",
                              expected_run_id=run_id)
    for error_code in ("user-cancel", "permission-denied"):
        with pytest.raises(JiaoduiError) as err:
            _recover(unit, manifest, attempt_id=f"{error_code}-1", error_code=error_code)
        assert err.value.code == "recovery-forbidden"

    changed = json.loads(manifest.read_text(encoding="utf-8"))
    assert [event["phase"] for event in changed["runs"][-1]["unit_events"][unit_id]] == ["read"]
    assert _used(manifest, unit, "call_correction") == 0
    assert _used(manifest, unit, "technical_redispatch") == 0


def test_late_unit_event_cannot_write_to_new_run(tmp_path, monkeypatch):
    from jiaodui import material

    _, unit, manifest = _material(tmp_path, monkeypatch)
    task_id, unit_id, _ = _ids(manifest, unit)
    _authorize(unit, manifest)
    before = manifest.read_bytes()

    with pytest.raises(JiaoduiError) as err:
        material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-stale",
                                   expected_run_id="stale-run")
    assert err.value.code == "run-changed"
    assert manifest.read_bytes() == before


def test_build_report_complete_is_independent_from_file_ok(tmp_path):
    from jiaodui.report import build_report

    paper = tmp_path / "卷子"
    unit = paper / "第1题"
    unit.mkdir(parents=True)
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text("不合规报告", encoding="utf-8")
    result = build_report(paper, out_path=tmp_path / "out.md", legacy_layout=True)
    assert result.out_path and Path(result.out_path).is_file()
    assert result.to_dict()["complete"] is False
    assert result.to_dict()["ok"] is True


def test_build_report_complete_accepts_passed_and_explicit_skip(tmp_path):
    from jiaodui.report import build_report

    paper = tmp_path / "卷子"
    passed = paper / "第1题"
    passed.mkdir(parents=True)
    (passed / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (passed / "_校对报告.md").write_text(
        "一般问题\n### 标记原文\n设【1|a|b】为$O$点。\n### 修改原因\n1. 参数错误。\n",
        encoding="utf-8")
    skipped = paper / "第2题"
    skipped.mkdir()
    (skipped / "第2题.md").write_text("第二题。", encoding="utf-8")
    (skipped / ".skip_proofread").touch()
    result = build_report(paper, out_path=tmp_path / "whole.md", legacy_layout=True)
    assert result.to_dict()["ok"] is True
    assert result.to_dict()["complete"] is True
    assert [item["unit"] for item in result.skipped] == ["第2题"]


def test_build_report_cli_marks_partial_file_incomplete(tmp_path):
    import os
    import subprocess
    import sys

    paper = tmp_path / "卷子"
    unit = paper / "第1题"
    unit.mkdir(parents=True)
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text("不合规报告", encoding="utf-8")
    output = tmp_path / "whole.md"
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "jiaodui", "build-report", str(paper),
                           "--out", str(output), "--legacy-layout", "--json"], cwd=root,
                          env=os.environ.copy(), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True and payload["complete"] is False
    assert output.is_file()


def test_cli_registers_policy_and_unit_recovery_commands():
    from jiaodui.cli import build_parser

    parser = build_parser()
    subcommands = next(a for a in parser._actions if getattr(a, "choices", None)).choices
    for name in ("execution-policy", "unit-recovery", "unit-event"):
        assert name in subcommands

    event = subcommands["unit-event"].parse_args([
        "--task-id", "t" * 32, "--unit-id", "u" * 32, "--phase", "read",
        "--attempt-id", "a-1", "--expected-run-id", "run-1",
    ])
    assert event.attempt_id == "a-1" and event.expected_run_id == "run-1"

    recovery = subcommands["unit-recovery"].parse_args([
        "--task-id", "t" * 32, "--unit-id", "u" * 32, "--attempt-id", "a-1",
        "--fingerprint", FINGERPRINT, "--error-code", "usage",
    ])
    assert recovery.attempt_id == "a-1"

    # attempt_id 是必填：少一个就应报用法错误
    with pytest.raises(JiaoduiError):
        subcommands["unit-event"].parse_args(["--task-id", "t", "--unit-id", "u", "--phase", "read"])
    # 心跳不带失败指纹（指纹属于恢复记账，见下面的 unit-recovery）
    assert "fingerprint" not in {
        action.dest for action in subcommands["unit-event"]._actions
    }
    for argv in (["--task-id", "t", "--unit-id", "u", "--fingerprint", FINGERPRINT],
                 ["--task-id", "t", "--unit-id", "u", "--attempt-id", "a"]):
        with pytest.raises(JiaoduiError):
            subcommands["unit-recovery"].parse_args(argv)


def test_mode_change_is_locked_and_reauthorization_preserves_spent(tmp_path, monkeypatch):
    """路线差异：main 允许同一轮次改模式并保留已花额度；分支把授权视为一次性。

    保留的部分是「已花额度不被重置」：同模式同来源重复授权返回同一策略、账本不动；
    要换模式必须先显式开启新轮次（分支既有契约，见 test_execution_policy）。
    """
    _, unit, manifest = _material(tmp_path, monkeypatch)
    _authorize(unit, manifest, mode="automatic", origin="user")
    _spend(unit, manifest, attempt_id="calc-1", category="calc_representation")

    assert _used(manifest, unit, "calc_representation") == 1
    same = _authorize(unit, manifest, mode="automatic", origin="user")
    assert same["mode"] == "automatic"
    assert _used(manifest, unit, "calc_representation") == 1, "重复授权不得重置已花额度"

    with pytest.raises(JiaoduiError) as err:
        _authorize(unit, manifest, mode="interactive", origin="user")
    assert err.value.code == "execution-policy-locked"


def test_recovery_attempt_is_idempotent_and_cancel_cannot_consume_it(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    _authorize(unit, manifest)

    _spend(unit, manifest, attempt_id="image-1", category="image_schema_fix")
    before = manifest.read_bytes()
    replay = _spend(unit, manifest, attempt_id="image-1", category="image_schema_fix")
    assert replay["idempotent"] is True
    assert manifest.read_bytes() == before, "同 attempt 重放不得改盘"

    with pytest.raises(JiaoduiError) as err:
        _recover(unit, manifest, attempt_id="cancel-1", error_code="user-cancel")
    assert err.value.code == "recovery-forbidden"

    # image_schema_fix 连带扣 call_correction（B1 采纳 main 的语义）
    assert _used(manifest, unit, "image_schema_fix") == 1
    assert _used(manifest, unit, "call_correction") == 1
