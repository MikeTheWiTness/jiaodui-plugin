from __future__ import annotations

import json
from pathlib import Path

from test_main_policy_contract import _authorize, _event, _material, FINGERPRINT_A


def test_legacy_manifest_without_policy_remains_readable_but_not_authorized(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["runs"][-1].pop("execution_policy", None)
    manifest.write_text(json.dumps(data), encoding="utf-8")

    from jiaodui import material
    loaded = material.load(manifest.parent)
    assert loaded["current_run_id"] == data["current_run_id"]
    _authorize(units[0], manifest)
    _event(units[0], manifest, attempt_id="legacy-upgrade")


def test_legacy_aggregated_budget_migrates_conservatively_per_unit(tmp_path, monkeypatch):
    units, manifest = _material(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["runs"][-1]["execution_policy"] = {
        "mode": "automatic", "origin": "confirmed", "confirmed_at": data["runs"][-1]["started_at"],
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
    manifest.write_text(json.dumps(data), encoding="utf-8")

    from jiaodui.workflow import set_execution_policy
    policy = set_execution_policy(units[0], mode="interactive", origin="user",
                                  expected_run_id=data["current_run_id"])
    for unit in units:
        assert policy["spent"][unit.name]["call_correction"] == 1
        assert policy["spent"][unit.name]["report_repair"] == 2
        assert policy["spent"][unit.name]["technical_redispatch"] == 1
        assert policy["spent"][unit.name]["calc_representation"] == 1
