from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError


FINGERPRINT_A = "a" * 64


def _material(tmp_path, monkeypatch):
    from jiaodui.workflow import convert_material, split_material

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "卷.md"
    source.write_text("1．题干。\n\n2．第二题。\n", encoding="utf-8")
    converted = convert_material(source, mode="exam", mode_origin="user")
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    units = [Path(path) for path in split.unit_dirs]
    manifest = workspace / "校对" / "卷" / "_校对记录.json"
    return units, manifest


def _authorize(unit: Path, manifest: Path, *, mode="automatic", origin="user"):
    from jiaodui.workflow import set_execution_policy

    data = json.loads(manifest.read_text(encoding="utf-8"))
    return set_execution_policy(unit, mode=mode, origin=origin,
                                expected_run_id=data["current_run_id"])


def _event(unit: Path, manifest: Path, *, attempt_id: str, fingerprint=FINGERPRINT_A,
           category="call_correction", phase="tool", event="correction", source=None):
    from jiaodui.workflow import record_unit_event

    data = json.loads(manifest.read_text(encoding="utf-8"))
    return record_unit_event(
        unit, phase=phase, event=event, source=source, category=category,
        attempt_id=attempt_id, fingerprint=fingerprint,
        expected_run_id=data["current_run_id"])


def test_new_run_is_not_preauthorized_and_attempt_fails_without_policy(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    before = manifest.read_bytes()
    data = json.loads(before)
    assert "execution_policy" not in data["runs"][-1]

    with pytest.raises(JiaoduiError) as err:
        _event(units[0], manifest, attempt_id="attempt-1")
    assert err.value.code == "execution-policy-required"
    assert manifest.read_bytes() == before
    from jiaodui.workflow import recover_unit
    with pytest.raises(JiaoduiError) as err:
        recover_unit(units[0], source="timeout", phase="verify", expected_run_id=data["current_run_id"],
                     attempt_id="retry-without-policy", fingerprint=FINGERPRINT_A)
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
        _event(units[0], manifest, attempt_id=f"{units[0].name}-call-{index}")

    with pytest.raises(JiaoduiError) as err:
        _event(units[0], manifest, attempt_id="第1题-call-over")
    assert err.value.code == "execution-budget-exhausted"
    _event(units[1], manifest, attempt_id="第2题-call-0")  # 第2题有独立额度
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["runs"][-1]["execution_policy"]["spent"]["第2题"]["call_correction"] == 1
    _event(units[1], manifest, attempt_id="第2题-call-1")
    with pytest.raises(JiaoduiError):
        _event(units[1], manifest, attempt_id="第2题-call-third")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    spent = data["runs"][-1]["execution_policy"]["spent"]
    assert spent["第1题"]["call_correction"] == 2
    assert spent["第2题"]["call_correction"] == 2


def test_attempt_id_is_idempotent_but_same_fingerprint_new_attempt_spends(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)

    first = _event(unit, manifest, attempt_id="attempt-a")
    before_duplicate = manifest.read_bytes()
    same_attempt = _event(unit, manifest, attempt_id="attempt-a", source="agent-changed")
    assert same_attempt["at"] == first["at"]
    assert manifest.read_bytes() == before_duplicate

    _event(unit, manifest, attempt_id="attempt-b", fingerprint=FINGERPRINT_A)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    spent = data["runs"][-1]["execution_policy"]["spent"][unit.name]
    assert spent["call_correction"] == 2
    assert len([e for e in data["runs"][-1]["unit_events"] if e["unit"] == unit.name]) == 2


def test_reusing_attempt_id_with_different_fingerprint_is_rejected(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    _authorize(units[0], manifest)
    _event(units[0], manifest, attempt_id="attempt-a")
    before = manifest.read_bytes()

    with pytest.raises(JiaoduiError) as err:
        _event(units[0], manifest, attempt_id="attempt-a", fingerprint="b" * 64)
    assert err.value.code == "attempt-id-conflict"
    assert manifest.read_bytes() == before


def test_fingerprint_must_be_sha256_hex(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    _authorize(units[0], manifest)
    with pytest.raises(JiaoduiError) as err:
        _event(units[0], manifest, attempt_id="attempt-a", fingerprint="not-a-hash")
    assert err.value.code == "invalid-attempt-fingerprint"


def test_image_schema_fix_spends_call_budget_once_per_attempt_not_additively(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)

    for index in range(2):
        _event(unit, manifest, attempt_id=f"image-{index}", category="image_schema_fix",
               phase="read_image", event="schema_correction", source="image_schema")
    before = manifest.read_bytes()
    with pytest.raises(JiaoduiError) as err:
        _event(unit, manifest, attempt_id="image-over", category="image_schema_fix",
               phase="read_image", event="schema_correction", source="image_schema")
    assert err.value.code == "execution-budget-exhausted"
    assert manifest.read_bytes() == before

    data = json.loads(before)
    spent = data["runs"][-1]["execution_policy"]["spent"][unit.name]
    assert spent["image_schema_fix"] == 2
    assert spent["call_correction"] == 2


def test_cancellation_and_permission_never_spend_or_recover(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    run_id = data["current_run_id"]
    before = manifest.read_bytes()
    from jiaodui.workflow import recover_unit

    for source in ("user_cancel", "permission_denied"):
        with pytest.raises(JiaoduiError) as err:
            recover_unit(unit, source=source, phase="verify", attempt_id=f"{source}-1",
                         fingerprint=FINGERPRINT_A, expected_run_id=run_id)
        assert err.value.code == "recovery-forbidden"
    assert manifest.read_bytes() == before

    _event(unit, manifest, attempt_id="cancel-event", category=None, event="cancelled",
           source="user_cancel")
    after = json.loads(manifest.read_text(encoding="utf-8"))
    assert after["runs"][-1]["execution_policy"]["spent"] == {}


def test_recovery_uses_only_technical_redispatch_budget(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    unit = units[0]
    _authorize(unit, manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    from jiaodui.workflow import recover_unit

    recovery = recover_unit(unit, source="timeout", phase="verify", attempt_id="retry-1",
                            fingerprint=FINGERPRINT_A, expected_run_id=data["current_run_id"])
    assert recovery["category"] == "technical_redispatch"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    spent = data["runs"][-1]["execution_policy"]["spent"][unit.name]
    assert spent["technical_redispatch"] == 1
    assert "unit_recovery" not in spent and "technical_retry" not in spent
    before = manifest.read_bytes()
    with pytest.raises(JiaoduiError) as err:
        recover_unit(unit, source="timeout", phase="verify", attempt_id="retry-2",
                     fingerprint=FINGERPRINT_A, expected_run_id=data["current_run_id"])
    assert err.value.code == "execution-budget-exhausted"
    assert manifest.read_bytes() == before


def test_policy_change_preserves_all_per_unit_spent_budgets(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    _authorize(units[0], manifest)
    _event(units[0], manifest, attempt_id="attempt-a", category="calc_representation")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    from jiaodui.workflow import set_execution_policy

    policy = set_execution_policy(units[0], mode="interactive", origin="user",
                                 expected_run_id=data["current_run_id"])
    assert policy["spent"][units[0].name]["calc_representation"] == 1
    assert units[1].name not in policy["spent"]


def test_cli_requires_attempt_id_and_fingerprint_for_unit_events():
    from jiaodui.cli import build_parser

    parser = build_parser()
    choices = next(action for action in parser._actions if getattr(action, "choices", None)).choices
    with pytest.raises(JiaoduiError):
        choices["execution-policy"].parse_args([
            "--unit", "第1题", "--expected-run-id", "run-1",
        ])
    args = choices["unit-event"].parse_args([
        "--unit", "第1题", "--phase", "verify", "--event", "started",
        "--attempt-id", "a-1", "--fingerprint", FINGERPRINT_A,
        "--expected-run-id", "run-1",
    ])
    assert args.attempt_id == "a-1"
    assert re.fullmatch(r"[0-9a-f]{64}", args.fingerprint)
