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


def test_parse_v1_in_new_layout_requires_explicit_manual_legacy(tmp_path, monkeypatch):
    root, unit = _unit(tmp_path, monkeypatch)
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    report = f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n"
    (unit / "_校对报告.md").write_text(report, encoding="utf-8")

    with pytest.raises(BusinessError) as error:
        parse_unit(unit)
    assert error.value.code == "parse-v1-new-layout-forbidden"
    assert not (unit / "_校对数据.json").exists()


def test_manual_legacy_writes_data_without_registration_and_downstream_excludes_it(tmp_path, monkeypatch):
    root, unit = _unit(tmp_path, monkeypatch)
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    report = f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n"
    (unit / "_校对报告.md").write_text(report, encoding="utf-8")

    result = parse_unit(unit, manual_legacy=True)
    payload = __import__("json").loads((unit / "_校对数据.json").read_text(encoding="utf-8"))
    assert result["registered"] is False
    assert payload["legacy_manual"] is True
    assert not material.registered(root, material.load(root), unit)
    built = build_report(root / "units" / root.name)
    assert not built.complete
    assert built.failed and built.failed[0]["unit"] == unit.name


def test_manual_legacy_holds_material_lock_through_write(tmp_path, monkeypatch):
    from contextlib import contextmanager

    root, unit = _unit(tmp_path, monkeypatch)
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    original_lock = material.locked
    entered = []

    @contextmanager
    def tracked_lock(path):
        entered.append(path)
        with original_lock(path):
            yield

    monkeypatch.setattr(material, "locked", tracked_lock)
    parse_unit(unit, manual_legacy=True)
    assert entered == [root]


def test_manual_legacy_preserves_v2_or_damaged_data(tmp_path, monkeypatch):
    root, unit = _unit(tmp_path, monkeypatch)
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    data_path = unit / "_校对数据.json"

    for existing in (
        '{"schema_version":2,"corrections":[]}',
        '{damaged json',
        '{}',
        '{"schema_version":99,"corrections":[],"summary":"无问题"}',
    ):
        data_path.write_text(existing, encoding="utf-8")
        with pytest.raises(BusinessError) as error:
            parse_unit(unit, manual_legacy=True)
        assert error.value.code == "legacy-overwrite-v2-forbidden"
        assert data_path.read_text(encoding="utf-8") == existing


@pytest.mark.parametrize("operation", ["parse", "repair"])
@pytest.mark.parametrize("version", [True, 1.0, None])
def test_manual_legacy_rejects_non_integer_explicit_schema_without_writing(tmp_path, monkeypatch, operation, version):
    import json
    from jiaodui.report_repair import repair_unit_report

    root, unit = _unit(tmp_path, monkeypatch)
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    report = unit / "_校对报告.md"
    report.write_text(f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    data = unit / "_校对数据.json"
    data.write_text(json.dumps({"schema_version": version, "summary": "无问题", "corrections": []}), encoding="utf-8")
    paths = (root / material.MANIFEST, report, data)
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    with pytest.raises(BusinessError) as error:
        if operation == "parse":
            parse_unit(unit, manual_legacy=True)
        else:
            repair_unit_report(unit, apply=True, manual_legacy=True)
    assert error.value.code == "legacy-overwrite-v2-forbidden"
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths] == before


