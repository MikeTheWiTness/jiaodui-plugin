from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError


def _material(tmp_path, monkeypatch):
    from jiaodui.workflow import convert_material, split_material

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "卷.md"
    source.write_text("1．题干。\n\n2．第二题。\n", encoding="utf-8")
    converted = convert_material(source, mode="exam", mode_origin="user")
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    return workspace, Path(split.unit_dirs[0]), workspace / "校对" / "卷" / "_校对记录.json"


def test_manifest_run_requires_explicit_idempotent_execution_policy(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "execution_policy" not in data["runs"][-1]
    from jiaodui.workflow import set_execution_policy
    before = manifest.read_bytes()
    policy = set_execution_policy(unit, mode="automatic", origin="confirmed",
                                 expected_run_id=data["current_run_id"])
    assert policy["mode"] == "automatic"
    assert policy["origin"] == "confirmed"
    assert policy["confirmed_at"]
    assert policy["budgets"] == {
        "call_correction": 2,
        "calc_representation": 2,
        "report_repair": 3,
        "targeted_review": 2,
        "technical_redispatch": 1,
        "image_schema_fix": 2,
    }
    assert policy["spent"] == {}
    after_confirmation = manifest.read_bytes()
    assert after_confirmation != before
    set_execution_policy(unit, mode="automatic", origin="confirmed",
                         expected_run_id=data["current_run_id"])
    assert manifest.read_bytes() == after_confirmation


def test_execution_policy_validation_rejects_budget_drift(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    from jiaodui.workflow import set_execution_policy
    set_execution_policy(unit, mode="automatic", origin="user", expected_run_id=data["current_run_id"])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["runs"][-1]["execution_policy"]["budgets"]["report_repair"] = 99
    manifest.write_text(json.dumps(data), encoding="utf-8")
    from jiaodui import material
    with pytest.raises(JiaoduiError) as err:
        material.load(manifest.parent)
    assert err.value.code == "invalid-manifest"


def test_unit_events_require_policy_attempt_and_expected_run(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    from jiaodui.workflow import record_unit_event, recover_unit, set_execution_policy
    run_id = data["current_run_id"]
    before = manifest.read_bytes()
    with pytest.raises(JiaoduiError) as err:
        record_unit_event(unit, phase="verify", event="started", expected_run_id=run_id,
                          attempt_id="attempt-1", fingerprint="a" * 64)
    assert err.value.code == "execution-policy-required"
    assert manifest.read_bytes() == before

    set_execution_policy(unit, mode="automatic", origin="user", expected_run_id=run_id)
    record_unit_event(unit, phase="verify", event="started", expected_run_id=run_id,
                      attempt_id="attempt-1", fingerprint="a" * 64)
    for source in ("user_cancel", "permission_denied"):
        with pytest.raises(JiaoduiError) as err:
            recover_unit(unit, source=source, phase="verify", expected_run_id=run_id,
                         attempt_id=f"{source}-1", fingerprint="b" * 64)
        assert err.value.code == "recovery-forbidden"
    changed = json.loads(manifest.read_text(encoding="utf-8"))
    events = changed["runs"][-1]["unit_events"]
    assert [e["event"] for e in events] == ["started"]
    assert changed["runs"][-1]["execution_policy"]["spent"] == {}


def test_late_unit_event_cannot_write_to_new_run(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    from jiaodui.workflow import record_unit_event
    with pytest.raises(JiaoduiError) as err:
        record_unit_event(unit, phase="校对", event="finished", expected_run_id="stale-run",
                          attempt_id="attempt-stale", fingerprint="a" * 64)
    assert err.value.code == "run-changed"


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
    assert "execution-policy" in subcommands
    assert "unit-recovery" in subcommands
    assert "unit-event" in subcommands
    args = parser.parse_args(["unit-event", "--unit", "第1题", "--phase", "verify",
                              "--event", "started", "--attempt-id", "attempt-1",
                              "--fingerprint", "a" * 64, "--expected-run-id", "run"])
    assert args.expected_run_id == "run"
    assert args.attempt_id == "attempt-1"


def test_changing_mode_preserves_spent_budget(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    from jiaodui.workflow import record_unit_event, set_execution_policy

    run_id = data["current_run_id"]
    set_execution_policy(unit, mode="automatic", origin="user", expected_run_id=run_id)
    record_unit_event(unit, phase="call", event="schema_fix", category="calc_representation",
                      attempt_id="calc-1", fingerprint="a" * 64, expected_run_id=run_id)
    changed = set_execution_policy(unit, mode="interactive", origin="user", expected_run_id=run_id)
    assert changed["mode"] == "interactive"
    assert changed["spent"][unit.name]["calc_representation"] == 1


def test_event_budget_is_idempotent_and_cancel_cannot_consume_it(tmp_path, monkeypatch):
    _, unit, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    from jiaodui.workflow import record_unit_event, set_execution_policy

    run_id = data["current_run_id"]
    set_execution_policy(unit, mode="automatic", origin="user", expected_run_id=run_id)
    record_unit_event(unit, phase="call", event="schema_fix", source="image_schema",
                      category="image_schema_fix", attempt_id="image-1", fingerprint="a" * 64,
                      expected_run_id=run_id)
    before = manifest.read_bytes()
    record_unit_event(unit, phase="call", event="schema_fix", source="image_schema",
                      category="image_schema_fix", attempt_id="image-1", fingerprint="a" * 64,
                      expected_run_id=run_id)
    assert manifest.read_bytes() == before
    with pytest.raises(JiaoduiError) as err:
        record_unit_event(unit, phase="call", event="cancelled", source="user_cancel",
                          attempt_id="cancel-1", fingerprint="b" * 64, category="image_schema_fix",
                          expected_run_id=run_id)
    assert err.value.code == "recovery-forbidden"
    after = json.loads(manifest.read_text(encoding="utf-8"))
    spent = after["runs"][-1]["execution_policy"]["spent"][unit.name]
    assert spent["call_correction"] == 1
    assert spent["image_schema_fix"] == 1
