from __future__ import annotations

import hashlib

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError
from jiaodui.report import build_report
from jiaodui.workflow import convert_material, split_material, parse_unit


def _unit(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("1．设物体A。\n", encoding="utf-8")
    converted = convert_material(source, material_name="交付状态", mode="exam")
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    root = workspace / "校对" / "交付状态"
    unit = __import__("pathlib").Path(split.unit_dirs[0])
    return root, unit


def test_report_file_generation_is_not_formal_delivery_when_unit_failed(tmp_path, monkeypatch):
    root, unit = _unit(tmp_path, monkeypatch)
    result = build_report(root / "units" / root.name)
    assert result.out_path
    assert not result.complete
    assert result.failed
    assert not result.to_dict()["complete"]

    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    parse_unit(unit)
    complete = build_report(root / "units" / root.name)
    assert complete.complete
    assert not complete.failed


def test_recovery_budget_is_cumulative_by_unit_category_and_fingerprint(tmp_path, monkeypatch):
    root, unit = _unit(tmp_path, monkeypatch)
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    unit_id = data["unit_ids"][unit.name]
    task_id = data["task_id"]

    fingerprint = hashlib.sha256(b"bad-arg").hexdigest()
    changed_agent = hashlib.sha256(b"same-error-different-agent").hexdigest()
    first = material.record_recovery_attempt(task_id, unit_id, "call_correction", fingerprint)
    second = material.record_recovery_attempt(task_id, unit_id, "call_correction", fingerprint)
    denied = material.record_recovery_attempt(task_id, unit_id, "call_correction", changed_agent)
    assert first["allowed"] and second["allowed"]
    assert second["fingerprint_attempts"] == 2
    assert not denied["allowed"] and not denied["retryable"]
    assert denied["remaining"] == 0

    current = material.load(root)["runs"][-1]
    state = current["recovery"][unit_id]["call_correction"]
    assert state["used"] == 2
    assert sum(state["fingerprints"].values()) == 2


def test_cancel_events_keep_initiator_and_reason_and_do_not_consume_retry_budget(tmp_path, monkeypatch):
    root, unit = _unit(tmp_path, monkeypatch)
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    unit_id, task_id = data["unit_ids"][unit.name], data["task_id"]
    event = material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-1",
                                       cancel_initiator="user", cancel_reason="user_cancel")
    assert event["phase"] == "read"
    run = material.load(root)["runs"][-1]
    assert run["cancellations"][-1]["initiator"] == "user"
    assert run["unit_state"][unit_id]["last_event_at"] == event["at"]
    assert "recovery" not in run

    with pytest.raises(BusinessError) as error:
        material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-2",
                                   cancel_initiator="parent", cancel_reason="user_cancel")
    assert error.value.code == "cancel-invalid"