@pytest.mark.parametrize("explicit_version", [False, True])
def test_valid_v1_data_remains_compatible_for_repeat_manual_parse(tmp_path, monkeypatch, explicit_version):
    import json

    root, unit = _unit(tmp_path, monkeypatch)
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    (unit / "_校对报告.md").write_text(f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    existing = {"summary": "无问题", "corrections": []}
    if explicit_version:
        existing["schema_version"] = 1
    (unit / "_校对数据.json").write_text(json.dumps(existing), encoding="utf-8")
    result = parse_unit(unit, manual_legacy=True)
    assert result["verified"] is True and result["registered"] is False
    assert parse_unit(unit, manual_legacy=True)["registered"] is False
    assert material.load(root)["unit_records"] == []


def test_manual_legacy_rejects_current_run_v2_registration(tmp_path, monkeypatch):
    from jiaodui.workflow import _check_manual_legacy_overwrite

    root, unit = _unit(tmp_path, monkeypatch)
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    data = material.load(root)
    unit_id = data["unit_ids"][unit.name]
    run = data["runs"][-1]
    run.setdefault("unit_state", {})[unit_id] = {"phase": "parent_reviewed"}
    data.setdefault("unit_reviews", []).append({
        "unit_id": unit_id, "run_id": data["current_run_id"],
        "decision": "accepted", "reviewer_id": "parent",
        "recorded_at": "test", "inputs": data["unit_inputs"][unit.name],
        "report_sha256": "0" * 64, "proposal_sha256": "1" * 64,
        "self_check_sha256": "2" * 64,
    })
    data["unit_records"].append({
        "unit": unit.name, "run_id": data["current_run_id"],
        "report_sha256": "0" * 64, "recorded_at": "test",
        "inputs": data["unit_inputs"][unit.name],
    })
    with pytest.raises(BusinessError) as error:
        _check_manual_legacy_overwrite(unit, root, data)
    assert error.value.code == "legacy-overwrite-v2-forbidden"


@pytest.mark.parametrize("operation", ["parse", "repair"])
@pytest.mark.parametrize("data_state", ["missing", "v1"])
def test_manual_legacy_cannot_downgrade_registration_after_event_overwrites_phase(
    tmp_path, monkeypatch, operation, data_state,
):
    """登记的版本未知也须拒绝，不能依赖可被事件覆盖的 phase 或报告封套。"""
    from jiaodui.report_repair import repair_unit_report
    from v2_helpers import deliver_v2

    root, unit = _unit(tmp_path, monkeypatch)
    deliver_v2(unit, accept=False)
    data = material.load(root)
    unit_id = data["unit_ids"][unit.name]
    assert not data.get("unit_reviews")
    material.record_unit_event(data["task_id"], unit_id, phase="read", attempt_id="later-worker")
    assert material.load(root)["runs"][-1]["unit_state"][unit_id]["phase"] == "read"
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    report_path = unit / "_校对报告.md"
    report_path.write_text(f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    data_path = unit / "_校对数据.json"
    if data_state == "missing":
        data_path.unlink()
    else:
        data_path.write_text(
            '{"schema_version":1,"corrections":[],"summary":"无问题"}', encoding="utf-8")
    before = {path: path.read_bytes() if path.exists() else None
              for path in (root / material.MANIFEST, report_path, data_path)}

    with pytest.raises(BusinessError) as error:
        if operation == "parse":
            parse_unit(unit, manual_legacy=True)
        else:
            repair_unit_report(unit, apply=True, manual_legacy=True)
    assert error.value.code == "legacy-overwrite-v2-forbidden"
    assert {path: path.read_bytes() if path.exists() else None for path in before} == before


def test_legacy_layout_parse_behavior_is_unchanged(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    unit = workspace / "旧材料" / "单元1"
    unit.mkdir(parents=True)
    source = "正文甲。\n"
    (unit / "单元1.md").write_text(source, encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    result = parse_unit(unit, legacy_layout=True)
    assert result["registered"] is False
    payload = __import__("json").loads((unit / "_校对数据.json").read_text(encoding="utf-8"))
    assert "legacy_manual" not in payload


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
    from v2_helpers import deliver_v2

    deliver_v2(unit)
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
    first = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                              attempt_id="w1", error_code="usage")
    second = material.record_recovery_attempt(task_id, unit_id, None, fingerprint,
                                              attempt_id="w2", error_code="usage")
    denied = material.record_recovery_attempt(task_id, unit_id, None, changed_agent,
                                              attempt_id="w3", error_code="usage")
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
    event = material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-1")
    assert event["phase"] == "read"
    cancellation = material.record_unit_cancel(task_id, unit_id, attempt_id="attempt-1",
                                               initiator="user", reason="user_cancel")
    assert cancellation["initiator"] == "user"
    run = material.load(root)["runs"][-1]
    assert run["cancellations"][-1]["initiator"] == "user"
    assert run["unit_state"][unit_id]["last_event_at"] == event["at"]
    assert "recovery" not in run

    with pytest.raises(BusinessError) as error:
        material.record_unit_cancel(task_id, unit_id, attempt_id="attempt-2",
                                    initiator="parent", reason="user_cancel")
    assert error.value.code == "cancel-invalid"
